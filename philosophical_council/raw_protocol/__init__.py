"""RAW Debate Data Protocol for Life_mean Lab.

This module implements the RAW DEBATE DATA PROTOCOL for recording
complete debate experiments for future ML training (SFT, DPO, reward
models, router training, etc.).

The RAW data must NEVER be overwritten by cleaned versions.
Keep separate: RAW events, evaluations, derived annotations, final answer.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

import re as _re

# Secret-looking token patterns that must never be persisted to RAW / db even
# when a backend error body echoes them (e.g. LM Studio 401 replay).
_SECRET_PATTERNS = (
    _re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
    _re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    _re.compile(r"gho_[A-Za-z0-9]{20,}"),
    _re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    _re.compile(r"[A-Za-z0-9_\-\.]{20,}@[A-Za-z0-9_\-\.]{6,}"),  # email-like cred
)


def redact_secrets(text) -> str:
    """Replace known credential patterns with a neutral placeholder.

    Guards the immutable RAW / db write path so an LLM backend that echoes a
    bearer token inside a 401 body (as LM Studio does) can never leak it into
    persisted records again. Pure transformation — never raises.
    """
    if not isinstance(text, str):
        return text
    redacted = text
    for pat in _SECRET_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    return redacted


# Schema version for the RAW protocol
SCHEMA_VERSION = "1.0.0"
LAB_VERSION = "0.1.0"
ORCHESTRATION_VERSION = "0.1.0"


class EventType(str, Enum):
    """Types of debate events."""

    PROPOSAL = "proposal"
    CRITIQUE = "critique"
    COUNTERARGUMENT = "counterargument"
    VERIFICATION = "verification"
    CORRECTION = "correction"
    REVISION = "revision"
    VOTE = "vote"
    SCORE = "score"
    TOOL_RESULT = "tool_result"
    CONSENSUS = "consensus"
    REJECTION = "rejection"
    FINAL_CANDIDATE = "final_candidate"


class CandidateStatus(str, Enum):
    """Status of debate candidates."""

    SELECTED = "selected"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    INVALID = "invalid"
    UNVERIFIED = "unverified"


class AgentStatus(str, Enum):
    """Status of agent calls."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    REJECTED = "rejected"


@dataclass
class ExperimentMeta:
    """Metadata for identifying an experiment."""

    schema_version: str = SCHEMA_VERSION
    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    debate_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    timestamp_start: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    timestamp_end: Optional[str] = None
    lab_version: str = LAB_VERSION
    orchestration_version: str = ORCHESTRATION_VERSION
    dataset_source: str = ""
    random_seed: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class InputOriginal:
    """Preserve the original user input without modification."""

    raw_prompt: str
    context: Optional[str] = None
    language: str = "en"
    constraints: list[str] = field(default_factory=list)
    generation_params: dict[str, Any] = field(default_factory=dict)

    # Estimated annotations (separate from original)
    estimated_domain: Optional[str] = None
    estimated_subdomain: Optional[str] = None
    estimated_task_type: Optional[str] = None
    estimated_difficulty: Optional[str] = None
    estimated_skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class RoutingDecision:
    """Record a routing decision."""

    router_id: str = "default"
    router_version: str = ORCHESTRATION_VERSION
    available_agents: list[str] = field(default_factory=list)
    considered_agents: list[str] = field(default_factory=list)
    selected_agents: list[str] = field(default_factory=list)
    non_selected_agents: list[str] = field(default_factory=list)
    routing_scores: dict[str, float] = field(default_factory=dict)
    detected_domain: Optional[str] = None
    sought_skills: list[str] = field(default_factory=list)
    selection_reason: Optional[str] = None
    execution_order: list[str] = field(default_factory=list)
    strategy: str = "sequential"  # parallel, sequential, debate, verification

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class AgentCall:
    """Record an agent call with complete observables."""

    agent_id: str
    agent_version: str = ORCHESTRATION_VERSION
    role: str = ""
    specialty: str = ""
    model_family: str = ""
    model_version: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    system_prompt_version: str = ""
    tools_available: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    input_sent: str = ""
    output_received: str = ""
    status: str = "success"
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    duration_seconds: Optional[float] = None
    estimated_cost: Optional[float] = None
    confidence_score: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class DebateEvent:
    """Record a single debate event."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_event_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    round_num: int = 0
    agent_id: str = ""
    event_type: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class Candidate:
    """Record a debate candidate."""

    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    creator_agent_id: str = ""
    version: str = "1"
    parent_candidate_id: Optional[str] = None
    content: str = ""
    critiques_received: list[str] = field(default_factory=list)
    corrections_proposed: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    status: str = "unverified"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class Disagreement:
    """Record a disagreement between agents."""

    disagreeing_agents: list[str] = field(default_factory=list)
    propositions: list[str] = field(default_factory=list)
    nature_of_disagreement: str = ""
    arguments_formulated: list[str] = field(default_factory=list)
    evidence_invoked: list[str] = field(default_factory=list)
    resolution: Optional[str] = None
    resolving_agent_or_mechanism: Optional[str] = None
    final_result: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class VerificationResult:
    """Record a verification result."""

    verifier_id: str = ""
    verification_method: str = ""
    candidate_evaluated: str = ""
    criteria: dict[str, Any] = field(default_factory=dict)
    scores_by_criteria: dict[str, float] = field(default_factory=dict)
    errors_detected: list[str] = field(default_factory=list)
    unverifiable_elements: list[str] = field(default_factory=list)
    result: Optional[bool] = None
    confidence_level: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class FinalSelection:
    """Record the final selection."""

    considered_candidates: list[str] = field(default_factory=list)
    winner_candidate_id: Optional[str] = None
    selection_method: str = ""
    votes_or_scores: dict[str, Any] = field(default_factory=dict)
    reasons_given: list[str] = field(default_factory=list)
    modifications_after_selection: list[str] = field(default_factory=list)
    final_answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class DerivedLabels:
    """Annotations for future routing (derived, not RAW)."""

    domain: Optional[str] = None
    skills_required: list[str] = field(default_factory=list)
    agents_solicited: list[str] = field(default_factory=list)
    best_individual_agent: Optional[str] = None
    best_agent_combination: list[str] = field(default_factory=list)
    agent_that_detected_error: Optional[str] = None
    agent_that_provided_solution: Optional[str] = None
    cost_of_each_strategy: dict[str, float] = field(default_factory=dict)
    quality_obtained: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class RawDebateRecorder:
    """Main recorder for RAW debate data."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(__file__).parent.parent / "storage" / "raw_data"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._experiments: dict[str, dict[str, Any]] = {}

    def start_experiment(
        self,
        task_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        dataset_source: str = "",
        random_seed: Optional[int] = None,
    ) -> ExperimentMeta:
        """Start a new experiment and return its metadata."""
        meta = ExperimentMeta(
            task_id=task_id or str(uuid.uuid4()),
            parent_task_id=parent_task_id,
            dataset_source=dataset_source,
            random_seed=random_seed,
        )
        self._experiments[meta.experiment_id] = {
            "meta": meta.to_dict(),
            "input_original": None,
            "routing_decisions": [],
            "agent_calls": [],
            "debate_events": [],
            "candidates": [],
            "disagreements": [],
            "verifications": [],
            "final_selection": None,
            "derived_labels": None,
        }
        logger.info("Started experiment %s", meta.experiment_id)
        return meta

    def record_input(
        self,
        experiment_id: str,
        raw_prompt: str,
        context: Optional[str] = None,
        language: str = "en",
        constraints: Optional[list[str]] = None,
        generation_params: Optional[dict[str, Any]] = None,
    ) -> InputOriginal:
        """Record the original input."""
        inp = InputOriginal(
            raw_prompt=raw_prompt,
            context=context,
            language=language,
            constraints=constraints or [],
            generation_params=generation_params or {},
        )
        self._experiments[experiment_id]["input_original"] = inp.to_dict()
        return inp

    def record_routing(
        self,
        experiment_id: str,
        router_id: str = "default",
        available_agents: Optional[list[str]] = None,
        considered_agents: Optional[list[str]] = None,
        selected_agents: Optional[list[str]] = None,
        routing_scores: Optional[dict[str, float]] = None,
        detected_domain: Optional[str] = None,
        strategy: str = "sequential",
    ) -> RoutingDecision:
        """Record a routing decision."""
        decision = RoutingDecision(
            router_id=router_id,
            available_agents=available_agents or [],
            considered_agents=considered_agents or [],
            selected_agents=selected_agents or [],
            non_selected_agents=[a for a in (available_agents or []) if a not in (selected_agents or [])],
            routing_scores=routing_scores or {},
            detected_domain=detected_domain,
            strategy=strategy,
        )
        self._experiments[experiment_id]["routing_decisions"].append(decision.to_dict())
        return decision

    def record_agent_call(
        self,
        experiment_id: str,
        agent_id: str,
        role: str,
        input_sent: str,
        output_received: str,
        status: str = "success",
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        duration_seconds: Optional[float] = None,
    ) -> AgentCall:
        """Record an agent call."""
        call = AgentCall(
            agent_id=agent_id,
            role=role,
            input_sent=redact_secrets(input_sent),
            output_received=redact_secrets(output_received),
            status=status,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            duration_seconds=duration_seconds,
        )
        self._experiments[experiment_id]["agent_calls"].append(call.to_dict())
        return call

    def record_debate_event(
        self,
        experiment_id: str,
        event_type: str,
        agent_id: str,
        content: str,
        round_num: int = 0,
        parent_event_id: Optional[str] = None,
    ) -> DebateEvent:
        """Record a debate event."""
        event = DebateEvent(
            event_type=event_type,
            agent_id=agent_id,
            content=redact_secrets(content),
            round_num=round_num,
            parent_event_id=parent_event_id,
        )
        self._experiments[experiment_id]["debate_events"].append(event.to_dict())
        return event

    def record_candidate(
        self,
        experiment_id: str,
        creator_agent_id: str,
        content: str,
        parent_candidate_id: Optional[str] = None,
    ) -> Candidate:
        """Record a candidate."""
        candidate = Candidate(
            creator_agent_id=creator_agent_id,
            content=content,
            parent_candidate_id=parent_candidate_id,
        )
        self._experiments[experiment_id]["candidates"].append(candidate.to_dict())
        return candidate

    def record_disagreement(
        self,
        experiment_id: str,
        disagreeing_agents: list[str],
        nature_of_disagreement: str,
        arguments_formulated: Optional[list[str]] = None,
    ) -> Disagreement:
        """Record a disagreement."""
        disagreement = Disagreement(
            disagreeing_agents=disagreeing_agents,
            nature_of_disagreement=nature_of_disagreement,
            arguments_formulated=arguments_formulated or [],
        )
        self._experiments[experiment_id]["disagreements"].append(disagreement.to_dict())
        return disagreement

    def record_verification(
        self,
        experiment_id: str,
        verifier_id: str,
        candidate_evaluated: str,
        verification_method: str,
        scores_by_criteria: Optional[dict[str, float]] = None,
        result: Optional[bool] = None,
    ) -> VerificationResult:
        """Record a verification result."""
        verification = VerificationResult(
            verifier_id=verifier_id,
            candidate_evaluated=candidate_evaluated,
            verification_method=verification_method,
            scores_by_criteria=scores_by_criteria or {},
            result=result,
        )
        self._experiments[experiment_id]["verifications"].append(verification.to_dict())
        return verification

    def finalize_selection(
        self,
        experiment_id: str,
        considered_candidates: list[str],
        winner_candidate_id: Optional[str],
        selection_method: str,
        final_answer: str,
        reasons_given: Optional[list[str]] = None,
    ) -> FinalSelection:
        """Record the final selection."""
        selection = FinalSelection(
            considered_candidates=considered_candidates,
            winner_candidate_id=winner_candidate_id,
            selection_method=selection_method,
            final_answer=final_answer,
            reasons_given=reasons_given or [],
        )
        self._experiments[experiment_id]["final_selection"] = selection.to_dict()
        return selection

    def generate_derived_labels(
        self,
        experiment_id: str,
        domain: Optional[str] = None,
        skills_required: Optional[list[str]] = None,
        best_individual_agent: Optional[str] = None,
    ) -> DerivedLabels:
        """Generate derived labels for future routing."""
        labels = DerivedLabels(
            domain=domain,
            skills_required=skills_required or [],
            best_individual_agent=best_individual_agent,
        )
        self._experiments[experiment_id]["derived_labels"] = labels.to_dict()
        return labels

    def end_experiment(self, experiment_id: str) -> None:
        """Mark experiment as ended."""
        if experiment_id in self._experiments:
            self._experiments[experiment_id]["meta"]["timestamp_end"] = datetime.utcnow().isoformat()

    def save_experiment(self, experiment_id: str, filepath: Optional[Path] = None) -> Path:
        """Save experiment data to JSON."""
        if experiment_id not in self._experiments:
            raise ValueError(f"Experiment {experiment_id} not found")

        data = self._experiments[experiment_id]
        if filepath is None:
            filepath = self.storage_dir / f"{experiment_id}.json"
        else:
            filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        logger.info("Saved experiment %s to %s", experiment_id, filepath)
        return Path(filepath)

    def load_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        """Load experiment data from JSON."""
        filepath = self.storage_dir / f"{experiment_id}.json"
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_experiment_ids(self) -> list[str]:
        """Get all experiment IDs."""
        return list(self._experiments.keys())
