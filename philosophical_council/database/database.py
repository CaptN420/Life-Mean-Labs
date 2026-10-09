"""SQLite database wrapper with schema initialization."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .repositories import (
    DebateRepository,
    EventRepository,
    MemoryRepository,
    ModeratorDecisionRepository,
    TurnRepository,
)
from .schema import get_schema_sql

logger = logging.getLogger(__name__)


class Database:
    """Manages the SQLite connection and exposes repositories."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self.debate_repo = DebateRepository(db_path)
        self.turn_repo = TurnRepository(db_path)
        self.memory_repo = MemoryRepository(db_path)
        self.moderator_repo = ModeratorDecisionRepository(db_path)
        self.event_repo = EventRepository(db_path)

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(get_schema_sql())
            logger.info("Database schema initialized at %s", self.db_path)
        finally:
            conn.close()

    def close(self) -> None:
        pass  # SQLite connections are per-request now


def create_database(db_path: str) -> Database:
    """Factory to create a Database instance."""
    return Database(db_path)
