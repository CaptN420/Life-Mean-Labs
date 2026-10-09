"""
Loop detector for identifying repetitive debate patterns.
"""

import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LoopDetector:
    """Detects when a debate is looping without progress."""
    
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
    
    def detect_loop(self, debate_state) -> bool:
        """
        Check if the debate is currently looping.

        Args:
            debate_state: Current DebateState object

        Returns:
            True if loop detected, False otherwise
        """
        recent_turns = debate_state.recent_turns

        if len(recent_turns) < self.threshold * 2:
            return False

        # Check for repeating agent patterns
        agents = [t.agent_id for t in recent_turns[-self.threshold * 2:]]

        # Pattern: A -> B -> A -> B (alternating without progress)
        if len(set(agents)) <= 2 and agents[0] != agents[-1]:
            logger.warning(f"Loop detected: agents {set(agents)} repeating")
            return True
        
        # Check for similar content repetition
        contents = [t.content.lower()[:50] for t in recent_turns[-self.threshold * 2:]]
        if len(set(contents)) < self.threshold:
            logger.warning("Loop detected: similar content repeating")
            return True
        
        return False
    
    def get_loop_type(self, debate_state) -> Optional[str]:
        """Get the type of loop detected."""
        recent_turns = debate_state.recent_turns
        
        if len(recent_turns) < 4:
            return None
        
        agents = [t.agent_id for t in recent_turns[-6:]]
        
        # Check alternating pattern
        if len(set(agents)) == 2 and agents[0] == agents[-1]:
            return "alternating"
        
        # Check content repetition
        contents = [t.content.lower()[:50] for t in recent_turns[-6:]]
        if len(set(contents)) < 3:
            return "content_repetition"
        
        return None
