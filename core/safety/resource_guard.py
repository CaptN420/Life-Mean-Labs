"""Resource guard for LIFE_MEAN.

Monitors CPU, memory, tokens, and other resources.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.safety.resource_guard")


class ResourceExceeded(str, Enum):
    """Type of resource exceeded."""
    CPU_TIME = "CPU_TIME"
    MEMORY = "MEMORY"
    TOKENS = "TOKENS"
    EXECUTION_TIME = "EXECUTION_TIME"
    RETRY_COUNT = "RETRY_COUNT"


@dataclass
class ResourceLimit:
    """Resource limit configuration."""
    resource_type: str
    soft_limit: float  # Warning threshold
    hard_limit: float  # Block threshold
    unit: str = ""


@dataclass
class ResourceEvent:
    """Event emitted when a resource limit is approached or exceeded."""
    event: str
    severity: str  # INFO, WARNING, ERROR, CRITICAL
    resource_type: str
    current_value: float
    limit: float
    unit: str
    component: str
    task_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "severity": self.severity,
            "resource_type": self.resource_type,
            "current_value": self.current_value,
            "limit": self.limit,
            "unit": self.unit,
            "component": self.component,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
        }


class ResourceGuard:
    """Monitors and enforces resource limits."""

    def __init__(self):
        self._limits: Dict[str, ResourceLimit] = {
            "cpu_time": ResourceLimit("cpu_time", 5000.0, 10000.0, "ms"),
            "memory": ResourceLimit("memory", 500.0, 1000.0, "MB"),
            "tokens": ResourceLimit("tokens", 50000, 100000, ""),
            "execution_time": ResourceLimit("execution_time", 30000.0, 60000.0, "ms"),
            "retry_count": ResourceLimit("retry_count", 3, 5, ""),
        }
        self._current_usage: Dict[str, float] = {}
        self._events: List[ResourceEvent] = []

    def check_limit(
        self,
        resource_type: str,
        current_value: float,
        component: str,
        task_id: str = "",
    ) -> Optional[ResourceEvent]:
        """Check if a resource limit is exceeded."""
        limit_config = self._limits.get(resource_type)
        if not limit_config:
            return None

        # Check hard limit
        if current_value >= limit_config.hard_limit:
            event = ResourceEvent(
                event=f"RESOURCE_EXCEEDED:{resource_type}",
                severity="CRITICAL",
                resource_type=resource_type,
                current_value=current_value,
                limit=limit_config.hard_limit,
                unit=limit_config.unit,
                component=component,
                task_id=task_id,
            )
            self._record_event(event)
            logger.critical("Resource %s exceeded hard limit: %s %s", resource_type, current_value, limit_config.unit)
            return event

        # Check soft limit
        if current_value >= limit_config.soft_limit:
            event = ResourceEvent(
                event=f"RESOURCE_WARNING:{resource_type}",
                severity="WARNING",
                resource_type=resource_type,
                current_value=current_value,
                limit=limit_config.soft_limit,
                unit=limit_config.unit,
                component=component,
                task_id=task_id,
            )
            self._record_event(event)
            logger.warning("Resource %s approaching limit: %s %s", resource_type, current_value, limit_config.unit)
            return event

        return None

    def update_usage(self, resource_type: str, value: float) -> None:
        """Update current resource usage."""
        self._current_usage[resource_type] = value

    def set_limit(self, resource_type: str, soft_limit: float, hard_limit: float, unit: str = "") -> None:
        """Set or update a resource limit."""
        if resource_type in self._limits:
            self._limits[resource_type] = ResourceLimit(
                resource_type=resource_type,
                soft_limit=soft_limit,
                hard_limit=hard_limit,
                unit=unit,
            )
        else:
            self._limits[resource_type] = ResourceLimit(
                resource_type=resource_type,
                soft_limit=soft_limit,
                hard_limit=hard_limit,
                unit=unit,
            )

    def _record_event(self, event: ResourceEvent) -> None:
        """Record a resource event."""
        self._events.append(event)
        if len(self._events) > 1000:
            self._events = self._events[-500:]

    def get_events(
        self,
        resource_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[ResourceEvent]:
        """Get recorded resource events."""
        result = self._events
        if resource_type:
            result = [e for e in result if e.resource_type == resource_type]
        if severity:
            result = [e for e in result if e.severity == severity]
        return result

    def clear_events(self) -> int:
        """Clear all recorded events."""
        count = len(self._events)
        self._events.clear()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get resource guard statistics."""
        return {
            "limits": {k: {"soft": v.soft_limit, "hard": v.hard_limit, "unit": v.unit} for k, v in self._limits.items()},
            "current_usage": dict(self._current_usage),
            "total_events": len(self._events),
        }
