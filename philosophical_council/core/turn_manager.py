"""Turn management for the debate engine."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """A single turn in the debate."""

    turn_id: int
    round_num: int
    speaker: str
    speaker_role: str
    moderator_question: Optional[str] = None
    moderator_reason: Optional[str] = None
    response: str = ""
    model: Optional[str] = None
    duration_seconds: Optional[float] = None
    timestamp: Optional[str] = None
    sections: Optional[dict] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "turn_id": self.turn_id,
            "round": self.round_num,
            "timestamp": self.timestamp,
            "speaker": self.speaker,
            "speaker_role": self.speaker_role,
            "moderator_question": self.moderator_question,
            "moderator_reason": self.moderator_reason,
            "response": self.response,
            "model": self.model,
            "duration_seconds": self.duration_seconds,
            "sections": self.sections,
        }


class TurnManager:
    """Manages turn sequencing and scheduling."""

    def __init__(self) -> None:
        self._turns: list[Turn] = []
        self._current_turn_id: int = 0
        self._current_round: int = 1  # Start at 1, not 0

    @property
    def current_turn_id(self) -> int:
        return self._current_turn_id

    @property
    def current_round(self) -> int:
        return self._current_round

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    def next_turn(self, speaker: str, speaker_role: str,
                 moderator_question: Optional[str] = None,
                 moderator_reason: Optional[str] = None,
                 model: Optional[str] = None) -> Turn:
        """Create and return the next turn."""
        self._current_turn_id += 1
        # Round increments every 5 turns, starting from round 1
        if self._current_turn_id % 5 == 0:
            self._current_round += 1

        turn = Turn(
            turn_id=self._current_turn_id,
            round_num=self._current_round,
            speaker=speaker,
            speaker_role=speaker_role,
            moderator_question=moderator_question,
            moderator_reason=moderator_reason,
            model=model,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._turns.append(turn)
        return turn

    def complete_turn(self, turn_id: int, response: str, duration: float,
                      sections: Optional[dict] = None) -> None:
        """Mark a turn as completed with its response (and optional parsed
        visible-response sections, §78)."""
        for turn in self._turns:
            if turn.turn_id == turn_id:
                turn.response = response
                turn.duration_seconds = duration
                if sections is not None:
                    turn.sections = sections
                return
        logger.warning("Turn %d not found for completion", turn_id)

    def get_turn(self, turn_id: int) -> Optional[Turn]:
        """Get a specific turn by ID."""
        for turn in self._turns:
            if turn.turn_id == turn_id:
                return turn
        return None

    def get_recent_turns(self, n: int = 20) -> list[Turn]:
        """Get the last n turns."""
        return self._turns[-n:]

    def get_all_turns(self) -> list[Turn]:
        """Get all turns."""
        return list(self._turns)

    def clear(self) -> None:
        """Clear all turns."""
        self._turns.clear()
        self._current_turn_id = 0
        self._current_round = 1  # Reset to 1, not 0
