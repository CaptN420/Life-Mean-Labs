"""
Routing logic for Hermes Multi-Agent Debate Orchestrator.
Determines which agent to call next based on debate state.
"""

import logging
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class Action(str, Enum):
    """Allowed actions in the debate."""
    RATIONAL = "RationalAgent"
    COUNTER_POSITION = "CounterPositionAgent"
    JUDGE = "JudgeAgent"
    BONSAI = "BonsaiAgent"
    SAVANT = "SavantAgent"
    END = "END"


class Router:
    """
    Routes debate flow by selecting the next agent.
    
    Uses Clef decision or deterministic fallback.
    """
    
    def __init__(self, allowed_actions: Optional[List[str]] = None):
        self.allowed_actions = allowed_actions or [
            Action.RATIONAL.value,
            Action.COUNTER_POSITION.value,
            Action.JUDGE.value,
        ]
        self._previous_action: Optional[str] = None
    
    def select_next_agent(
        self,
        debate_state: Dict[str, Any],
        clef_decision: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Select the next agent to call.
        
        Args:
            debate_state: Current debate state
            clef_decision: Decision from Clef (optional)
        
        Returns:
            Agent name to call
        """
        # If Clef made a decision, validate and use it
        if clef_decision:
            selected = clef_decision.get('next_agent', '')
            if selected in self.allowed_actions:
                logger.info(f"CLEF selected: {selected}")
                self._previous_action = selected
                return selected
        
        # Deterministic fallback
        agent = self._deterministic_select(debate_state)
        logger.info(f"DETERMINISTIC fallback: {agent}")
        self._previous_action = agent
        return agent
    
    def _deterministic_select(self, state: Dict[str, Any]) -> str:
        """Select next agent using deterministic rules."""
        turn_number = state.get('turn_number', 0)
        max_turns = state.get('max_turns', 20)
        loop_detected = state.get('loop_detected', False)
        consensus_reached = state.get('consensus_reached', False)
        escalation_level = state.get('escalation_level', 0)
        
        # End conditions
        if consensus_reached or turn_number >= max_turns:
            return Action.END.value
        
        # Loop detected - call Judge
        if loop_detected:
            return Action.JUDGE.value
        
        # Escalation levels
        if escalation_level >= 3:
            return Action.SAVANT.value
        elif escalation_level >= 2:
            return Action.BONSAI.value
        
        # Alternate between rational and counter-position
        previous = state.get('current_agent', '')
        if previous == Action.RATIONAL.value:
            return Action.COUNTER_POSITION.value
        elif previous == Action.COUNTER_POSITION.value:
            return Action.RATIONAL.value
        
        # Default to rational
        return Action.RATIONAL.value
    
    def validate_action(self, action: str) -> bool:
        """Validate that an action is allowed."""
        return action in self.allowed_actions or action == Action.END.value
    
    def get_allowed_actions(self) -> List[str]:
        """Get list of allowed actions."""
        return self.allowed_actions.copy()
