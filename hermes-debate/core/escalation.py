"""
Escalation logic for Hermes Multi-Agent Debate Orchestrator.
Manages escalation between different model levels.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class EscalationManager:
    """
    Manages debate escalation based on difficulty and conflict.
    
    Levels:
    0: Agents 4B (Qwen, Gemma)
    1: Judge
    2: Bonsai 27B
    3: Savant Commander
    """
    
    def __init__(
        self,
        judge_threshold: float = 0.45,
        bonsai_threshold: float = 0.70,
        savant_threshold: float = 0.90
    ):
        self.judge_threshold = judge_threshold
        self.bonsai_threshold = bonsai_threshold
        self.savant_threshold = savant_threshold
    
    def should_escalate(
        self,
        difficulty_score: float,
        conflict_score: float,
        loop_detected: bool,
        current_level: int = 0
    ) -> int:
        """
        Determine if escalation is needed and to what level.
        
        Returns:
            New escalation level (0-3)
        """
        # Check if we should escalate
        if loop_detected and current_level < 1:
            return 1
        
        if difficulty_score >= self.savant_threshold and current_level < 3:
            return 3
        elif difficulty_score >= self.bonsai_threshold and current_level < 2:
            return 2
        elif conflict_score >= self.judge_threshold and current_level < 1:
            return 1
        
        # Check if we can de-escalate
        if difficulty_score < self.judge_threshold * 0.5 and current_level > 0:
            return 0
        
        return current_level
    
    def get_agent_for_level(self, level: int) -> str:
        """Get the agent name for an escalation level."""
        agents = {
            0: "RationalAgent",
            1: "JudgeAgent",
            2: "BonsaiAgent",
            3: "SavantAgent"
        }
        return agents.get(level, "RationalAgent")
    
    def should_call_judge(self, state: Dict[str, Any]) -> bool:
        """Check if Judge should be called."""
        return (
            state.get('loop_detected', False) or
            state.get('consensus_reached', False) or
            state.get('conflict_score', 0.0) >= self.judge_threshold or
            state.get('turn_number', 0) >= state.get('max_turns', 20)
        )
