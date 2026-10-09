"""
Qwen3.5 4B - Rational Agent
Performs logical reasoning, analysis, and argumentation.
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class RationalAgent(BaseAgent):
    """
    Agent rationnel / analytique
    
    Responsabilités:
    - Raisonnement logique
    - Analyse et détection de contradictions
    - Argumentation et contre-argumentation
    - Analyse factuelle
    - Résolution de problèmes
    """
    
    def __init__(self, agent_id: str = "qwen35_4b", **kwargs):
        super().__init__(agent_id, AgentRole.PHILOSOPHER, kwargs)
    
    def _get_system_prompt(self) -> str:
        return """You are Agent_Rationnel, a rational and analytical philosopher.
Your role is to provide deep, logical analysis of arguments.
You must:
- Analyze the logical structure of arguments
- Identify hidden assumptions and biases
- Detect contradictions and fallacies
- Provide counter-arguments when appropriate
- Maintain intellectual honesty and precision

Do not repeat arguments already established.
Identify new insights and implications.
"""
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate a reasoned response."""
        turn_number = debate_context.get('turn_number', 0) + 1
        
        # In production, this would call Qwen3.5 4B via the backend
        # For now, return simulated response
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"[Rational Analysis] Analyzing: {prompt[:200]}...",
            turn_number=turn_number,
            metadata={
                'agent_type': 'rational',
                'model': 'qwen35_4b'
            }
        )
