"""Role Template — core object model.

A RoleTemplate is a *versioned, hashable, serializable* description of a team /
protocol. It lives in the EXPERIMENTAL LAYER and CONFIGURES the existing stable
core (existing engines, agents, model config) — it never replaces it.

Invariants enforced at this layer:

    MODEL  !=  ROLE  !=  PERSONA

- A template describes ROLES (responsibilities).
- A ROLE may declare a *preferred/default* PERSONA, but a persona is a
  separate identity and the experiment may override it.
- MODELS are NEVER hardcoded inside a template. Model assignment is a separate
  `RoleModelMapping` (role_id -> model) carried by the experiment.

The content hash is DETERMINISTIC: it covers every scientifically-meaningful
field (role instructions, objectives, constraints, expected output, permissions,
team composition/order, version, template_id) and EXCLUDES `created_at` /
`updated_at` so re-saving without content change keeps the same hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _canonical_dict(obj: Any) -> Any:
    """Normalise a Python object into a canonical, hash-stable structure."""
    if isinstance(obj, dict):
        return {str(k): _canonical_dict(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_canonical_dict(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    return str(obj)


@dataclass
class RoleSpec:
    """A single role in a RoleTemplate (a responsibility, not a model/persona)."""

    role_id: str
    name: str = ""
    instructions_template: str = ""
    objectives: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    expected_output: str = ""
    permissions: List[str] = field(default_factory=list)
    # Optional *preferred* persona — the experiment may override it.
    default_persona: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.role_id.replace("_", " ").title()

    def content(self) -> Dict[str, Any]:
        """The scientifically-meaningful payload used for hashing."""
        return {
            "role_id": self.role_id,
            "name": self.name,
            "instructions_template": self.instructions_template,
            "objectives": self.objectives,
            "constraints": self.constraints,
            "expected_output": self.expected_output,
            "permissions": self.permissions,
            "default_persona": self.default_persona,
        }

    def to_dict(self) -> Dict[str, Any]:
        return self.content()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleSpec":
        return cls(
            role_id=str(data.get("role_id", "")),
            name=str(data.get("name", "")),
            instructions_template=str(data.get("instructions_template", "")),
            objectives=list(data.get("objectives", [])),
            constraints=list(data.get("constraints", [])),
            expected_output=str(data.get("expected_output", "")),
            permissions=list(data.get("permissions", [])),
            default_persona=str(data.get("default_persona", "")),
        )


@dataclass
class RoleTemplate:
    """A versioned, hashable description of an agent team / protocol."""

    template_id: str
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    # Executor/protocol this template is compatible with:
    #   "code_lab" | "philosophical_debate" | "general_reasoning" (metadata only)
    # The executor is PART of the template identity (hashed): provenance says
    # which protocol a template may drive, and a run must never claim a template
    # executed under a protocol it is not compatible with.
    executor_type: str = ""
    roles: List[RoleSpec] = field(default_factory=list)
    created_at: str = ""          # metadata only — NOT part of the hash
    updated_at: str = ""          # metadata only — NOT part of the hash

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.template_id.replace("-", " ").title()

    # ── hashing ───────────────────────────────────────────────────────────
    def content(self) -> Dict[str, Any]:
        """Canonical content dict (excludes timestamps)."""
        return {
            "template_id": self.template_id,
            "version": self.version,
            "description": self.description,
            "executor_type": self.executor_type,
            "roles": [r.content() for r in self.roles],
        }

    def content_hash(self) -> str:
        """Deterministic SHA-256 over the canonical JSON of meaningful content.

        Changing role instructions, objectives, constraints, output schema,
        permissions, team composition/order, version or template_id changes the
        hash. Re-saving with identical content (only timestamps change) keeps it.
        """
        blob = json.dumps(
            _canonical_dict(self.content()),
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    # ── serialization ─────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.content(),
            "name": self.name,
            "hash": self.content_hash(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleTemplate":
        return cls(
            template_id=str(data.get("template_id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "1.0.0")),
            description=str(data.get("description", "")),
            executor_type=str(data.get("executor_type", "")),
            roles=[RoleSpec.from_dict(r) for r in data.get("roles", [])],
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )

    def summary(self) -> Dict[str, Any]:
        """Safe, metadata-only summary for API/UI (no instruction bodies)."""
        return {
            "id": self.template_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "hash": self.content_hash(),
            "executor_type": self.executor_type,
            "roles": [
                {"role_id": r.role_id, "name": r.name,
                 "default_persona": r.default_persona}
                for r in self.roles
            ],
        }


@dataclass
class RoleModelMapping:
    """CONFIGURED experiment-level model assignment (separate from template).

    Maps role_id -> model id. An empty / missing entry means DYNAMIC routing
    (the existing stable-core router/fallback decides). This is the piece that
    lets the SAME template run against DIFFERENT models and vice-versa.
    """

    template_id: str = ""
    template_version: str = ""
    models: Dict[str, str] = field(default_factory=dict)  # role_id -> model

    def get(self, role_id: str) -> str:
        return self.models.get(role_id, "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_version": self.template_version,
            "models": dict(self.models),
        }
