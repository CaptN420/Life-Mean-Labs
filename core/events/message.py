"""Core events — universal communication units.

Copied from Mia_Brain (External/Mia_Brain/CaptN-BRAIN-main/captn/runtime/base.py)
with minimal adaptation for the new architecture.

Message: The universal communication unit for all components.
Task: The core unit of work defined in the schema.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """The universal communication unit for all components."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = "system"
    destination: str = "orchestrator"
    type: str = "task"  # task, state_update, error, response
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "destination": self.destination,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            sender=data.get("sender", "system"),
            destination=data.get("destination", "orchestrator"),
            type=data.get("type", "task"),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class Task:
    """The core unit of work defined in the schema."""

    task_id: str
    source: str
    action: str  # The primary action requested
    pipeline_id: str  # Added to support pipeline logic
    priority: int = 1
    payload: Dict[str, Any] = field(default_factory=dict)
    retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed
    file_path: Optional[str] = None  # Added to support direct file pathing

    def to_json(self) -> Dict[str, Any]:
        return self.__dict__

    @property
    def is_complete(self) -> bool:
        return self.status in ("completed", "failed")


@dataclass
class Rule:
    """A strict rule enforced by the Orchestrator."""

    name: str
    description: str
    condition: Any  # Callable[[Task], bool]
    error_message: str


@dataclass
class Pipeline:
    """A sequence of actions that a task must go through."""

    id: str
    steps: List[str]  # e.g., ["extractor", "normalizer", "translator", "validator"]
