"""Short-term memory — recent conversation context."""

from __future__ import annotations

import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """Holds the most recent N turns for immediate context."""

    def __init__(self, capacity: int = 20) -> None:
        self.capacity = capacity
        self._turns: deque[dict[str, str]] = deque(maxlen=capacity)

    def add(self, turn_id: int, round_num: int, speaker: str,
            moderator_question: Optional[str], response: str) -> None:
        """Add a turn to short-term memory."""
        self._turns.append({
            "turn_id": str(turn_id),
            "round": str(round_num),
            "speaker": speaker,
            "moderator_question": moderator_question or "",
            "response": response,
        })

    def get_context(self) -> str:
        """Return a text representation of the current short-term context."""
        if not self._turns:
            return "(No recent turns yet.)"
        lines = ["SHORT-TERM MEMORY (recent context):"]
        for entry in self._turns:
            lines.append(f"\n--- Turn {entry['turn_id']} (Round {entry['round']}) ---")
            lines.append(f"Speaker: {entry['speaker']}")
            if entry["moderator_question"]:
                lines.append(f"Moderator: {entry['moderator_question']}")
            lines.append(f"{entry['response']}")
        return "\n".join(lines)

    def get_recent_turns(self, n: Optional[int] = None) -> list[dict[str, str]]:
        """Return the last n turns as dicts."""
        if n is None:
            return list(self._turns)
        return list(self._turns)[-n:]

    def clear(self) -> None:
        self._turns.clear()

    @property
    def count(self) -> int:
        return len(self._turns)
