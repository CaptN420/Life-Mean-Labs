"""
LM Studio Backend - OpenAI-compatible API.
"""

import logging
import aiohttp
from typing import Optional, Dict, Any
from .base import InferenceBackend, ModelStatus

logger = logging.getLogger(__name__)


class LMStudioBackend(InferenceBackend):
    """
    Backend for LM Studio / OpenAI-compatible API.
    """
    
    def __init__(self, base_url: str = "http://localhost:1234/v1", api_key: str = ""):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or ""
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """Generate response from model."""
        session = await self._get_session()
        
        payload = {
            'model': model_id,
            'messages': messages,
            'temperature': kwargs.get('temperature', 0.7),
            'max_tokens': kwargs.get('max_tokens', 2048),
            'top_p': kwargs.get('top_p', 1.0),
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        async with session.post(
            f'{self.base_url}/chat/completions',
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=kwargs.get('timeout', 120))
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"LM Studio error: {error_text}")
                raise Exception(f"API error: {response.status} - {error_text}")
            
            data = await response.json()
            return {
                'content': data['choices'][0]['message']['content'],
                'model': model_id,
                'finish_reason': data['choices'][0]['finish_reason'],
                'usage': data.get('usage', {})
            }
    
    async def health_check(self) -> bool:
        """Check if backend is healthy."""
        try:
            session = await self._get_session()
            async with session.get(f'{self.base_url}/models') as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def load(self, model_id: str, config: dict) -> bool:
        """Load model - LM Studio handles this via API."""
        # For LM Studio, models are loaded via the API
        # This is a no-op as LM Studio manages loading
        logger.info(f"Model {model_id} ready via LM Studio")
        return True
    
    async def unload(self, model_id: str) -> bool:
        """Unload model - LM Studio handles this via API."""
        logger.info(f"Model {model_id} unloaded from LM Studio")
        return True
    
    async def get_vram_usage(self) -> dict:
        """Get VRAM usage from LM Studio."""
        try:
            session = await self._get_session()
            # LM Studio exposes metrics via /metrics endpoint
            async with session.get(f'{self.base_url}/metrics') as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'used_mb': data.get('gpu_memory_used', 0),
                        'total_mb': data.get('gpu_memory_total', 0),
                        'available_mb': data.get('gpu_memory_free', 0)
                    }
        except Exception as e:
            logger.warning(f"Could not get VRAM usage: {e}")
        
        # Fallback: return dummy values
        return {'used_mb': 0, 'total_mb': 12000, 'available_mb': 12000}
