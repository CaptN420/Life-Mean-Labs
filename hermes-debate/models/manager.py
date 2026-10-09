"""
Model Manager - handles model lifecycle and VRAM management.
"""

import asyncio
import logging
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from .registry import ModelRegistry, ModelEntry
from .backends.base import InferenceBackend
from ..config import HermesConfig

logger = logging.getLogger(__name__)


@dataclass
class ModelLock:
    """Lock for model operations."""
    model_id: str
    locked_at: datetime
    locked_by: str
    
    def is_expired(self, timeout_ms: int = 30000) -> bool:
        """Check if lock has expired."""
        elapsed = (datetime.utcnow() - self.locked_at).total_seconds() * 1000
        return elapsed > timeout_ms


class ModelManager:
    """Manages model loading, unloading, and VRAM."""
    
    def __init__(
        self,
        registry: ModelRegistry,
        backend: InferenceBackend,
        config: HermesConfig
    ):
        self.registry = registry
        self.backend = backend
        self.config = config
        
        self._locks: dict[str, ModelLock] = {}
        self._active_models: set[str] = set()
        self._lock = asyncio.Lock()
    
    async def load_model(self, model_id: str) -> bool:
        """Load a model into VRAM."""
        async with self._lock:
            entry = self.registry.get(model_id)
            if not entry:
                logger.error(f"Model {model_id} not found in registry")
                return False
            
            if entry.status == "READY":
                logger.info(f"Model {model_id} already loaded")
                return True
            
            # Check VRAM availability
            vram_info = await self.backend.get_vram_usage()
            if vram_info['used_mb'] + 5000 > self.config.runtime.max_vram_gb * 1024:
                logger.error(f"Insufficient VRAM: {vram_info['used_mb']}MB used")
                return False
            
            try:
                entry.status = "LOADING"
                config_dict = {
                    'model_id': entry.config.model_id,
                    'role': entry.config.role,
                    'max_tokens': entry.config.max_tokens,
                    'temperature': entry.config.temperature
                }
                
                success = await self.backend.load_model(model_id, config_dict)
                
                if success:
                    entry.status = "READY"
                    self._active_models.add(model_id)
                    entry.last_loaded = datetime.utcnow().timestamp()
                    logger.info(f"Model {model_id} loaded successfully")
                    return True
                else:
                    entry.status = "ERROR"
                    logger.error(f"Failed to load model {model_id}")
                    return False
                    
            except Exception as e:
                entry.status = "ERROR"
                logger.error(f"Error loading model {model_id}: {e}")
                return False
    
    async def unload_model(self, model_id: str) -> bool:
        """Unload a model from VRAM."""
        async with self._lock:
            entry = self.registry.get(model_id)
            if not entry:
                return False
            
            if entry.status != "READY":
                logger.warning(f"Model {model_id} not in READY state")
                return False
            
            try:
                entry.status = "UNLOADING"
                success = await self.backend.unload_model(model_id)
                
                if success:
                    entry.status = "UNLOADED"
                    self._active_models.discard(model_id)
                    logger.info(f"Model {model_id} unloaded successfully")
                    return True
                else:
                    logger.error(f"Failed to unload model {model_id}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error unloading model {model_id}: {e}")
                return False
    
    async def switch_model(self, from_model: str, to_model: str) -> bool:
        """Switch from one model to another."""
        # Check if from_model is Clef-flash (lightweight, high-frequency)
        entry = self.registry.get(from_model)
        should_keep_resident = False
        
        if (entry and entry.config.vram_class == "decision" 
            and self.config.runtime.keep_clef_resident):
            # Clef-flash IQ4_XS: attempt to keep resident if VRAM allows
            vram_info = await self.backend.get_vram_usage()
            available_mb = (self.config.runtime.max_vram_gb * 1024) - vram_info['used_mb']
            
            # Estimate Clef-flash size
            clef_estimated_size_mb = self.config.runtime.clef_estimated_size_mb
            
            if available_mb > clef_estimated_size_mb + self.config.runtime.vram_reserve_mb:
                logger.info(f"Keeping Clef-flash resident (available VRAM: {available_mb}MB)")
                should_keep_resident = True
        
        if not should_keep_resident:
            # Unload current model first (strict mode)
            await self.unload_model(from_model)
        
        # Load new model
        return await self.load_model(to_model)
    
    async def get_status(self, model_id: str) -> Optional[str]:
        """Get current status of a model."""
        entry = self.registry.get(model_id)
        return entry.status if entry else None
    
    async def ensure_loaded(self, model_id: str) -> bool:
        """Ensure a model is loaded."""
        entry = self.registry.get(model_id)
        if entry and entry.status == "READY":
            return True
        
        # For Clef-flash decision models, check VRAM before loading
        if (entry and entry.config.vram_class == "decision"
            and self.config.runtime.keep_clef_resident):
            vram_info = await self.backend.get_vram_usage()
            available_mb = (self.config.runtime.max_vram_gb * 1024) - vram_info['used_mb']
            
            # If VRAM is tight, don't load if it would exceed limit
            clef_estimated_size_mb = self.config.runtime.clef_estimated_size_mb
            if available_mb < clef_estimated_size_mb:
                logger.warning(f"Insufficient VRAM for Clef-flash ({available_mb}MB available)")
                return False
        
        return await self.load_model(model_id)
    
    async def ensure_unloaded(self, model_id: str) -> bool:
        """Ensure a model is unloaded."""
        entry = self.registry.get(model_id)
        if entry and entry.status == "UNLOADED":
            return True
        return await self.unload_model(model_id)
    
    async def get_vram_usage(self) -> dict:
        """Get current VRAM usage."""
        return await self.backend.get_vram_usage()
    
    @property
    def active_models(self) -> set[str]:
        """Get set of currently active models."""
        return self._active_models.copy()
