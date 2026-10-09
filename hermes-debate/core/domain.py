"""
Experiment Domain Model.

Defines the core entities for experimental design:
- Question
- Persona
- Role
- Model
- Protocol
- Experiment
- Run
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class PersonaType(str, Enum):
    """Types of personas available in the system."""
    
    # Core personas (selected by default)
    ANALYTICAL_PHILOSOPHER = "analytical_philosopher"
    ETHICAL_PHILOSOPHER = "ethical_philosopher"
    SKEPTIC = "skeptic"
    ADVOCATE = "advocate"
    SCIENTIST = "scientist"
    PRAGMATIST = "pragmatist"
    
    # Optional personas (not selected by default)
    CONTRARIAN = "contrarian"
    HUMANIST = "humanist"
    FUTURIST = "futurist"
    OPTIMIST = "optimist"
    PESSIMIST_RISK_ANALYST = "pessimist_risk_analyst"
    MEDIATOR = "mediator"
    NEUTRAL_JUDGE = "neutral_judge"
    INTERDISCIPLINARY_RESEARCHER = "interdisciplinary_researcher"


class RoleType(str, Enum):
    """Types of roles agents can take during debate."""
    
    ADVOCATE = "advocate"
    CRITIC = "critic"
    SKEPTIC = "skeptic"
    QUESTIONER = "questioner"
    CROSS_EXAMINER = "cross_examiner"
    RESEARCHER = "researcher"
    SYNTHESIZER = "synthesizer"
    JUDGE = "judge"
    MODERATOR = "moderator"
    DEVILS_ADVOCATE = "devils_advocate"
    FINAL_EVALUATOR = "final_evaluator"


class ProtocolType(str, Enum):
    """Types of debate protocols."""
    
    FREE_DEBATE = "free_debate"
    STRUCTURED_DEBATE = "structured_debate"
    OXFORD_STYLE = "oxford_style"
    SOCRATIC = "socratic"
    CROSS_EXAMINATION = "cross_examination"
    MULTI_ROUND_DEBATE = "multi_round_debate"
    DEBATE_WITH_JUDGE = "debate_with_judge"
    DEBATE_WITH_SYNTHESIS = "debate_with_synthesis"
    CUSTOM = "custom_protocol"


class ModelType(str, Enum):
    """Types of models."""
    
    GENERATIVE = "generative"
    DECISION = "decision_model"


@dataclass
class Question:
    """A research question or debate topic."""
    
    id: str
    text: str
    version: str = "1.0"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'text': self.text,
            'version': self.version,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
        }


@dataclass
class Persona:
    """A perspective or identity in the debate."""
    
    id: str
    name: str
    persona_type: PersonaType
    description: str
    prompt_template: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    version: str = "1.0"
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.persona_type.value,
            'description': self.description,
            'version': self.version,
        }


@dataclass
class Role:
    """A role that an agent takes during a specific phase."""
    
    id: str
    name: str
    role_type: RoleType
    description: str
    metadata: dict = field(default_factory=dict)
    version: str = "1.0"
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.role_type.value,
            'description': self.description,
            'version': self.version,
        }


@dataclass
class ModelConfig:
    """Configuration for a model."""
    
    id: str
    name: str
    model_type: ModelType
    provider: str  # "lm_studio", "openai", "mock", etc.
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    parameters: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    version: str = "1.0"
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.model_type.value,
            'provider': self.provider,
            'endpoint': self.endpoint,
            'parameters': self.parameters,
            'version': self.version,
        }


@dataclass
class Protocol:
    """A debate protocol defining the flow."""
    
    id: str
    name: str
    protocol_type: ProtocolType
    description: str
    phases: list[dict]  # List of phase definitions
    metadata: dict = field(default_factory=dict)
    version: str = "1.0"
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.protocol_type.value,
            'description': self.description,
            'phases': self.phases,
            'version': self.version,
        }


@dataclass
class Experiment:
    """
    An experimental configuration.
    
    Immutable scientific entity that defines what will be tested.
    """
    
    id: str
    question_id: str
    personas: list[str]  # Persona IDs
    roles: list[str]  # Role IDs
    model_pool: list[str]  # Model IDs available for assignment
    protocol_id: str
    orchestrator_id: str
    decision_model_id: Optional[str] = None
    repetitions: int = 5
    max_turns: int = 8
    constraints: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'question_id': self.question_id,
            'personas': self.personas,
            'roles': self.roles,
            'model_pool': self.model_pool,
            'protocol_id': self.protocol_id,
            'orchestrator_id': self.orchestrator_id,
            'decision_model_id': self.decision_model_id,
            'repetitions': self.repetitions,
            'max_turns': self.max_turns,
            'constraints': self.constraints,
            'version': self.version,
            'created_at': self.created_at.isoformat(),
        }


@dataclass
class Run:
    """
    A single execution of an Experiment.
    
    Immutable record of what happened during execution.
    """
    
    id: str
    experiment_id: str
    run_number: int
    status: str  # "running", "completed", "failed", "paused"
    transcript: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    raw_artifact_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'experiment_id': self.experiment_id,
            'run_number': self.run_number,
            'status': self.status,
            'transcript_length': len(self.transcript),
            'metrics': self.metrics,
            'errors': self.errors,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class AssignmentStrategy(ABC):
    """
    Abstract base class for assignment strategies.
    
    Assignment strategies determine how models are assigned to personas and roles.
    """
    
    @abstractmethod
    async def assign(
        self,
        persona: str,
        role: str,
        phase: str,
        candidates: list[str],
        context: dict,
    ) -> dict:
        """
        Assign a model to a persona/role combination.
        
        Args:
            persona: Persona ID
            role: Role ID
            phase: Current debate phase
            candidates: Available model IDs
            context: Additional context (debate state, history, etc.)
            
        Returns:
            Assignment result with selected model and metadata
        """
        ...


@dataclass
class AssignmentResult:
    """Result of an assignment decision."""
    
    persona: str
    role: str
    phase: str
    selected_model: str
    strategy: str
    confidence: float
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'persona': self.persona,
            'role': self.role,
            'phase': self.phase,
            'selected_model': self.selected_model,
            'strategy': self.strategy,
            'confidence': self.confidence,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat(),
        }


class FixedAssignment(AssignmentStrategy):
    """Fixed assignment: persona always uses the same model."""
    
    def __init__(self, mapping: dict[str, str]):
        """
        Initialize with a fixed mapping.
        
        Args:
            mapping: Dict mapping persona_id -> model_id
        """
        self.mapping = mapping
    
    async def assign(
        self,
        persona: str,
        role: str,
        phase: str,
        candidates: list[str],
        context: dict,
    ) -> AssignmentResult:
        """Return the fixed model for this persona."""
        model_id = self.mapping.get(persona, candidates[0] if candidates else "default")
        
        return AssignmentResult(
            persona=persona,
            role=role,
            phase=phase,
            selected_model=model_id,
            strategy="fixed",
            confidence=1.0,
        )


class RandomAssignment(AssignmentStrategy):
    """Random assignment: randomly select from candidates."""
    
    def __init__(self, seed: Optional[int] = None):
        import random
        self.rng = random.Random(seed)
    
    async def assign(
        self,
        persona: str,
        role: str,
        phase: str,
        candidates: list[str],
        context: dict,
    ) -> AssignmentResult:
        """Return a randomly selected model."""
        if not candidates:
            raise ValueError("No candidates available for random assignment")
        
        selected = self.rng.choice(candidates)
        
        return AssignmentResult(
            persona=persona,
            role=role,
            phase=phase,
            selected_model=selected,
            strategy="random",
            confidence=0.5,
        )


class RoundRobinAssignment(AssignmentStrategy):
    """Round-robin assignment: cycle through candidates."""
    
    def __init__(self):
        self._counters: dict[str, int] = {}
    
    async def assign(
        self,
        persona: str,
        role: str,
        phase: str,
        candidates: list[str],
        context: dict,
    ) -> AssignmentResult:
        """Return the next model in round-robin order."""
        if not candidates:
            raise ValueError("No candidates available for round-robin assignment")
        
        key = f"{persona}:{role}:{phase}"
        self._counters[key] = self._counters.get(key, 0)
        
        selected = candidates[self._counters[key] % len(candidates)]
        self._counters[key] += 1
        
        return AssignmentResult(
            persona=persona,
            role=role,
            phase=phase,
            selected_model=selected,
            strategy="round_robin",
            confidence=0.7,
        )
