"""Debate state management.

CORE (lifecycle) DebateState. The debate engine uses TWO distinct state
objects: ``_state`` (this CORE dataclass) for the debate lifecycle
(start/pause/resume/stop/advance/record_error) and ``argument_state`` (the
ENHANCED ``philosophical_council.memory.debate_state.DebateState``) for
progressive argumentation, repetition detection, phases and the
optimistic-turn reservation/rollback. This division is intentional and must be
preserved: core does NOT re-export the enhanced class.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DebateState:
    """Tracks the current state of a debate."""

    # Basic state
    topic: str = ""
    status: str = "idle"  # idle, running, paused, stopping, stopped, error

    # Progress tracking
    turn_id: int = 0
    round_num: int = 0

    # Timestamps
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    # Current moderator decision
    current_moderator_decision: dict[str, str] = field(default_factory=dict)

    # Statistics
    total_turns: int = 0
    error_count: int = 0

    def start(self) -> None:
        """Start the debate."""
        self.status = "running"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.turn_id = 0
        self.round_num = 0
        self.total_turns = 0
        logger.info("Debate started: %s", self.topic)

    def pause(self) -> None:
        """Pause the debate."""
        self.status = "paused"
        logger.info("Debate paused")

    def resume(self) -> None:
        """Resume the debate."""
        self.status = "running"
        logger.info("Debate resumed")

    def stop(self) -> None:
        """Stop the debate."""
        self.status = "stopped"
        self.finished_at = datetime.now(timezone.utc).isoformat()
        logger.info("Debate stopped after %d turns", self.total_turns)

    def advance_turn(self) -> int:
        """Advance to the next turn, return the new turn_id."""
        self.turn_id += 1
        if self.turn_id % 5 == 0:
            self.round_num += 1
        self.total_turns += 1
        return self.turn_id

    def record_error(self, message: str) -> None:
        """Record an error."""
        self.error_count += 1
        logger.warning("Error #%d: %s", self.error_count, message)

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict."""
        return {
            "topic": self.topic,
            "status": self.status,
            "turn_id": self.turn_id,
            "round_num": self.round_num,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_turns": self.total_turns,
            "error_count": self.error_count,
            "current_moderator_decision": self.current_moderator_decision,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DebateState:
        """Deserialize from dict."""
        state = cls(
            topic=str(data.get("topic", "")),
            status=str(data.get("status", "idle")),
            turn_id=int(data.get("turn_id", 0)),
            round_num=int(data.get("round_num", 0)),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )
        state.total_turns = int(data.get("total_turns", 0))
        state.error_count = int(data.get("error_count", 0))
        mod = data.get("current_moderator_decision", {})
        if isinstance(mod, dict):
            state.current_moderator_decision = mod
        return state