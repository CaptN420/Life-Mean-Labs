"""Mid-term memory — structured summaries of debate sections."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MidTermEntry:
    """A summary of a section of the debate."""

    period: str
    main_arguments: list[str] = field(default_factory=list)
    counter_arguments: list[str] = field(default_factory=list)
    agreements: list[str] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    important_questions: list[str] = field(default_factory=list)
    position_changes: list[str] = field(default_factory=list)
    unresolved_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "period": self.period,
            "main_arguments": self.main_arguments,
            "counter_arguments": self.counter_arguments,
            "agreements": self.agreements,
            "disagreements": self.disagreements,
            "contradictions": self.contradictions,
            "important_questions": self.important_questions,
            "position_changes": self.position_changes,
            "unresolved_issues": self.unresolved_issues,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MidTermEntry:
        return cls(
            period=str(data.get("period", "unknown")),
            main_arguments=data.get("main_arguments", []) or [],
            counter_arguments=data.get("counter_arguments", []) or [],
            agreements=data.get("agreements", []) or [],
            disagreements=data.get("disagreements", []) or [],
            contradictions=data.get("contradictions", []) or [],
            important_questions=data.get("important_questions", []) or [],
            position_changes=data.get("position_changes", []) or [],
            unresolved_issues=data.get("unresolved_issues", []) or [],
        )


class MidTermMemory:
    """Stores structured summaries of recent debate sections."""

    def __init__(self) -> None:
        self._entries: list[MidTermEntry] = []

    def add(self, entry: MidTermEntry) -> None:
        """Add a mid-term memory entry."""
        self._entries.append(entry)
        # Keep last 20 entries to avoid unbounded growth
        if len(self._entries) > 20:
            self._entries = self._entries[-20:]

    def get_context(self) -> str:
        """Return a text representation of mid-term memory."""
        if not self._entries:
            return "(No mid-term memories yet.)"
        lines = ["MID-TERM MEMORY (section summaries):"]
        for entry in self._entries:
            lines.append(f"\n=== {entry.period} ===")
            if entry.main_arguments:
                lines.append("Main arguments:")
                for arg in entry.main_arguments[-5:]:
                    lines.append(f"  - {arg}")
            if entry.counter_arguments:
                lines.append("Counter-arguments:")
                for arg in entry.counter_arguments[-5:]:
                    lines.append(f"  - {arg}")
            if entry.contradictions:
                lines.append("Contradictions:")
                for c in entry.contradictions[-3:]:
                    lines.append(f"  ! {c}")
            if entry.important_questions:
                lines.append("Open questions:")
                for q in entry.important_questions[-3:]:
                    lines.append(f"  ? {q}")
            if entry.unresolved_issues:
                lines.append("Unresolved:")
                for u in entry.unresolved_issues[-3:]:
                    lines.append(f"  ~ {u}")
        return "\n".join(lines)

    def get_entries(self) -> list[MidTermEntry]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
