"""Debate Lab configuration (V1).

A reproducible, serializable per-run configuration, parallel in spirit to
``code_lab.config.CodeLabConfig`` but for the EXISTING DebateEngine.

Every field is recorded in RAW provenance; nothing is exposed that the
DebateEngine/runtime does not actually honor (no phantom controls):

- ``max_turns``            real execution budget (>=1, ceiling 10000)
- ``temperature`` / token budgets / memory intervals  wired to DebateConfig
- ``prevent_repetition`` / ``max_consecutive_same_speaker``  wired to the
  session's argument-state repetition policy
- ``model_routing_method`` only real ModelRouter methods (context_aware /
  round_robin / weighted / random) — never the fake "llm" mode
- ``speaker_selection_mode`` only "moderator_llm" (the one real supported mode)
- ``role_models``          exact per-role model; blank = dynamic routing
- ``model_pool``           the dynamic routing pool
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Model routing methods that are GENUINELY implemented by ModelRouter.
REAL_MODEL_ROUTING_METHODS = ("context_aware", "round_robin", "weighted", "random")
# Speaker-selection modes that are genuinely implemented (moderator-driven).
REAL_SPEAKER_SELECTION_MODES = ("moderator_llm",)
MAX_TURNS_CEILING = 10000


class DebateLabConfigError(ValueError):
    """A controlled configuration error (never a silent fallback)."""


@dataclass
class DebateLabConfig:
    """Configuration for a single Debate Lab run."""

    # User inputs
    topic: str = ""
    run_name: str = ""

    # Team / workflow preset (a RoleTemplate — NOT an ExperimentProtocol).
    template_id: str = "philosophical-debate"
    role_models: Dict[str, str] = field(default_factory=dict)  # role_id -> model

    # Execution budget
    max_turns: int = 20

    # Inference
    temperature: float = 0.8
    moderator_max_tokens: int = 1000
    participant_max_tokens: int = 2000
    max_continuations: int = 2

    # Memory
    short_term_turns: int = 20
    mid_term_interval: int = 10
    long_term_interval: int = 50

    # Repetition policy
    prevent_repetition: bool = True
    max_consecutive_same_speaker: int = 1

    # Speaker selection ("who speaks next") — separate from MODEL routing.
    speaker_selection_mode: str = "moderator_llm"

    # Model routing ("which model executes this call").
    model_routing_method: str = "context_aware"
    model_pool: List[str] = field(default_factory=list)

    seed: Optional[int] = None

    # Tracking
    run_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = f"debatelab_{uuid.uuid4().hex[:10]}"
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not self.topic or not self.topic.strip():
            raise DebateLabConfigError("DEBATE_TOPIC_REQUIRED: a topic is required")
        if not isinstance(self.max_turns, int) or self.max_turns < 1:
            raise DebateLabConfigError("INVALID_MAX_TURNS: max_turns must be >= 1")
        if self.max_turns > MAX_TURNS_CEILING:
            raise DebateLabConfigError(
                f"INVALID_MAX_TURNS: max_turns must be <= {MAX_TURNS_CEILING}")
        if not (0.0 <= float(self.temperature) <= 2.0):
            raise DebateLabConfigError("INVALID_TEMPERATURE: temperature must be in [0, 2]")
        if self.model_routing_method not in REAL_MODEL_ROUTING_METHODS:
            raise DebateLabConfigError(
                f"INVALID_MODEL_ROUTING: '{self.model_routing_method}' is not a real "
                f"routing method (choose one of {REAL_MODEL_ROUTING_METHODS})")
        if self.speaker_selection_mode not in REAL_SPEAKER_SELECTION_MODES:
            raise DebateLabConfigError(
                f"INVALID_SPEAKER_SELECTION: '{self.speaker_selection_mode}' is not "
                f"implemented (only {REAL_SPEAKER_SELECTION_MODES})")
        if self.moderator_max_tokens < 1 or self.participant_max_tokens < 1:
            raise DebateLabConfigError("INVALID_TOKEN_BUDGET: token budgets must be >= 1")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "topic": self.topic,
            "run_name": self.run_name,
            "template_id": self.template_id,
            "role_models": dict(self.role_models),
            "max_turns": self.max_turns,
            "temperature": self.temperature,
            "moderator_max_tokens": self.moderator_max_tokens,
            "participant_max_tokens": self.participant_max_tokens,
            "max_continuations": self.max_continuations,
            "short_term_turns": self.short_term_turns,
            "mid_term_interval": self.mid_term_interval,
            "long_term_interval": self.long_term_interval,
            "prevent_repetition": self.prevent_repetition,
            "max_consecutive_same_speaker": self.max_consecutive_same_speaker,
            "speaker_selection_mode": self.speaker_selection_mode,
            "model_routing_method": self.model_routing_method,
            "model_pool": list(self.model_pool),
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateLabConfig":
        return cls(
            topic=str(data.get("topic", "")),
            run_name=str(data.get("run_name", "")),
            template_id=str(data.get("template_id", "philosophical-debate")),
            role_models=dict(data.get("role_models", {}) or {}),
            max_turns=int(data.get("max_turns", 20)),
            temperature=float(data.get("temperature", 0.8)),
            moderator_max_tokens=int(data.get("moderator_max_tokens", 1000)),
            participant_max_tokens=int(data.get("participant_max_tokens", 2000)),
            max_continuations=int(data.get("max_continuations", 2)),
            short_term_turns=int(data.get("short_term_turns", 20)),
            mid_term_interval=int(data.get("mid_term_interval", 10)),
            long_term_interval=int(data.get("long_term_interval", 50)),
            prevent_repetition=_to_bool(data.get("prevent_repetition", True)),
            max_consecutive_same_speaker=int(data.get("max_consecutive_same_speaker", 1)),
            speaker_selection_mode=str(data.get("speaker_selection_mode", "moderator_llm")),
            model_routing_method=str(data.get("model_routing_method", "context_aware")),
            model_pool=list(data.get("model_pool", []) or []),
            seed=data.get("seed"),
            run_id=str(data.get("run_id", "")),
            created_at=str(data.get("created_at", "")),
        )


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "on", "yes")
