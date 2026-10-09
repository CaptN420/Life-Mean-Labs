"""Events for the debate engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DebateState(Enum):
    """States of the debate lifecycle."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class TurnEvent:
    """Event fired when a turn completes."""

    turn_id: int
    round_num: int
    speaker: str
    speaker_role: str
    response: str
    moderator_question: Optional[str] = None
    moderator_reason: Optional[str] = None
    model: Optional[str] = None
    duration_seconds: Optional[float] = None
    finish_reason: Optional[str] = None
    was_truncated: bool = False


@dataclass
class ModeratorEvent:
    """Event fired when the moderator makes a decision."""

    turn_id: int
    round_num: int
    selected_speaker: str
    challenge: str
    reason: str
    question: Optional[str] = None
    detected_issues: Optional[str] = None


@dataclass
class MemoryEvent:
    """Event fired when memory is updated."""

    event_type: str  # "short_term", "mid_term", "long_term"
    details: str


@dataclass
class StateEvent:
    """Event fired when the debate state changes."""

    new_state: DebateState
    old_state: Optional[DebateState] = None
    message: Optional[str] = None


@dataclass
class ErrorEvent:
    """Event fired when an error occurs."""

    error_type: str
    message: str
    turn_id: Optional[int] = None


@dataclass
class DebateUpdate:
    """Complete update payload for the GUI."""

    state: DebateState
    turn: Optional[TurnEvent] = None
    moderator: Optional[ModeratorEvent] = None
    memory: Optional[MemoryEvent] = None
    error: Optional[ErrorEvent] = None
    stats: dict[str, Any] = field(default_factory=dict)
