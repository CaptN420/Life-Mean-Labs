"""
Inference Backend Abstraction.
Allows different backends (Transformers, vLLM, llama.cpp, Ollama, etc.)
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
import asyncio


class InferenceBackend(ABC):
    """Abstract base class for inference backends."""
    
    @abstractmethod
    async def load_model(self, model_id: str, config: dict) -> bool:
        """Load a model into memory/VRAM."""
        ...
    
    @abstractmethod
    async def unload_model(self, model_id: str) -> bool:
        """Unload a model from memory/VRAM."""
        ...
    
    @abstractmethod
    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """Generate a response from the model."""
        ...
    
    @abstractmethod
    async def health(self, model_id: str) -> bool:
        """Check if a model is healthy and ready."""
        ...
    
    @abstractmethod
    async def get_vram_usage(self) -> dict:
        """Get current VRAM usage statistics."""
        ...


class FakeInferenceBackend(InferenceBackend):
    """Fake backend for simulation mode - no GPU required."""
    
    def __init__(self, delay_ms: int = 100):
        self.delay_ms = delay_ms
        self.loaded_models: set[str] = set()
        self.vram_used_mb: int = 0
    
    async def load_model(self, model_id: str, config: dict) -> bool:
        """Simulate loading a model."""
        await asyncio.sleep(self.delay_ms / 1000)
        self.loaded_models.add(model_id)
        self.vram_used_mb += 5000 if 'clef' not in model_id else 1000
        return True
    
    async def unload_model(self, model_id: str) -> bool:
        """Simulate unloading a model."""
        await asyncio.sleep(self.delay_ms / 1000)
        self.loaded_models.discard(model_id)
        self.vram_used_mb -= 5000 if 'clef' not in model_id else 1000
        self.vram_used_mb = max(0, self.vram_used_mb)
        return True
    
    async def generate(self, model_id: str, messages: list[dict], **kwargs) -> dict:
        """Simulate model inference."""
        await asyncio.sleep(self.delay_ms / 1000)
        
        # Extract last user message
        user_msg = ""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                user_msg = msg.get('content', '')
                break
        
        # Return simulated response based on model
        if 'clef' in model_id or self.model_name in model_id:
            return {
                'model': model_id,
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': '{"next_action": "MODEL_A", "confidence": 0.91, "consensus_reached": false, "loop_detected": false}'
                    }
                }]
            }
        else:
            return {
                'model': model_id,
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': f"Simulated response from {model_id} about: {user_msg[:50]}..."
                    }
                }]
            }
    
    async def health(self, model_id: str) -> bool:
        """Check health (always healthy in simulation)."""
        return True
    
    async def get_vram_usage(self) -> dict:
        """Get simulated VRAM usage."""
        return {
            'used_mb': self.vram_used_mb,
            'free_mb': 80000 - self.vram_used_mb,
            'total_mb': 80000,
            'loaded_models': list(self.loaded_models)
        }
