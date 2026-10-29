"""Experience Registry — persistent storage and retrieval of debate experiments.

Each experience is an immutable record of a completed debate session.
Experiences can be replayed, investigated further, or compared.
Historical results are never overwritten — new investigations create derived experiences.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.experience_registry")


# ── Enums ────────────────────────────────────────────────────────────────────


class ExperienceStatus(str, Enum):
    """Lifecycle status of an experience."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    REPLAYED = "REPLAYED"
    INVESTIGATED = "INVESTIGATED"
    ARCHIVED = "ARCHIVED"


class ExperienceType(str, Enum):
    """Type of experience."""
    ORIGINAL = "ORIGINAL"
    REPLAY = "REPLAY"
    DEEP_INVESTIGATION = "DEEP_INVESTIGATION"
    FOLLOW_UP = "FOLLOW_UP"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ExperienceRecord:
    """Immutable record of a completed debate experience."""

    experience_id: str
    session_id: str
    question: str
    hypotheses: List[str] = field(default_factory=list)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    contradiction_ids: List[str] = field(default_factory=list)
    conclusions: List[str] = field(default_factory=list)
    decision: str = "UNRESOLVED"
    rule_version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    parent_experience_id: Optional[str] = None
    status: ExperienceStatus = ExperienceStatus.PENDING
    experience_type: ExperienceType = ExperienceType.ORIGINAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Derived experience tracking
    derived_experience_ids: List[str] = field(default_factory=list)

    @property
    def is_historical(self) -> bool:
        """True if this is an original or replay (not a deep investigation)."""
        return self.experience_type in (ExperienceType.ORIGINAL, ExperienceType.REPLAY)

    @property
    def is_investigation(self) -> bool:
        """True if this is a deep investigation or follow-up."""
        return self.experience_type in (ExperienceType.DEEP_INVESTIGATION, ExperienceType.FOLLOW_UP)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "session_id": self.session_id,
            "question": self.question,
            "hypotheses": self.hypotheses,
            "claims": self.claims,
            "evidence_ids": self.evidence_ids,
            "contradiction_ids": self.contradiction_ids,
            "conclusions": self.conclusions,
            "decision": self.decision,
            "rule_version": self.rule_version,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "parent_experience_id": self.parent_experience_id,
            "status": self.status.value,
            "experience_type": self.experience_type.value,
            "metadata": self.metadata,
            "derived_experience_ids": self.derived_experience_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperienceRecord:
        return cls(
            experience_id=data["experience_id"],
            session_id=data["session_id"],
            question=data["question"],
            hypotheses=data.get("hypotheses", []),
            claims=data.get("claims", []),
            evidence_ids=data.get("evidence_ids", []),
            contradiction_ids=data.get("contradiction_ids", []),
            conclusions=data.get("conclusions", []),
            decision=data.get("decision", "UNRESOLVED"),
            rule_version=data.get("rule_version", "1.0.0"),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
            parent_experience_id=data.get("parent_experience_id"),
            status=ExperienceStatus(data.get("status", "PENDING")),
            experience_type=ExperienceType(data.get("experience_type", "ORIGINAL")),
            metadata=data.get("metadata", {}),
            derived_experience_ids=data.get("derived_experience_ids", []),
        )


# ── Experience Registry ──────────────────────────────────────────────────────


class ExperienceRegistry:
    """Registry for storing, retrieving, and searching debate experiences.

    Experiences are immutable — once created, they cannot be modified.
    New investigations create derived experiences with a parent reference.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self._experiences: Dict[str, ExperienceRecord] = {}
        self._storage_path = storage_path
        self._next_id = 1

        if storage_path:
            self._load_from_disk()

    def create_experience(
        self,
        session_id: str,
        question: str,
        decision: str = "UNRESOLVED",
        claims: Optional[List[Dict[str, Any]]] = None,
        evidence_ids: Optional[List[str]] = None,
        contradiction_ids: Optional[List[str]] = None,
        conclusions: Optional[List[str]] = None,
        rule_version: str = "1.0.0",
        parent_experience_id: Optional[str] = None,
        experience_type: ExperienceType = ExperienceType.ORIGINAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExperienceRecord:
        """Create a new experience record."""
        exp_id = f"EXP-{self._next_id:04d}"
        self._next_id += 1

        record = ExperienceRecord(
            experience_id=exp_id,
            session_id=session_id,
            question=question,
            hypotheses=[],
            claims=claims or [],
            evidence_ids=evidence_ids or [],
            contradiction_ids=contradiction_ids or [],
            conclusions=conclusions or [],
            decision=decision,
            rule_version=rule_version,
            parent_experience_id=parent_experience_id,
            status=ExperienceStatus.COMPLETED,
            experience_type=experience_type,
            metadata=metadata or {},
        )

        self._experiences[exp_id] = record

        # Update parent's derived list
        if parent_experience_id and parent_experience_id in self._experiences:
            parent = self._experiences[parent_experience_id]
            parent.derived_experience_ids.append(exp_id)

        logger.info("Experience created: %s (type=%s, parent=%s)", exp_id, experience_type.value, parent_experience_id)
        return record

    def get_experience(self, experience_id: str) -> Optional[ExperienceRecord]:
        """Retrieve an experience by ID."""
        return self._experiences.get(experience_id)

    def get_by_session(self, session_id: str) -> List[ExperienceRecord]:
        """Get all experiences associated with a session."""
        return [exp for exp in self._experiences.values() if exp.session_id == session_id]

    def get_all(self) -> List[ExperienceRecord]:
        """Get all experiences."""
        return list(self._experiences.values())

    def search_by_question(self, query: str) -> List[ExperienceRecord]:
        """Search experiences by question content (case-insensitive substring)."""
        query_lower = query.lower()
        return [
            exp for exp in self._experiences.values()
            if query_lower in exp.question.lower()
        ]

    def search_by_decision(self, decision: str) -> List[ExperienceRecord]:
        """Search experiences by decision."""
        return [exp for exp in self._experiences.values() if exp.decision == decision]

    def search_by_hypothesis(self, hypothesis_keyword: str) -> List[ExperienceRecord]:
        """Search experiences containing a hypothesis keyword."""
        keyword = hypothesis_keyword.lower()
        return [
            exp for exp in self._experiences.values()
            if any(keyword in h.lower() for h in exp.hypotheses)
        ]

    def search_by_contradiction(self, contradiction_id: str) -> List[ExperienceRecord]:
        """Search experiences that contain a specific contradiction."""
        return [
            exp for exp in self._experiences.values()
            if contradiction_id in exp.contradiction_ids
        ]

    def get_derived_experiences(self, experience_id: str) -> List[ExperienceRecord]:
        """Get all experiences derived from a parent."""
        parent = self._experiences.get(experience_id)
        if not parent:
            return []
        return [self._experiences[eid] for eid in parent.derived_experience_ids if eid in self._experiences]

    def get_experience_tree(self, experience_id: str) -> Dict[str, Any]:
        """Get the full tree of an experience and its descendants."""
        exp = self._experiences.get(experience_id)
        if not exp:
            return {}

        tree = {
            "experience": exp.to_dict(),
            "children": [],
        }

        for child_id in exp.derived_experience_ids:
            child = self._experiences.get(child_id)
            if child:
                tree["children"].append(self.get_experience_tree(child_id))

        return tree

    def complete_experience(self, experience_id: str, decision: str, conclusions: Optional[List[str]] = None) -> bool:
        """Mark an experience as completed with a decision."""
        exp = self._experiences.get(experience_id)
        if not exp:
            return False
        exp.decision = decision
        exp.completed_at = time.time()
        if conclusions:
            exp.conclusions = conclusions
        exp.status = ExperienceStatus.COMPLETED
        return True

    def archive_experience(self, experience_id: str) -> bool:
        """Archive an experience."""
        exp = self._experiences.get(experience_id)
        if not exp:
            return False
        exp.status = ExperienceStatus.ARCHIVED
        return True

    def _load_from_disk(self) -> None:
        """Load experiences from JSONL file."""
        if not self._storage_path:
            return
        path = Path(self._storage_path)
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    record = ExperienceRecord.from_dict(data)
                    self._experiences[record.experience_id] = record
                    # Update next ID counter
                    num = int(record.experience_id.split("-")[1])
                    if num >= self._next_id:
                        self._next_id = num + 1
                except (json.JSONDecodeError, KeyError):
                    logger.warning("Skipping malformed experience line: %s", line[:80])

    def persist_to_disk(self) -> int:
        """Persist all experiences to JSONL file. Returns count written."""
        if not self._storage_path:
            return 0
        path = Path(self._storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for exp in sorted(self._experiences.values(), key=lambda e: e.created_at):
                f.write(json.dumps(exp.to_dict(), ensure_ascii=False) + "\n")
        return len(self._experiences)

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        by_status = {}
        by_type = {}
        by_decision = {}
        for exp in self._experiences.values():
            by_status[exp.status.value] = by_status.get(exp.status.value, 0) + 1
            by_type[exp.experience_type.value] = by_type.get(exp.experience_type.value, 0) + 1
            by_decision[exp.decision] = by_decision.get(exp.decision, 0) + 1

        return {
            "total_experiences": len(self._experiences),
            "by_status": by_status,
            "by_type": by_type,
            "by_decision": by_decision,
        }
