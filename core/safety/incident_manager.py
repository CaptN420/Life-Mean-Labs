"""Incident manager for LIFE_MEAN.

Tracks, manages, and reports incidents.
"""
from __future__ import annotations

import json
import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.safety.incident_manager")


class IncidentSeverity(str, Enum):
    """Severity of an incident."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, Enum):
    """Status of an incident."""
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    QUARANTINED = "QUARANTINED"


@dataclass
class IncidentEvent:
    """An incident that occurred in the system."""
    event_type: str
    severity: IncidentSeverity
    component: str
    worker: str = ""
    task_id: str = ""
    validation: str = "UNVERIFIED"
    attempts: int = 0
    progress_detected: bool = False
    action: str = "PAUSE"
    security_bypass_attempted: bool = False
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    trace_id: str = ""
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event_type,
            "severity": self.severity.value,
            "component": self.component,
            "worker": self.worker,
            "task_id": self.task_id,
            "validation": self.validation,
            "attempts": self.attempts,
            "progress_detected": self.progress_detected,
            "action": self.action,
            "security_bypass_attempted": self.security_bypass_attempted,
            "evidence": self.evidence,
            "trace_id": self.trace_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class IncidentManager:
    """Manages incidents in the system."""

    def __init__(self):
        self._incidents: Dict[str, IncidentEvent] = {}
        self._event_log: List[Dict[str, Any]] = []

    def create_incident(
        self,
        event_type: str,
        severity: IncidentSeverity,
        component: str,
        worker: str = "",
        task_id: str = "",
        validation: str = "UNVERIFIED",
        attempts: int = 0,
        progress_detected: bool = False,
        action: str = "PAUSE",
        security_bypass_attempted: bool = False,
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> IncidentEvent:
        """Create a new incident."""
        trace_id = str(uuid.uuid4())[:8]

        incident = IncidentEvent(
            event_type=event_type,
            severity=severity,
            component=component,
            worker=worker,
            task_id=task_id,
            validation=validation,
            attempts=attempts,
            progress_detected=progress_detected,
            action=action,
            security_bypass_attempted=security_bypass_attempted,
            evidence=evidence or [],
            trace_id=trace_id,
        )

        self._incidents[trace_id] = incident
        self._event_log.append(incident.to_dict())

        logger.warning(
            "Incident created: %s in %s (trace: %s)",
            event_type, component, trace_id,
        )

        return incident

    def update_status(self, trace_id: str, status: IncidentStatus) -> bool:
        """Update the status of an incident."""
        if trace_id not in self._incidents:
            return False

        incident = self._incidents[trace_id]
        incident.status = status

        if status == IncidentStatus.RESOLVED and incident.resolved_at is None:
            incident.resolved_at = time.time()

        # Update event log
        for event in self._event_log:
            if event.get("trace_id") == trace_id:
                event["status"] = status.value
                break

        return True

    def get_incident(self, trace_id: str) -> Optional[IncidentEvent]:
        """Get an incident by trace ID."""
        return self._incidents.get(trace_id)

    def get_open_incidents(self) -> List[IncidentEvent]:
        """Get all open incidents."""
        return [
            inc for inc in self._incidents.values()
            if inc.status == IncidentStatus.OPEN
        ]

    def get_incidents_by_severity(
        self,
        severity: IncidentSeverity,
    ) -> List[IncidentEvent]:
        """Get incidents by severity."""
        return [
            inc for inc in self._incidents.values()
            if inc.severity == severity
        ]

    def resolve_incident(self, trace_id: str) -> bool:
        """Mark an incident as resolved."""
        return self.update_status(trace_id, IncidentStatus.RESOLVED)

    def quarantine_incident(self, trace_id: str) -> bool:
        """Quarantine an incident (mark as critical)."""
        return self.update_status(trace_id, IncidentStatus.QUARANTINED)

    def get_statistics(self) -> Dict[str, Any]:
        """Get incident statistics."""
        stats = {
            "total": len(self._incidents),
            "by_severity": {},
            "by_status": {},
        }

        for inc in self._incidents.values():
            sev_key = inc.severity.value
            stats["by_severity"][sev_key] = stats["by_severity"].get(sev_key, 0) + 1

            status_key = inc.status.value
            stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

        return stats

    def export_log(self) -> List[Dict[str, Any]]:
        """Export the event log."""
        return list(self._event_log)

    def clear_resolved(self) -> int:
        """Clear resolved incidents."""
        count = 0
        to_remove = [tid for tid, inc in self._incidents.items() if inc.status == IncidentStatus.RESOLVED]
        for tid in to_remove:
            del self._incidents[tid]
            count += 1
        return count
