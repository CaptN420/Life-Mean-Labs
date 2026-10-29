"""Persona schema — dataclasses for the unified persona system.

This module defines the canonical data structures for personas, providers,
and model specs. It is the single source of truth for serialization and
validation.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class PersonaType(str, enum.Enum):
    """Types of personas available in the system."""

    # Core philosophical personas
    ANALYTICAL_PHILOSOPHER = "analytical_philosopher"
    ETHICAL_PHILOSOPHER = "ethical_philosopher"
    SKEPTIC = "skeptic"
    ADVOCATE = "advocate"
    SCIENTIST = "scientist"
    PRAGMATIST = "pragmatist"

    # Optional personas
    CONTRARIAN = "contrarian"
    HUMANIST = "humanist"
    FUTURIST = "futurist"
    OPTIMIST = "optimist"
    PESSIMIST_RISK_ANALYST = "pessimist_risk_analyst"
    MEDIATOR = "mediator"
    NEUTRAL_JUDGE = "neutral_judge"
    INTERDISCIPLINARY_RESEARCHER = "interdisciplinary_researcher"


class ProviderType(str, enum.Enum):
    """Types of LLM providers supported."""

    LOCAL = "local"           # LM Studio, ollama, llama.cpp
    OPENAI = "openai"         # OpenAI API (gpt-4, gpt-3.5-turbo)
    ANTHROPIC = "anthropic"   # Claude models
    AZURE = "azure"           # Azure OpenAI
    MOCK = "mock"             # Testing / deterministic fallback


class ModelHealth(str, enum.Enum):
    """Health status of a model."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class PersonaConfig:
    """Configuration for a single persona."""

    role_id: str
    name: str
    persona_type: PersonaType
    description: str
    system_prompt: str
    color: str = "#888888"
    version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Optional template inheritance (parent persona_id)
    parent_persona_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.role_id.strip():
            raise ValueError("role_id must not be empty")
        if not self.system_prompt.strip():
            raise ValueError("system_prompt must not be empty")

    @property
    def persona_id(self) -> str:
        """Unique identifier for this persona."""
        return self.role_id

    @property
    def is_template(self) -> bool:
        """Whether this persona is a template (has children)."""
        return bool(self.parent_persona_id)

    def content_hash(self) -> str:
        """Deterministic hash of meaningful content."""
        blob = json.dumps({
            "role_id": self.role_id,
            "name": self.name,
            "persona_type": self.persona_type.value,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "version": self.version,
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "persona_type": self.persona_type.value,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "color": self.color,
            "version": self.version,
            "metadata": self.metadata,
            "parent_persona_id": self.parent_persona_id,
            "content_hash": self.content_hash(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaConfig":
        return cls(
            role_id=str(data.get("role_id", "")),
            name=str(data.get("name", "")),
            persona_type=PersonaType(str(data.get("persona_type", "analytical_philosopher"))),
            description=str(data.get("description", "")),
            system_prompt=str(data.get("system_prompt", "")),
            color=str(data.get("color", "#888888")),
            version=str(data.get("version", "1.0.0")),
            metadata=dict(data.get("metadata", {}) or {}),
            parent_persona_id=data.get("parent_persona_id"),
        )


@dataclass
class ModelSpec:
    """Declarative description of an LLM model's capabilities."""

    model_id: str
    provider: ProviderType
    endpoint: str = ""
    api_key_env: str = ""

    # Declared or measured capabilities.
    context_window: int = 8192
    max_output_tokens: int = 4096
    estimated_vram_mb: int = 0
    estimated_ram_mb: int = 0
    estimated_params_b: float = 0.0

    # Observed metrics (updated by health checks).
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    last_health_check: float = 0.0
    health: ModelHealth = ModelHealth.UNKNOWN
    success_rate: float = 0.0
    total_requests: int = 0
    failed_requests: int = 0

    # Metadata.
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.health in (ModelHealth.HEALTHY, ModelHealth.DEGRADED)

    @property
    def is_local(self) -> bool:
        return self.provider == ProviderType.LOCAL

    def record_success(self, latency_ms: float) -> None:
        alpha = 0.1
        self.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.avg_latency_ms
        if latency_ms > self.p99_latency_ms:
            self.p99_latency_ms = latency_ms
        self.total_requests += 1
        self.last_health_check = time.time()
        self.success_rate = (self.success_rate * (self.total_requests - 1) + 1.0) / self.total_requests
        if self.success_rate >= 0.95:
            self.health = ModelHealth.HEALTHY
        elif self.success_rate >= 0.7:
            self.health = ModelHealth.DEGRADED
        else:
            self.health = ModelHealth.UNHEALTHY

    def record_failure(self) -> None:
        self.total_requests += 1
        self.failed_requests += 1
        self.last_health_check = time.time()
        if self.total_requests > 0:
            self.success_rate = (self.total_requests - self.failed_requests) / self.total_requests
        if self.success_rate < 0.5:
            self.health = ModelHealth.UNHEALTHY
        elif self.success_rate < 0.7:
            self.health = ModelHealth.DEGRADED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider.value,
            "endpoint": self.endpoint,
            "api_key_env": self.api_key_env,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "estimated_vram_mb": self.estimated_vram_mb,
            "estimated_ram_mb": self.estimated_ram_mb,
            "estimated_params_b": self.estimated_params_b,
            "avg_latency_ms": self.avg_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "health": self.health.value,
            "success_rate": self.success_rate,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelSpec":
        return cls(
            model_id=str(data.get("model_id", "")),
            provider=ProviderType(str(data.get("provider", "local"))),
            endpoint=str(data.get("endpoint", "")),
            api_key_env=str(data.get("api_key_env", "")),
            context_window=int(data.get("context_window", 8192)),
            max_output_tokens=int(data.get("max_output_tokens", 4096)),
            estimated_vram_mb=int(data.get("estimated_vram_mb", 0)),
            estimated_ram_mb=int(data.get("estimated_ram_mb", 0)),
            estimated_params_b=float(data.get("estimated_params_b", 0.0)),
            tags=list(data.get("tags", []) or []),
        )


# ── Persona Relationships ───────────────────────────────────────────────────


class RelationshipType(str, enum.Enum):
    """Types of relationships between personas."""

    # Dialogue relationships
    DEBATE_PARTNER = "debate_partner"          # Will debate together
    RESPONDER = "responder"                   # Responds to another persona
    CHALLENGER = "challenger"                 # Challenges another persona's views
    SYNTHESIZER = "synthesizer"               # Synthesizes views from others

    # Knowledge relationships
    MENTOR = "mentor"                         # Teaches/trains another
    STUDENT = "student"                       # Learns from another
    COLLABORATOR = "collaborator"             # Works together on tasks

    # Structural relationships
    SUBORDINATE = "subordinate"               # Reports to another
    SUPERVISOR = "supervisor"                 # Oversees another


@dataclass
class PersonaRelationship:
    """A relationship between two personas."""

    source_id: str                              # persona that initiates
    target_id: str                              # persona that receives
    relationship_type: RelationshipType
    strength: float = 1.0                       # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type.value,
            "strength": self.strength,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaRelationship":
        return cls(
            source_id=str(data.get("source_id", "")),
            target_id=str(data.get("target_id", "")),
            relationship_type=RelationshipType(str(data.get("relationship_type", "debate_partner"))),
            strength=float(data.get("strength", 1.0)),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class DebateSessionConfig:
    """Configuration for a single debate session."""

    topic: str
    personas: List[str] = field(default_factory=list)          # persona role_ids
    model_pool: List[str] = field(default_factory=list)        # model_id -> provider mapping
    max_turns: int = 20
    temperature: float = 0.8
    max_tokens: int = 2000
    routing_method: str = "context_aware"                      # context_aware, round_robin, weighted, random
    prevent_repetition: bool = True
    trace_id: str = ""

    # New: persona relationships for this session
    relationship_graph: Dict[str, Any] = field(default_factory=dict)  # source_id -> list of target_ids
    workflow: List[str] = field(default_factory=list)                # ordered execution sequence

    def __post_init__(self) -> None:
        if not self.topic.strip():
            raise ValueError("topic must not be empty")
        if self.max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        if self.routing_method not in ("context_aware", "round_robin", "weighted", "random"):
            raise ValueError(f"invalid routing_method: {self.routing_method}")

    @property
    def session_id(self) -> str:
        return f"debate_{int(time.time())}_{hash(self.topic) % 0xFFFF:04x}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "personas": list(self.personas),
            "model_pool": list(self.model_pool),
            "max_turns": self.max_turns,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "routing_method": self.routing_method,
            "prevent_repetition": self.prevent_repetition,
            "trace_id": self.trace_id,
            "relationship_graph": self.relationship_graph,
            "workflow": list(self.workflow),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebateSessionConfig":
        return cls(
            topic=str(data.get("topic", "")),
            personas=list(data.get("personas", []) or []),
            model_pool=list(data.get("model_pool", []) or []),
            max_turns=int(data.get("max_turns", 20)),
            temperature=float(data.get("temperature", 0.8)),
            max_tokens=int(data.get("max_tokens", 2000)),
            routing_method=str(data.get("routing_method", "context_aware")),
            prevent_repetition=bool(data.get("prevent_repetition", True)),
            trace_id=str(data.get("trace_id", "")),
            relationship_graph=dict(data.get("relationship_graph", {}) or {}),
            workflow=list(data.get("workflow", []) or []),
        )
