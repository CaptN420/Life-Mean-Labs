"""
Consensus detector for identifying when philosophers agree.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ConsensusDetector:
    """Detects consensus among debate participants."""
    
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
    
    def detect_consensus(self, debate_state) -> dict:
        """
        Detect if consensus has been reached.
        
        Args:
            debate_state: Current DebateState object
            
        Returns:
            Dictionary with consensus information
        """
        recent_turns = debate_state.recent_turns
        
        if len(recent_turns) < 2:
            return {
                'consensus_reached': False,
                'confidence': 0.0,
                'reason': 'Insufficient turns'
            }
        
        # Check for agreement patterns
        positions = debate_state.positions
        
        # If both agents have similar positions, likely consensus
        if len(positions) >= 2:
            pos_values = list(positions.values())
            if len(set(pos_values)) == 1:
                return {
                    'consensus_reached': True,
                    'confidence': 0.95,
                    'reason': 'Identical positions expressed'
                }
        
        # Check recent turns for agreement language
        agreement_keywords = ['agree', 'concur', 'accept', 'valid point', 'correct']
        disagreement_keywords = ['disagree', 'however', 'but', 'contrary', 'false']
        
        agreement_count = 0
        disagreement_count = 0
        
        for turn in recent_turns[-4:]:
            content = turn.content.lower()
            if any(kw in content for kw in agreement_keywords):
                agreement_count += 1
            elif any(kw in content for kw in disagreement_keywords):
                disagreement_count += 1
        
        total_signals = agreement_count + disagreement_count
        if total_signals > 0:
            consensus_ratio = agreement_count / total_signals
            if consensus_ratio >= self.threshold:
                return {
                    'consensus_reached': True,
                    'confidence': consensus_ratio,
                    'reason': 'High agreement ratio in recent turns'
                }
        
        return {
            'consensus_reached': False,
            'confidence': 0.0,
            'reason': 'No clear consensus detected'
        }
