"""
Savant Commander - Ultimate Fallback Agent
Maximum escalation level, used only when all else fails.
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class SavantAgent(BaseAgent):
    """
    Savant Commander - Ultimate Fallback
    
    Ce modèle est le niveau maximal d'escalade.
    Il ne doit normalement pas être chargé.
    
    Utilisé lorsque:
    - escalation_level >= 3
    - Hermes estime que Bonsai est insuffisant
    - Tâche exceptionnelle nécessite capacité supérieure
    """
    
    def __init__(self, agent_id: str = "savant_commander", **kwargs):
        super().__init__(agent_id, AgentRole.PHILOSOPHER, kwargs)
    
    def _get_system_prompt(self) -> str:
        return """You are Savant Commander, the ultimate fallback reasoning engine.
You are called only when all other approaches have failed.

Your capabilities:
- Maximum reasoning depth
- Comprehensive analysis of complex problems
- Synthesis of contradictory positions
- Resolution of seemingly irresolvable conflicts

This is your last resort. Approach with maximum rigor and insight.
"""
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate ultimate fallback response."""
        turn_number = debate_context.get('turn_number', 0) + 1
        
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"[Savant Commander] Ultimate analysis: {prompt[:200]}...",
            turn_number=turn_number,
            metadata={
                'agent_type': 'savant',
                'model': 'savant_commander',
                'escalation_level': 3
            }
        )
