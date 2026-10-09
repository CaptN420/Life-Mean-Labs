"""
Model Pool — VRAM-aware model lifecycle management for debates.

Instead of load/unload on every turn, the pool:
1. Pre-loads all models needed for a debate at start
2. Keeps them resident during the entire debate
3. Unloads only when the debate completes or explicitly requested
4. Supports concurrent model usage (multiple models in VRAM)
5. Tracks reference counts to avoid premature unloading
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModelSlot:
    """Tracks a single model's lifecycle in the pool."""
    model_id: str
    ref_count: int = 0
    loaded_at: Optional[float] = None
    last_used_at: Optional[float] = None
    config: Optional[dict] = field(default_factory=dict)

    @property
    def is_loaded(self) -> bool:
        return self.ref_count > 0 and self.loaded_at is not None

    def touch(self) -> None:
        """Mark as recently used."""
        self.last_used_at = time.time()


class ModelPool:
    """
    VRAM-aware model pool for debate orchestration.

    Usage:
        pool = ModelPool(manager)
        async with pool.acquire('model_a'):
            await agent.generate(...)
        # model_a stays loaded until pool.release() or context exits
    """

    def __init__(self, manager):
        """
        Args:
            manager: ModelManager instance
        """
        self.manager = manager
        self._slots: Dict[str, ModelSlot] = {}
        self._lock = asyncio.Lock()
        self._debate_active = False
        self._loaded_count = 0
        self._peak_vram_mb = 0

    async def start_debate(self) -> None:
        """Mark pool as active for a debate — prevents aggressive unloading."""
        self._debate_active = True
        logger.info("Model pool: debate started, keeping models resident")

    async def end_debate(self) -> None:
        """Mark pool as inactive — allows cleanup after debate."""
        self._debate_active = False
        logger.info("Model pool: debate ended")

    async def acquire(self, model_id: str, config: Optional[dict] = None) -> bool:
        """
        Acquire a model — increments ref count and ensures it's loaded.

        Returns True if successful, False otherwise.
        """
        async with self._lock:
            if model_id not in self._slots:
                self._slots[model_id] = ModelSlot(model_id=model_id, config=config or {})

            slot = self._slots[model_id]
            slot.ref_count += 1
            slot.last_used_at = time.time()

            if not slot.is_loaded:
                logger.info(f"Model pool: loading {model_id} (ref count: {slot.ref_count})")
                success = await self.manager.load_model(model_id)
                if success:
                    slot.loaded_at = time.time()
                    self._loaded_count += 1
                    vram_info = await self.manager.get_vram_usage()
                    self._peak_vram_mb = max(self._peak_vram_mb, vram_info.get('used_mb', 0))
                else:
                    slot.ref_count -= 1
                    if slot.ref_count == 0:
                        del self._slots[model_id]
                    return False

            logger.debug(f"Model pool: {model_id} acquired (refs: {slot.ref_count}, loaded: {self._loaded_count})")
            return True

    async def release(self, model_id: str) -> None:
        """
        Release a model — decrements ref count, unloads if no more refs.
        """
        async with self._lock:
            slot = self._slots.get(model_id)
            if not slot:
                return

            slot.ref_count -= 1
            slot.last_used_at = time.time()

            if slot.ref_count <= 0:
                logger.info(f"Model pool: unloading {model_id} (refs reached 0)")
                await self.manager.unload_model(model_id)
                slot.loaded_at = None
                self._loaded_count -= 1
                del self._slots[model_id]

    async def ensure_all_loaded(self, model_ids: list[str]) -> list[str]:
        """
        Pre-load all models needed for a debate.

        Returns list of successfully loaded model IDs.
        """
        loaded = []
        for model_id in model_ids:
            if await self.acquire(model_id):
                loaded.append(model_id)

        logger.info(f"Model pool: {len(loaded)}/{len(model_ids)} models pre-loaded")
        return loaded

    async def cleanup(self) -> None:
        """Unload all models — call after debate completes."""
        async with self._lock:
            model_ids = list(self._slots.keys())
            for model_id in model_ids:
                await self.manager.unload_model(model_id)

            self._slots.clear()
            self._loaded_count = 0
            logger.info("Model pool: all models unloaded")

    def get_status(self) -> dict:
        """Get current pool status."""
        return {
            'active': self._debate_active,
            'loaded_models': list(self._slots.keys()),
            'loaded_count': self._loaded_count,
            'peak_vram_mb': self._peak_vram_mb,
            'slots': {
                mid: {
                    'refs': slot.ref_count,
                    'loaded': slot.is_loaded,
                    'last_used': slot.last_used_at,
                }
                for mid, slot in self._slots.items()
            }
        }

    @property
    def active_models(self) -> Set[str]:
        """Get set of currently loaded model IDs."""
        return {mid for mid, slot in self._slots.items() if slot.is_loaded}

    async def __aenter__(self):
        await self.start_debate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.end_debate()
