"""Structured events for the Deterministic Debate Engine.

Defines the event types and serialization used throughout the debate lifecycle.
Events are emitted via the existing EventBus for observability.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DebateEventType(str, Enum):
    """Event types emitted during a debate session."""

    DEBATE_STARTED = "DEBATE_STARTED"
    ROUND_STARTED = "ROUND_STARTED"
    CLAIM_SUBMITTED = "CLAIM_SUBMITTED"
    COUNTERCLAIM_SUBMITTED = "COUNTERCLAIM_SUBMITTED"
    EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    CONTRADICTION_DETECTED = "CONTRADICTION_DETECTED"
    CONTRADICTION_RESOLVED = "CONTRADICTION_RESOLVED"
    ARBITER_DECISION = "ARBITER_DECISION"
    DEBATE_STAGNATION = "DEBATE_STAGNATION"
    DEBATE_PAUSED = "DEBATE_PAUSED"
    DEBATE_RESUMED = "DEBATE_RESUMED"
    DEBATE_STOPPED = "DEBATE_STOPPED"
    DEBATE_COMPLETED = "DEBATE_COMPLETED"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    RESOURCE_WARNING = "RESOURCE_WARNING"
    # Experience lifecycle events
    EXPERIENCE_CREATED = "EXPERIENCE_CREATED"
    EXPERIENCE_REPLAY_STARTED = "EXPERIENCE_REPLAY_STARTED"
    EXPERIENCE_REPLAY_COMPLETED = "EXPERIENCE_REPLAY_COMPLETED"
    INVESTIGATION_CREATED = "INVESTIGATION_CREATED"
    NEW_EVIDENCE_DISCOVERED = "NEW_EVIDENCE_DISCOVERED"
    EVIDENCE_INVALIDATED = "EVIDENCE_INVALIDATED"
    EVIDENCE_IMPACT_DETECTED = "EVIDENCE_IMPACT_DETECTED"
    DEPENDENCY_CYCLE_DETECTED = "DEPENDENCY_CYCLE_DETECTED"
    CONCLUSION_REVALIDATION_REQUIRED = "CONCLUSION_REVALIDATION_REQUIRED"
    CONCLUSION_REVALIDATED = "CONCLUSION_REVALIDATED"
    INVESTIGATION_STAGNATION = "INVESTIGATION_STAGNATION"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED"
    # Smart investigation triggers
    EXPERIENCE_REINVESTIGATION_SUGGESTED = "EXPERIENCE_REINVESTIGATION_SUGGESTED"
    REINVESTIGATION_AUTHORIZATION_REQUIRED = "REINVESTIGATION_AUTHORIZATION_REQUIRED"
    REINVESTIGATION_AUTHORIZED = "REINVESTIGATION_AUTHORIZED"
    REINVESTIGATION_DENIED = "REINVESTIGATION_DENIED"
    # Failure-to-Knowledge pipeline events
    FAILURE_ANALYSIS_STARTED = "FAILURE_ANALYSIS_STARTED"
    FAILURE_CLASSIFIED = "FAILURE_CLASSIFIED"
    COMPARABLE_RUN_FOUND = "COMPARABLE_RUN_FOUND"
    CAUSAL_HYPOTHESIS_CREATED = "CAUSAL_HYPOTHESIS_CREATED"
    CONTROLLED_EXPERIMENT_PROPOSED = "CONTROLLED_EXPERIMENT_PROPOSED"
    EXPERIMENT_APPROVED = "EXPERIMENT_APPROVED"
    CONTROLLED_EXPERIMENT_STARTED = "CONTROLLED_EXPERIMENT_STARTED"
    CONTROLLED_EXPERIMENT_COMPLETED = "CONTROLLED_EXPERIMENT_COMPLETED"
    KNOWLEDGE_RECORD_CREATED = "KNOWLEDGE_RECORD_CREATED"
    HYPOTHESIS_REFUTED = "HYPOTHESIS_REFUTED"
    FALSE_SUCCESS_SUSPECTED = "FALSE_SUCCESS_SUSPECTED"
    REVALIDATION_REQUESTED = "REVALIDATION_REQUESTED"


@dataclass
class DebateEvent:
    """Structured event from a debate session."""

    event_type: DebateEventType
    session_id: str
    trace_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    sequence_number: int = 0
    source: str = ""
    validated: bool = True
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "sequence_number": self.sequence_number,
            "source": self.source,
            "validated": self.validated,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)


class DebateEventLogger:
    """Logs debate events with sequence numbering and filtering."""

    def __init__(self, session_id: str, trace_id: str) -> None:
        self._session_id = session_id
        self._trace_id = trace_id
        self._events: List[DebateEvent] = []
        self._sequence = 0

    def log(self, event_type: DebateEventType, payload: Dict[str, Any], source: str = "", validated: bool = True) -> DebateEvent:
        """Log an event with auto-incrementing sequence number."""
        self._sequence += 1
        event = DebateEvent(
            event_type=event_type,
            session_id=self._session_id,
            trace_id=self._trace_id,
            payload=payload,
            sequence_number=self._sequence,
            source=source,
            validated=validated,
        )
        self._events.append(event)
        return event

    def get_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get logged events, optionally filtered by type."""
        if event_type:
            result = [e.to_dict() for e in self._events if e.event_type.value == event_type]
        else:
            result = [e.to_dict() for e in self._events]
        return result[-limit:]

    def get_sequence(self) -> int:
        """Get current sequence number."""
        return self._sequence

    def clear(self) -> int:
        """Clear all logged events. Returns count cleared."""
        count = len(self._events)
        self._events.clear()
        self._sequence = 0
        return count
