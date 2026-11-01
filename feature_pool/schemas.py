"""FeaturePool schemas — data models for feature registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class FeatureStatus(str, Enum):
    """Technical lifecycle status of a feature."""
    DISCOVERED = "DISCOVERED"
    ANALYZED = "ANALYZED"
    VALIDATED = "VALIDATED"
    READY = "READY"
    INTEGRATED = "INTEGRATED"
    BROKEN = "BROKEN"
    BLOCKED = "BLOCKED"
    ARCHIVED = "ARCHIVED"
    EXPERIMENTAL = "EXPERIMENTAL"


class IntegrationStatus(str, Enum):
    """Integration state — separate from technical status."""
    NOT_STARTED = "NOT_STARTED"
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ROLLED_BACK = "ROLLED_BACK"


class FeatureCategory(str, Enum):
    """Category of feature."""
    # Core infrastructure
    ROUTING = "routing"
    PERSISTENCE = "persistence"
    OBSERVABILITY = "observability"
    SAFETY = "safety"
    PROVIDERS = "providers"

    # Experimentation
    EXPERIMENTS = "experiments"
    GENERATION = "generation"
    VALIDATION = "validation"
    METACOGNITION = "metacognition"

    # AI/Agent
    AGENTS = "agents"
    PERSONAS = "personas"
    DEBATE = "debate"
    CODE_LAB = "code_lab"
    AUTOPILOT = "autopilot"

    # Studio
    STUDIO = "studio"
    WORKFLOWS = "workflows"
    PROMPTS = "prompts"

    # Legacy
    LEGACY = "legacy"
    CRAWLERS = "crawlers"
    TOOLS = "tools"


@dataclass
class FeatureLocation:
    """Location of a feature in the codebase."""
    path: str           # Relative to project root
    module: str         # Python module name
    line_start: int     # Line number (1-indexed)
    line_end: Optional[int]
    symbol: str         # Class or function name

    def __str__(self) -> str:
        loc = f":{self.line_start}" if self.line_end else ""
        return f"{self.path}:{self.symbol}{loc}"


@dataclass
class HistoryEntry:
    """Audit trail entry."""
    timestamp: datetime
    action: str         # DISCOVERED, ANALYZED, VALIDATED, etc.
    actor: str          # "system", "user", or user identifier
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "actor": self.actor,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEntry":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            action=data["action"],
            actor=data.get("actor", "system"),
            details=data.get("details", {}),
        )


@dataclass
class Feature:
    """Represents a discovered feature."""
    id: str                     # Stable ID: feat_<category>_<name>
    name: str
    category: FeatureCategory
    status: FeatureStatus = FeatureStatus.DISCOVERED
    integration_status: IntegrationStatus = IntegrationStatus.NOT_STARTED
    locations: List[FeatureLocation] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)
    test_paths: List[str] = field(default_factory=list)
    # Gaps observed during analysis (e.g. "no_tests"). Never a status change.
    coverage_gaps: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.5     # 0.0 to 1.0 analysis confidence
    history: List[HistoryEntry] = field(default_factory=list)

    @property
    def is_legacy(self) -> bool:
        """Whether this feature comes from legacy code."""
        for loc in self.locations:
            # Normalize path separators for cross-platform detection
            normalized = loc.path.replace("\\", "/")
            if ("legacy/" in normalized or
                "historical" in normalized or
                "hermes-debate" in normalized):
                return True
        return False

    @property
    def source(self) -> str:
        """Primary source path."""
        return self.locations[0].path if self.locations else "unknown"

    @property
    def has_tests(self) -> bool:
        """Whether tests exist for this feature."""
        return len(self.test_paths) > 0

    @property
    def recommended_action(self) -> str:
        """Recommended next action based on status."""
        if self.status == FeatureStatus.BROKEN:
            return "Investigate and fix"
        if self.status == FeatureStatus.BLOCKED:
            return "Resolve blockers"
        if self.status == FeatureStatus.VALIDATED and self.integration_status == IntegrationStatus.NOT_STARTED:
            return "Plan integration"
        if self.status == FeatureStatus.DISCOVERED:
            return "Analyze"
        if self.status == FeatureStatus.ANALYZED:
            return "Validate"
        return "Review"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "status": self.status.value,
            "integration_status": self.integration_status.value,
            "locations": [
                {
                    "path": loc.path,
                    "module": loc.module,
                    "line_start": loc.line_start,
                    "line_end": loc.line_end,
                    "symbol": loc.symbol,
                }
                for loc in self.locations
            ],
            "dependencies": list(self.dependencies),
            "test_paths": self.test_paths,
            "coverage_gaps": self.coverage_gaps,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "history": [h.to_dict() for h in self.history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Feature":
        """Deserialize from storage."""
        locations = [
            FeatureLocation(
                path=loc["path"],
                module=loc["module"],
                line_start=loc["line_start"],
                line_end=loc.get("line_end"),
                symbol=loc["symbol"],
            )
            for loc in data.get("locations", [])
        ]
        history = [
            HistoryEntry.from_dict(h) for h in data.get("history", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            category=FeatureCategory(data["category"]),
            status=FeatureStatus(data["status"]),
            integration_status=IntegrationStatus(data.get("integration_status", "NOT_STARTED")),
            locations=locations,
            dependencies=set(data.get("dependencies", [])),
            test_paths=data.get("test_paths", []),
            coverage_gaps=data.get("coverage_gaps", []),
            metadata=data.get("metadata", {}),
            confidence=data.get("confidence", 0.5),
            history=history,
        )

    def add_history(self, action: str, actor: str = "system", details: Optional[Dict[str, Any]] = None) -> None:
        """Record a history entry."""
        self.history.append(HistoryEntry(
            timestamp=datetime.now(),
            action=action,
            actor=actor,
            details=details or {},
        ))


@dataclass
class Conflict:
    """Represents a compatibility conflict between features."""
    feature_a: str
    feature_b: str
    conflict_type: str
    severity: str  # "high", "medium", "low"
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_a": self.feature_a,
            "feature_b": self.feature_b,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass
class IntegrationPlan:
    """Plan for integrating a feature."""
    feature_id: str
    steps: List[Dict[str, Any]]
    estimated_risk: str  # "low", "medium", "high"
    required_tests: List[str]
    rollback_plan: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "steps": self.steps,
            "estimated_risk": self.estimated_risk,
            "required_tests": self.required_tests,
            "rollback_plan": self.rollback_plan,
        }
