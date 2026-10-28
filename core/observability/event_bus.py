"""Event bus for LIFE_MEAN.

Provides event distribution and notification coordination.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("core.observability.event_bus")


class EventPriority(str, Enum):
    """Priority of an event."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Event:
    """Event emitted by the system."""
    event_type: str
    payload: Dict[str, Any]
    priority: EventPriority = EventPriority.NORMAL
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "priority": self.priority.value,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventBus:
    """Event bus for distributing events to subscribers."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._event_log: List[Event] = []
        self._rate_limits: Dict[str, int] = {}  # event_type -> count per window

    def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        """Subscribe to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed to %s", event_type)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        self._event_log.append(event)

        # Rate limiting
        if event.event_type in self._rate_limits:
            self._rate_limits[event.event_type] += 1
            if self._rate_limits[event.event_type] > 100:
                logger.warning("Rate limit exceeded for %s", event.event_type)
                return

        # Call subscribers
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.error("Event handler error for %s: %s", event.event_type, exc)

    def publish_critical(self, event_type: str, payload: Dict[str, Any], source: str = "") -> None:
        """Publish a critical event."""
        event = Event(
            event_type=event_type,
            payload=payload,
            priority=EventPriority.CRITICAL,
            source=source,
        )
        self.publish(event)

    def publish_warning(self, event_type: str, payload: Dict[str, Any], source: str = "") -> None:
        """Publish a warning event."""
        event = Event(
            event_type=event_type,
            payload=payload,
            priority=EventPriority.HIGH,
            source=source,
        )
        self.publish(event)

    def get_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Get recent events."""
        if event_type:
            result = [e for e in self._event_log if e.event_type == event_type]
        else:
            result = list(self._event_log)
        return result[-limit:]

    def clear_log(self) -> int:
        """Clear the event log."""
        count = len(self._event_log)
        self._event_log.clear()
        return count

    def get_statistics(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        type_counts = {}
        for e in self._event_log:
            type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1

        return {
            "total_events": len(self._event_log),
            "by_type": type_counts,
            "subscribers": {k: len(v) for k, v in self._subscribers.items()},
        }
