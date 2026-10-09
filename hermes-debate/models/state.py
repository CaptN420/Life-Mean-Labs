"""
Core data structures for the Hermes Multi-Agent Debate Orchestrator.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Action(str, Enum):
    """Allowed actions in the debate."""
    MODEL_A = "MODEL_A"
    MODEL_B = "MODEL_B"
    JUDGE = "JUDGE"
    SYNTHESIZE = "SYNTHESIZE"
    FACT_CHECK = "FACT_CHECK"
    END = "END"


class ModelStatus(str, Enum):
    """Lifecycle states for models."""
    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    READY = "READY"
    RUNNING = "RUNNING"
    UNLOADING = "UNLOADING"
    ERROR = "ERROR"


class AgentRole(str, Enum):
    """Roles for debate agents."""
    PHILOSOPHER = "philosopher"
    CRITIC = "critic"
    JUDGE = "judge"
    DECISION_MODEL = "decision_model"


@dataclass
class Decision:
    """Structured decision from Clef or internal logic."""
    next_action: Action
    confidence: float
    consensus_reached: bool = False
    loop_detected: bool = False
    needs_fact_check: bool = False
    debate_progress: float = 0.0
    reason: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Decision':
        """Parse decision from dictionary."""
        try:
            action = Action(data.get('next_action', 'END'))
        except ValueError:
            action = Action.END
        
        return cls(
            next_action=action,
            confidence=float(data.get('confidence', 0.0)),
            consensus_reached=bool(data.get('consensus_reached', False)),
            loop_detected=bool(data.get('loop_detected', False)),
            needs_fact_check=bool(data.get('needs_fact_check', False)),
            debate_progress=float(data.get('debate_progress', 0.0)),
            reason=data.get('reason', '')
        )


@dataclass
class AgentResponse:
    """Response from a reasoning agent."""
    agent_id: str
    role: AgentRole
    content: str
    turn_number: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class DebateState:
    """Central structured memory for the debate."""

    # Core fields
    request: str = ""
    objective: str = ""
    debate_id: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Participants and agents
    participants: list[str] = field(default_factory=list)
    available_agents: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    current_agent: Optional[str] = None
    previous_agent: Optional[str] = None

    # Turn tracking
    turn_number: int = 0
    max_turns: int = 8

    # Debate content - structured memory
    positions: dict[str, str] = field(default_factory=dict)
    arguments: list[dict] = field(default_factory=list)
    counterarguments: list[dict] = field(default_factory=list)
    objections: list[dict] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    unresolved_points: list[str] = field(default_factory=list)

    # Consensus and loop detection
    consensus: bool = False
    consensus_confidence: float = 0.0
    loop_detected: bool = False
    judge_requested: bool = False

    # Progress tracking
    debate_progress: float = 0.0
    progress_score: float = 0.0

    # Clef decision context
    clef_decision: Optional[dict] = None
    clef_confidence: float = 0.0

    # Memory pipeline
    recent_turns: list[AgentResponse] = field(default_factory=list)
    historical_turns: list[AgentResponse] = field(default_factory=list)
    historical_summary: str = ""
    selected_memory: Optional[list[dict]] = None

    # Flags
    fact_check_required: bool = False
    final_answer_ready: bool = False

    # Metadata
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_turn(self, response: AgentResponse) -> None:
        """Add a turn to the debate state."""
        self.recent_turns.append(response)
        self.turn_number += 1
        self.updated_at = datetime.utcnow()

        # Move older turns to historical when buffer gets full
        if len(self.recent_turns) > 10:
            older = self.recent_turns[:-5]
            self.historical_turns.extend(older)
            self.recent_turns = self.recent_turns[-5:]
            # Build compressed summary of historical turns
            summary_parts = []
            for t in older:
                summary_parts.append(f"[Turn {t.turn_number}] {t.role.value}: {t.content[:200]}")
            if summary_parts:
                self.historical_summary = "\n".join(summary_parts)

    def update_progress(self, progress: float) -> None:
        """Update debate progress."""
        self.debate_progress = max(0.0, min(1.0, progress))
        self.progress_score = self.debate_progress
        self.updated_at = datetime.utcnow()

    def detect_loop(self) -> bool:
        """Check if the debate is looping."""
        if len(self.recent_turns) < 4:
            return False

        # Check for repeating agent patterns (alternating A,B,A,B...)
        agents = [t.agent_id for t in self.recent_turns[-6:]]
        if len(set(agents)) == 2 and agents[0] != agents[-1]:
            self.loop_detected = True
            return True

        # Check for content repetition
        contents = [t.content.lower()[:50] for t in self.recent_turns[-4:]]
        if len(set(contents)) < 2:
            self.loop_detected = True
            return True

        return False

    def to_dict(self) -> dict:
        """Serialize state to dictionary."""
        return {
            'debate_id': self.debate_id,
            'request': self.request,
            'objective': self.objective,
            'turn_number': self.turn_number,
            'max_turns': self.max_turns,
            'current_agent': self.current_agent,
            'previous_agent': self.previous_agent,
            'positions': self.positions,
            'arguments': self.arguments,
            'objections': self.objections,
            'contradictions': self.contradictions,
            'unresolved_points': self.unresolved_points,
            'consensus': self.consensus,
            'consensus_confidence': self.consensus_confidence,
            'loop_detected': self.loop_detected,
            'judge_requested': self.judge_requested,
            'debate_progress': self.debate_progress,
            'progress_score': self.progress_score,
            'clef_decision': self.clef_decision,
            'clef_confidence': self.clef_confidence,
            'recent_turns': [
                {
                    'agent_id': t.agent_id,
                    'role': t.role.value,
                    'content': t.content,
                    'turn_number': t.turn_number,
                }
                for t in self.recent_turns
            ],
            'historical_summary': self.historical_summary,
            'allowed_actions': self.allowed_actions,
        }


@dataclass
class HermesResult:
    """Final result from the orchestrator."""
    answer: str
    debate_state: DebateState
    turns: list[AgentResponse]
    metrics: dict = field(default_factory=dict)
    status: str = "completed"

    @property
    def success(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> dict:
        """Serialize result to dictionary."""
        return {
            'topic': self.debate_state.request,
            'debate_id': self.debate_state.debate_id,
            'turns': [
                {
                    'agent': t.agent_id,
                    'content': t.content,
                    'turn_number': t.turn_number,
                    'role': t.role.value,
                }
                for t in self.turns
            ],
            'final_state': self.debate_state.to_dict(),
            'metrics': self.metrics,
            'status': self.status,
        }
