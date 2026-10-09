"""
Bonsai 27B - Deep Reasoning / Escalation Agent
Used when smaller models fail or complex reasoning required.
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class BonsaiAgent(BaseAgent):
    """
    Bonsai 27B - Deep Reasoning / Escalation
    
    Intervient lorsque:
    - Petits modèles fortement en désaccord
    - Problème difficile (difficulty_score > 0.7)
    - Boucle persistante
    - Judge incertain
    - Complexité élevée
    """
    
    def __init__(self, agent_id: str = "bonsai_27b", **kwargs):
        super().__init__(agent_id, AgentRole.PHILOSOPHER, kwargs)
    
    def _get_system_prompt(self) -> str:
        return """You are Bonsai 27B, a deep reasoning model operating at the highest level.
You are called when simpler models cannot resolve a complex philosophical problem.

Your role:
- Perform deep, multi-layered analysis
- Synthesize multiple perspectives
- Identify subtle logical structures
- Provide comprehensive resolution attempts

You receive a condensed, clean context - no raw history dumps.
Focus on the core issue and provide your best reasoning.
"""
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate deep reasoning response."""
        turn_number = debate_context.get('turn_number', 0) + 1
        
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"[Bonsai Deep Reasoning] Analyzing complex problem: {prompt[:200]}...",
            turn_number=turn_number,
            metadata={
                'agent_type': 'bonsai',
                'model': 'bonsai_27b',
                'escalation_level': 2
            }
        )
