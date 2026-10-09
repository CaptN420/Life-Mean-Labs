"""
Base agent abstraction for debate participants.
"""

from abc import ABC, abstractmethod
import logging
from typing import Optional
from datetime import datetime

from ..models.state import AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all debate agents."""
    
    def __init__(self, agent_id: str, role: AgentRole, config: dict):
        self.agent_id = agent_id
        self.role = role
        self.config = config
    
    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        debate_context: dict,
        **kwargs
    ) -> AgentResponse:
        """Generate a response to a prompt."""
        ...
    
    async def format_prompt(self, objective: str, state: dict) -> list[dict]:
        """Format the prompt for this agent."""
        system_prompt = self._get_system_prompt()
        
        user_prompt = f"""
Objective: {objective}

Current Debate State:
- Turn: {state.get('turn_number', 0)}
- Current Agent: {state.get('current_agent', 'N/A')}
- Previous Agent: {state.get('previous_agent', 'N/A')}

Recent Turns:
{self._format_recent_turns(state.get('recent_turns', []))}

Structured Memory:
Positions: {state.get('positions', {})}
Arguments: {state.get('arguments', [])}
Objections: {state.get('objections', [])}
Unresolved Points: {state.get('unresolved_points', [])}
Contradictions: {state.get('contradictions', [])}

Your task is to continue the debate from your perspective as a {self.role.value}.
"""
        
        return [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt.strip()}
        ]
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for this agent."""
        return f"""You are a {self.role.value} in a philosophical debate.
Your goal is to provide deep, thoughtful analysis and reasoning.
Be precise, logical, and engage with the arguments presented.
"""
    
    def _format_recent_turns(self, turns: list[dict]) -> str:
        """Format recent turns for context."""
        if not turns:
            return "No recent turns."
        
        lines = []
        for turn in turns[-5:]:
            agent = turn.get('agent_id', 'Unknown')
            content = turn.get('content', '')[:200]
            lines.append(f"- {agent}: {content}...")
        
        return "\n".join(lines)


class ReasoningAgent(BaseAgent):
    """Agent that performs deep reasoning."""
    
    def __init__(self, agent_id: str, role: AgentRole = AgentRole.PHILOSOPHER, **kwargs):
        super().__init__(agent_id, role, kwargs)
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate a reasoned response."""
        # In production, this would call the actual model
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"Simulated reasoning from {self.agent_id}: {prompt[:100]}...",
            turn_number=debate_context.get('turn_number', 0) + 1
        )


class CriticAgent(BaseAgent):
    """Agent that critiques and challenges arguments."""
    
    def __init__(self, agent_id: str = "critic", role: AgentRole = AgentRole.CRITIC, **kwargs):
        super().__init__(agent_id, role, kwargs)
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate a critical response."""
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"Simulated critique from {self.agent_id}: Analyzing the argument about '{prompt[:50]}...'...",
            turn_number=debate_context.get('turn_number', 0) + 1
        )


class JudgeAgent(BaseAgent):
    """Agent that evaluates and synthesizes the debate."""
    
    def __init__(self, agent_id: str = "judge", role: AgentRole = AgentRole.JUDGE, **kwargs):
        super().__init__(agent_id, role, kwargs)
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate a judgment/synthesis."""
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"Simulated judgment from {self.agent_id}: Synthesizing the debate on '{prompt[:50]}...'...",
            turn_number=debate_context.get('turn_number', 0) + 1
        )
