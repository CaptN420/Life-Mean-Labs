"""
Debate State - Central structured memory for the debate.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DebateState:
    """
    Central structured memory for the debate.
    
    This is the source of truth - never rebuild state from raw history.
    """
    
    # Core fields
    debate_id: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    objective: str = ""
    request: str = ""
    
    # Participants and agents
    current_agent: Optional[str] = None
    previous_agent: Optional[str] = None
    allowed_actions: List[str] = field(default_factory=list)
    
    # Turn tracking
    turn_number: int = 0
    max_turns: int = 20
    
    # Debate content - structured memory
    positions: Dict[str, str] = field(default_factory=dict)
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    objections: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    unresolved_points: List[str] = field(default_factory=list)
    
    # Consensus and loop detection
    consensus_reached: bool = False
    consensus_confidence: float = 0.0
    loop_detected: bool = False
    
    # Progress tracking
    progress_score: float = 0.0
    difficulty_score: float = 0.0
    conflict_score: float = 0.0
    
    # Escalation
    escalation_level: int = 0
    
    # Memory pipeline
    recent_turns: List[Dict[str, Any]] = field(default_factory=list)
    selected_memories: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_turn(self, agent_id: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Add a turn to the debate state."""
        self.recent_turns.append({
            'agent_id': agent_id,
            'content': content,
            'turn_number': self.turn_number,
            'timestamp': datetime.utcnow().isoformat()
        })
        self.turn_number += 1
        self.updated_at = datetime.utcnow()
        
        # Keep only last N turns in recent
        if len(self.recent_turns) > 10:
            self.recent_turns = self.recent_turns[-10:]
    
    def update_progress(self, progress: float) -> None:
        """Update debate progress score."""
        self.progress_score = max(0.0, min(1.0, progress))
        self.updated_at = datetime.utcnow()
    
    def detect_loop(self) -> bool:
        """Check if the debate is looping."""
        if len(self.recent_turns) < 4:
            return False
        
        # Check for repeating agent patterns
        agents = [t['agent_id'] for t in self.recent_turns[-6:]]
        if len(set(agents)) == 2 and agents[0] != agents[-1]:
            self.loop_detected = True
            return True
        
        # Check for content repetition
        contents = [t['content'][:50].lower() for t in self.recent_turns[-4:]]
        if len(set(contents)) < 2:
            self.loop_detected = True
            return True
        
        return False
    
    def to_dict(self) -> dict:
        """Serialize state to dictionary."""
        return {
            'debate_id': self.debate_id,
            'objective': self.objective,
            'turn_number': self.turn_number,
            'max_turns': self.max_turns,
            'current_agent': self.current_agent,
            'previous_agent': self.previous_agent,
            'allowed_actions': self.allowed_actions,
            'positions': self.positions,
            'arguments': self.arguments,
            'objections': self.objections,
            'contradictions': self.contradictions,
            'unresolved_points': self.unresolved_points,
            'consensus_reached': self.consensus_reached,
            'consensus_confidence': self.consensus_confidence,
            'loop_detected': self.loop_detected,
            'progress_score': self.progress_score,
            'difficulty_score': self.difficulty_score,
            'conflict_score': self.conflict_score,
            'escalation_level': self.escalation_level,
            'recent_turns': self.recent_turns,
            'selected_memories': self.selected_memories,
            'metadata': self.metadata
        }
