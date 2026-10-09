"""Long-term memory — persistent philosophical knowledge."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LongTermEntry:
    """A single persistent memory entry."""

    key: str
    category: Optional[str]
    content: str
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "category": self.category,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(self, data: dict[str, object]) -> LongTermEntry:
        return LongTermEntry(
            key=str(data.get("key", "")),
            category=data.get("category"),
            content=str(data.get("content", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


class LongTermMemory:
    """Persistent knowledge base that survives restarts."""

    def __init__(self) -> None:
        self._entries: dict[str, LongTermEntry] = {}

    def add(self, entry: LongTermEntry) -> None:
        """Add or update a long-term memory entry."""
        self._entries[entry.key] = entry

    def get(self, key: str) -> Optional[LongTermEntry]:
        return self._entries.get(key)

    def get_by_category(self, category: str) -> list[LongTermEntry]:
        return [e for e in self._entries.values() if e.category == category]

    def get_all(self) -> list[LongTermEntry]:
        return list(self._entries.values())

    def get_context(self) -> str:
        """Return a text representation of long-term memory."""
        if not self._entries:
            return "(No long-term memories yet.)"
        lines = ["LONG-TERM MEMORY (persistent knowledge):"]
        by_cat: dict[str, list[LongTermEntry]] = {}
        for entry in self._entries.values():
            cat = entry.category or "other"
            by_cat.setdefault(cat, []).append(entry)
        for cat, entries in sorted(by_cat.items()):
            lines.append(f"\n=== {cat.upper()} ===")
            for entry in entries:
                lines.append(f"[{entry.key}] {entry.content[:200]}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._entries.clear()

    @property
    def count(self) -> int:
        return len(self._entries)
