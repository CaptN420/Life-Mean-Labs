"""
Mock Backend for testing without real models.
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from .base import InferenceBackend, ModelStatus

logger = logging.getLogger(__name__)


class MockBackend(InferenceBackend):
    """
    Mock backend for simulation and testing.
    Simulates model responses without actual inference.
    """
    
    def __init__(self, simulate_latency: float = 0.1):
        self.simulate_latency = simulate_latency
        self._models_loaded: set[str] = set()
        self._call_count: int = 0
    
    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """Generate mock response."""
        await asyncio.sleep(self.simulate_latency)
        self._call_count += 1
        
        # Extract last user message for context
        last_message = ""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_message = msg.get('content', '')
                break
        
        return {
            'content': f"[Mock Response from {model_id}] Simulated reasoning based on: {last_message[:100]}...",
            'model': model_id,
            'finish_reason': 'stop',
            'usage': {'prompt_tokens': 50, 'completion_tokens': 100, 'total_tokens': 150}
        }
    
    async def health_check(self) -> bool:
        """Mock backend is always healthy."""
        return True
    
    async def load(self, model_id: str, config: dict) -> bool:
        """Simulate model loading."""
        await asyncio.sleep(0.5)  # Simulate load time
        self._models_loaded.add(model_id)
        logger.info(f"Mock: Model {model_id} loaded")
        return True
    
    async def unload(self, model_id: str) -> bool:
        """Simulate model unloading."""
        self._models_loaded.discard(model_id)
        logger.info(f"Mock: Model {model_id} unloaded")
        return True
    
    async def get_vram_usage(self) -> dict:
        """Return mock VRAM usage."""
        return {
            'used_mb': 2048,
            'total_mb': 12000,
            'available_mb': 9952
        }
    
    @property
    def call_count(self) -> int:
        """Get total number of generate calls."""
        return self._call_count
    
    @property
    def models_loaded(self) -> set[str]:
        """Get set of loaded models."""
        return self._models_loaded.copy()
