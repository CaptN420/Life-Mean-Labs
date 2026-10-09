"""
Judge Agent - Evaluates and synthesizes the debate.
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class JudgeAgent(BaseAgent):
    """
    Agent Judge - Arbitrage et synthèse
    
    Intervient lorsque:
    - loop_detected == true
    - consensus_possible == true
    - conflict_score > threshold
    - turn_number >= max_turns
    - escalation_level >= judge_threshold
    """
    
    def __init__(self, agent_id: str = "judge", **kwargs):
        super().__init__(agent_id, AgentRole.JUDGE, kwargs)
    
    def _get_system_prompt(self) -> str:
        return """You are the Judge in a philosophical debate.
Your role is to evaluate arguments, identify strengths and weaknesses, 
and synthesize conclusions.

You must:
- Compare positions objectively
- Identify the strongest arguments
- Distinguish factual disagreements from philosophical ones
- Produce a synthesis of the debate
- Determine if escalation is necessary

Be fair, balanced, and thorough.
"""
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate a judgment/synthesis."""
        turn_number = debate_context.get('turn_number', 0) + 1
        
        positions = debate_context.get('positions', {})
        arguments = debate_context.get('arguments', [])
        
        synthesis = f"""[Judge Synthesis]
Debate on: {debate_context.get('objective', 'unknown')}
Turns completed: {turn_number}

Key Positions:
{chr(10).join(f'- {k}: {v[:100]}...' for k, v in positions.items())}

Strongest Arguments Identified:
{chr(10).join(f'{i+1}. {a.get("content", "N/A")[:150]}' for i, a in enumerate(arguments[-5:]))}

Recommendation: Continue debate or reach conclusion based on progress.
"""
        
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=synthesis,
            turn_number=turn_number,
            metadata={
                'agent_type': 'judge',
                'model': 'judge'
            }
        )
