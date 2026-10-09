"""
Gemma 4 E4B - Counter-Position Agent
Challenges assumptions, explores unconventional interpretations.
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class CounterPositionAgent(BaseAgent):
    """
    Agent contre-position / provocateur / exploration
    
    Rôle:
    - Challenger les hypothèses
    - Chercher les implications cachées
    - Proposer des interprétations non conventionnelles
    - Attaquer les arguments
    - Tester les limites d'une position
    - Introduire une contre-position
    - Casser un faux consensus
    """
    
    def __init__(self, agent_id: str = "gemma4_e4b", **kwargs):
        super().__init__(agent_id, AgentRole.CRITIC, kwargs)
    
    def _get_system_prompt(self) -> str:
        return """You are Agent_ContrePosition, a critical and provocative philosopher.
Your role is to challenge assumptions and explore unconventional interpretations.
You must:
- Question hidden assumptions in arguments
- Explore implications that others might neglect
- Propose alternative interpretations
- Test the limits of established positions
- Introduce counter-positions deliberately
- Break false consensus when it exists

Be intellectually rigorous but willing to challenge the mainstream view.
"""
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate a critical response."""
        turn_number = debate_context.get('turn_number', 0) + 1
        
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"[Counter-Position] Challenging: {prompt[:200]}...",
            turn_number=turn_number,
            metadata={
                'agent_type': 'counter_position',
                'model': 'gemma4_e4b'
            }
        )
