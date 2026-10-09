"""Core events — EventBus abstraction.

Defines the interface for event publishing and subscription.
Adapted from Mia_Brain's MessageBus concept.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from core.events.message import Message

logger = logging.getLogger(__name__)


class EventBus:
    """Event bus for decoupled communication between components.

    Adapted from Mia_Brain's MessageBus concept.
    Supports:
    - Publish/subscribe pattern
    - Type-based routing
    - Synchronous execution
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._history: List[Message] = []

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug(f"Subscribed to {event_type}")

    def publish(self, message: Message) -> None:
        """Publish a message to all handlers of the matching type."""
        self._history.append(message)
        handlers = self._handlers.get(message.type, [])
        for handler in handlers:
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Handler error for {message.type}: {e}")

    def get_history(self, limit: int = 100) -> List[Message]:
        """Get recent message history."""
        return self._history[-limit:]

    def clear_history(self) -> None:
        """Clear message history."""
        self._history.clear()

    @property
    def history_count(self) -> int:
        return len(self._history)


class InMemoryStateStore:
    """Simple in-memory state store for experiments.

    Stores key-value pairs with timestamps.
    Used for experiment state tracking.
    """

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}

    def set(self, key: str, value: Any) -> None:
        """Store a value."""
        self._data[key] = value
        import time
        self._timestamps[key] = time.time()

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value."""
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists."""
        return key in self._data

    def delete(self, key: str) -> bool:
        """Delete a key."""
        if key in self._data:
            del self._data[key]
            if key in self._timestamps:
                del self._timestamps[key]
            return True
        return False

    def keys(self) -> List[str]:
        """Get all keys."""
        return list(self._data.keys())

    def clear(self) -> None:
        """Clear all data."""
        self._data.clear()
        self._timestamps.clear()
