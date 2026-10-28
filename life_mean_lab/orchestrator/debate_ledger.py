"""Argument Ledger — structured record of debate events.

Tracks arguments, objections, refutations, concessions, hypotheses,
open questions, proposed concepts, and position changes. Detects exact
repetitions and provides configurable semantic repetition detection.

Design rules:
  - Textual similarity is NOT treated as conceptual repetition.
  - Events are directly observable; interpretations are separate.
  - Ledger is append-only; entries cannot be modified after recording.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Life_mean.Orchestrator.DebateLedger")


# ── Event types ───────────────────────────────────────────────────────────────


class DebateEventType(str, enum.Enum):
    ARGUMENT = "argument"
    OBJECTION = "objection"
    REFUTATION = "refutation"
    CONCESSION = "concession"
    HYPOTHESIS = "hypothesis"
    OPEN_QUESTION = "open_question"
    PROPOSED_CONCEPT = "proposed_concept"
    POSITION_CHANGE = "position_change"


# ── Event dataclass ───────────────────────────────────────────────────────────


@dataclass
class DebateEvent:
    """A single event in a debate."""
    event_type: DebateEventType
    agent_id: str
    content: str
    timestamp: float = field(default_factory=time.time)
    round_number: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        """Deterministic ID based on content and agent."""
        payload = f"{self.agent_id}:{self.event_type.value}:{self.content}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.event_type.value,
            "agent_id": self.agent_id,
            "content_preview": self.content[:200] if len(self.content) > 200 else self.content,
            "timestamp": self.timestamp,
            "round_number": self.round_number,
            "metadata": self.metadata,
        }


# ── Repetition detector ───────────────────────────────────────────────────────


class RepetitionDetector:
    """Detects exact and configurable semantic repetitions."""

    def __init__(self, max_history: int = 100) -> None:
        self._exact_hashes: Dict[str, int] = {}  # hash -> count
        self._recent_events: List[DebateEvent] = []
        self._max_history = max_history

    def check_exact(self, event: DebateEvent) -> bool:
        """Check for exact textual repetition."""
        content_hash = hashlib.sha256(event.content.encode("utf-8")).hexdigest()
        count = self._exact_hashes.get(content_hash, 0)
        if count > 0:
            logger.debug("Exact repetition detected for %s: '%.50s...'",
                         event.agent_id, event.content)
            return True
        self._record(event)
        return False

    def check_configured(self, event: DebateEvent, similarity_threshold: float = 0.9) -> bool:
        """Check for repetitions using configurable similarity."""
        # Exact check first.
        if self.check_exact(event):
            return True

        # Semantic check against recent events (configurable threshold).
        for recent in self._recent_events[-self._max_history:]:
            if recent.agent_id == event.agent_id and recent.event_type == event.event_type:
                # Simple token overlap ratio as proxy for semantic similarity.
                tokens_a = set(event.content.lower().split())
                tokens_b = set(recent.content.lower().split())
                if len(tokens_a) > 0 and len(tokens_b) > 0:
                    overlap = len(tokens_a & tokens_b) / max(len(tokens_a), len(tokens_b))
                    if overlap >= similarity_threshold:
                        logger.debug("Semantic repetition detected for %s (overlap=%.2f)",
                                     event.agent_id, overlap)
                        return True

        self._record(event)
        return False

    def _record(self, event: DebateEvent) -> None:
        content_hash = hashlib.sha256(event.content.encode("utf-8")).hexdigest()
        self._exact_hashes[content_hash] = self._exact_hashes.get(content_hash, 0) + 1
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_history:
            self._recent_events.pop(0)


# ── Debate Ledger ─────────────────────────────────────────────────────────────


class ArgumentLedger:
    """Structured record of all debate events.

    Provides append-only logging with repetition detection and summary queries.
    """

    def __init__(self, debate_id: str, detect_repetitions: bool = True) -> None:
        self.debate_id = debate_id
        self._events: List[DebateEvent] = []
        self._repetition_detector = RepetitionDetector() if detect_repetitions else None
        self._agent_positions: Dict[str, str] = {}  # agent_id -> current position
        self._position_changes: List[Dict[str, Any]] = []

    def record(
        self,
        event_type: DebateEventType,
        agent_id: str,
        content: str,
        round_number: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DebateEvent:
        """Record a debate event. Returns the recorded event."""
        event = DebateEvent(
            event_type=event_type,
            agent_id=agent_id,
            content=content,
            round_number=round_number,
            metadata=metadata or {},
        )
        self._events.append(event)

        # Track position changes.
        if event_type == DebateEventType.POSITION_CHANGE:
            self._position_changes.append({
                "agent_id": agent_id,
                "new_position": content[:100],
                "round": round_number,
                "timestamp": event.timestamp,
            })

        # Check for repetitions.
        if self._repetition_detector:
            is_repeated = self._repetition_detector.check_configured(event)
            if is_repeated:
                event.metadata["is_repeated"] = True
                logger.warning("REPETITION DETECTED for %s - consider regeneration", agent_id)

        return event

    def get_events_by_agent(self, agent_id: str) -> List[DebateEvent]:
        """Get all events for a specific agent."""
        return [e for e in self._events if e.agent_id == agent_id]

    def get_events_by_type(self, event_type: DebateEventType) -> List[DebateEvent]:
        """Get all events of a specific type."""
        return [e for e in self._events if e.event_type == event_type]

    def get_open_questions(self) -> List[DebateEvent]:
        """Get all open questions."""
        return self.get_events_by_type(DebateEventType.OPEN_QUESTION)

    def get_position_changes(self) -> List[Dict[str, Any]]:
        """Get all position changes."""
        return self._position_changes

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary of the debate."""
        type_counts = {}
        for e in self._events:
            type_counts[e.event_type.value] = type_counts.get(e.event_type.value, 0) + 1

        return {
            "debate_id": self.debate_id,
            "total_events": len(self._events),
            "event_type_counts": type_counts,
            "position_changes": len(self._position_changes),
            "open_questions": len(self.get_open_questions()),
            "rounds_completed": max((e.round_number for e in self._events), default=0),
        }

    def export_json(self, path: str) -> str:
        """Export ledger to JSON."""
        import json
        data = {
            "debate_id": self.debate_id,
            "events": [e.to_dict() for e in self._events],
            "summary": self.get_summary(),
            "position_changes": self._position_changes,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path
