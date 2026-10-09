"""
Strands Decider 2B Decision Model.

Specialized adapter for Strands Decider 2B via LM Studio.
Configurable and framework-agnostic.
"""

import logging
from typing import Any, Optional

from .lmstudio import LMStudioDecisionModel

logger = logging.getLogger(__name__)


class StrandsDecider2B(LMStudioDecisionModel):
    """
    Decision model adapter for Strands Decider 2B.
    
    Strands Decider 2B is a specialized decision model designed for:
    - Agent routing in multi-agent systems
    - Structured option selection
    - High-confidence decision making
    
    This adapter communicates with Strands Decider 2B via LM Studio.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout_seconds: int = 60,
    ):
        """
        Initialize Strands Decider 2B adapter.
        
        Args:
            base_url: LM Studio API endpoint
            model_id: Model identifier (optional — will be discovered from LM Studio)
            api_key: API key if required
            temperature: Generation temperature (default 0.0 for decisions)
            max_tokens: Maximum tokens for response
            timeout_seconds: Request timeout
        """
        super().__init__(
            base_url=base_url,
            model_id=model_id,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        
        self._model_name = "strands-decider-2b"
        self._capabilities = [
            "routing",
            "classification",
            "tool_selection",
            "agent_selection",
        ]
    
    async def get_model_info(self) -> dict[str, Any]:
        """Get Strands Decider 2B specific metadata."""
        info = await super().get_model_info()
        info.update({
            'id': self._model_name,
            'type': 'decision_model',
            'provider': 'lm_studio',
            'version': '2.0',
            'capabilities': self._capabilities,
            'is_local': True,
            'description': 'Strands Decider 2B - Specialized decision model for multi-agent routing',
        })
        return info
    
    def _build_decision_prompt(self, options: list[str], context: dict) -> str:
        """Build Strands Decider 2B specific prompt."""
        base_prompt = super()._build_decision_prompt(options, context)
        
        # Add Strands-specific instructions
        strands_instructions = """
Strands Decider 2B Instructions:
- You are a specialized decision model for multi-agent systems
- Analyze the debate state carefully
- Consider agent history, current turn, and consensus status
- Select the option that maximizes debate progress
- Return confidence score based on certainty of selection
"""
        
        return f"{base_prompt}\n\n{strands_instructions}"
