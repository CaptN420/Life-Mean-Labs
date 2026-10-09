"""ExperimentDesign — versioned, typed schema for the Experimental Engine.

A design is the frozen contract of ONE experiment. Lifecycle:

    DRAFT -> REVIEWED -> APPROVED -> FROZEN   (REJECTED / SUPERSEDED optional)

Execution is forbidden unless ``status == FROZEN``. A frozen design is
immutable by construction: every edit goes through ``with_`` which returns a
NEW design carrying ``version += 1`` (and marks the old one SUPERSEDED), never
mutating the frozen snapshot in place.

This module holds typed dataclasses only — no execution, no LLM, no engine.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Design lifecycle states. Execution is gated on FROZEN only.
DESIGN_STATES = ("DRAFT", "REVIEWED", "APPROVED", "FROZEN", "REJECTED", "SUPERSEDED")
# State reachable by human approval before a run may even be prepared.
_FREEZABLE_FROM = ("DRAFT", "REVIEWED", "APPROVED")


class DesignStateError(ValueError):
    """Raised on an illegal lifecycle transition (e.g. freezing a REJECTED design)."""


@dataclass
class DesignAgent:
    """One experimental agent. MODEL != ROLE != PERSONA != SKILL != TOOL: each
    concern is a distinct field; ``model_assignment`` is None => dynamic routing."""

    agent_id: str
    role: str
    persona: str = ""
    model_assignment: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    system_prompt: str = ""
    # Layered prompt composition (ROLE / PERSONA / SKILLS / CONTEXT /
    # CAPABILITIES / CONSTRAINTS / OUTPUT) per spec §7, so a single layer can
    # change without rewriting the whole prompt. Component hashes are recorded
    # alongside the final prompt hash in provenance.
    prompt_components: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "persona": self.persona,
            "model_assignment": self.model_assignment,
            "skills": list(self.skills),
            "allowed_tools": list(self.allowed_tools),
            "system_prompt": self.system_prompt,
            "prompt_components": dict(self.prompt_components),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignAgent":
        return cls(
            agent_id=str(data.get("agent_id", "")),
            role=str(data.get("role", "")),
            persona=str(data.get("persona", "")),
            model_assignment=data.get("model_assignment"),
            skills=[str(s) for s in data.get("skills", [])],
            allowed_tools=[str(t) for t in data.get("allowed_tools", [])],
            system_prompt=str(data.get("system_prompt", "")),
            prompt_components=dict(data.get("prompt_components", {})),
        )


@dataclass
class DesignStage:
    """One execution stage. ``executor_type`` selects the executor via the
    dispatcher — a stage NEVER hardcodes a model; it picks which EXISTING
    engine/worker runs it."""

    stage_id: str
    executor_type: str
    participants: List[str] = field(default_factory=list)  # agent_ids
    request: str = ""
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "executor_type": self.executor_type,
            "participants": list(self.participants),
            "request": self.request,
            "config": dict(self.config),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignStage":
        return cls(
            stage_id=str(data.get("stage_id", "")),
            executor_type=str(data.get("executor_type", "")),
            participants=[str(a) for a in data.get("participants", [])],
            request=str(data.get("request", "")),
            config=dict(data.get("config", {})),
        )


@dataclass
class DesignBudgets:
    """Budget ceilings; a run exceeding any ceil stops (STOP_CONDITION_REACHED),
    never silently continues."""

    max_agent_calls: int = 20
    max_iterations: int = 10
    max_tool_calls: int = 50
    max_runtime_seconds: int = 1800
    max_repairs: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_agent_calls": self.max_agent_calls,
            "max_iterations": self.max_iterations,
            "max_tool_calls": self.max_tool_calls,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_repairs": self.max_repairs,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignBudgets":
        return cls(
            max_agent_calls=int(data.get("max_agent_calls", 20)),
            max_iterations=int(data.get("max_iterations", 10)),
            max_tool_calls=int(data.get("max_tool_calls", 50)),
            max_runtime_seconds=int(data.get("max_runtime_seconds", 1800)),
            max_repairs=int(data.get("max_repairs", 3)),
        )


class ExperimentDesign:
    """Immutable-once-frozen experiment contract."""

    def __init__(
        self,
        *,
        title: str = "",
        description: str = "",
        research_question: str = "",
        agents: Optional[List[DesignAgent]] = None,
        stages: Optional[List[DesignStage]] = None,
        validators: Optional[List[str]] = None,
        budgets: Optional[DesignBudgets] = None,
        stop_conditions: Optional[List[Dict[str, Any]]] = None,
        design_id: Optional[str] = None,
        version: int = 1,
        status: str = "DRAFT",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if status not in DESIGN_STATES:
            raise ValueError(f"invalid design status '{status}'")
        self.design_id = design_id or f"DESIGN-{uuid.uuid4().hex[:12].upper()}"
        self.title = title
        self.description = description
        self.research_question = research_question
        self.agents = list(agents or [])
        self.stages = list(stages or [])
        self.validators = [str(v) for v in (validators or [])]
        self.budgets = budgets or DesignBudgets()
        self.stop_conditions = [dict(s) for s in (stop_conditions or [])]
        self.version = version
        self.status = status
        self.metadata = dict(metadata or {})
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.frozen_hash = ""

    # ── serialization ─────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return {
            "design_id": self.design_id,
            "version": self.version,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "research_question": self.research_question,
            "agents": [a.to_dict() for a in self.agents],
            "stages": [s.to_dict() for s in self.stages],
            "validators": list(self.validators),
            "budgets": self.budgets.to_dict(),
            "stop_conditions": self.stop_conditions,
            "frozen_hash": self.frozen_hash,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentDesign":
        d = cls(
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            research_question=str(data.get("research_question", "")),
            agents=[DesignAgent.from_dict(a) for a in data.get("agents", [])],
            stages=[DesignStage.from_dict(s) for s in data.get("stages", [])],
            validators=[str(v) for v in data.get("validators", [])],
            budgets=DesignBudgets.from_dict(data.get("budgets", {})),
            stop_conditions=[dict(s) for s in data.get("stop_conditions", [])],
            design_id=str(data.get("design_id")),
            version=int(data.get("version", 1)),
            status=str(data.get("status", "DRAFT")),
            metadata=dict(data.get("metadata", {})),
        )
        d.frozen_hash = str(data.get("frozen_hash", "") or "")
        return d

    # ── content hash (spec §3 / §17) ──────────────────────────────────────
    def _content_payload(self) -> str:
        """Deterministic, science-only payload for the design hash: excludes
        design_id, status, frozen_hash and timestamps. version IS included so a
        versioned re-run of identical content still has a distinct identity."""
        payload = {
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "research_question": self.research_question,
            "agents": sorted((a.to_dict() for a in self.agents), key=lambda a: a["agent_id"]),
            "stages": sorted((s.to_dict() for s in self.stages), key=lambda s: s["stage_id"]),
            "validators": self.validators,
            "budgets": self.budgets.to_dict(),
            "stop_conditions": self.stop_conditions,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    def content_hash(self) -> str:
        return hashlib.sha256(self._content_payload().encode("utf-8")).hexdigest()

    # ── lifecycle ─────────────────────────────────────────────────────────
    @property
    def is_frozen(self) -> bool:
        return self.status == "FROZEN"

    @property
    def can_run(self) -> bool:
        return self.is_frozen

    def transition(self, target: str) -> "ExperimentDesign":
        """Return a NEW design in ``target`` state, cloning current content
        (original untouched). Only DRAFT->REVIEWED->APPROED->FROZEN advances;
        REJECTED/SUPERSEDED are terminal reclassifications."""
        if target not in DESIGN_STATES:
            raise DesignStateError(f"invalid state '{target}'")
        if self.is_frozen:
            raise DesignStateError("a frozen design cannot transition; make a new version")
        if target == "FROZEN" and self.status not in _FREEZABLE_FROM:
            raise DesignStateError(f"cannot freeze from '{self.status}'")
        updated = self.clone()
        updated.status = target
        if target == "FROZEN":
            updated.frozen_hash = self.content_hash()  # hash of the content, pre-status
        updated.updated_at = time.time()
        return updated

    def freeze(self) -> "ExperimentDesign":
        return self.transition("FROZEN")

    def approve(self) -> "ExperimentDesign":
        return self.transition("APPROVED")

    def review(self) -> "ExperimentDesign":
        return self.transition("REVIEWED")

    def clone(self) -> "ExperimentDesign":
        return self.from_dict(self.to_dict())

    def with_(self, **updates: Any) -> "ExperimentDesign":
        """Return a NEW design with ``updates`` applied. From a frozen design
        this produces a SUPERSEDED old + a fresh next version (DRAFT). The
        caller decides the restart state via ``status`` in updates."""
        data = self.to_dict()
        if self.is_frozen:
            # Frozen contract is immutable: editing it is a NEW version.
            old = self.clone()
            old.status = "SUPERSEDED"
            data = old.to_dict()
            data["status"] = "DRAFT"
            data["version"] = self.version + 1
        for k, v in updates.items():
            data[k] = v
        return self.from_dict(data)

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<ExperimentDesign {self.design_id} v{self.version} {self.status} "
                f"agents={len(self.agents)} stages={len(self.stages)}>")