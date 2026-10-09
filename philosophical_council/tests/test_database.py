"""Tests for database layer."""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from philosophical_council.database.database import Database
from philosophical_council.database.schema import get_schema_sql


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return f.name


@pytest.fixture
def db(db_path):
    """Create a database instance."""
    return Database(db_path)


class TestDatabase:
    """Tests for the database layer."""

    def test_schema_creation(self, db):
        """Test that schema is created properly."""
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "debates" in table_names
        assert "turns" in table_names
        assert "memory_short" in table_names
        assert "memory_mid" in table_names
        assert "memory_long" in table_names
        conn.close()

    def test_create_debate(self, db):
        """Test creating a debate."""
        debate_id = db.debate_repo.create_debate("What is meaning?")
        debate = db.debate_repo.get_debate(debate_id)
        assert debate is not None
        assert debate["topic"] == "What is meaning?"
        assert debate["status"] == "idle"

    def test_insert_turn(self, db):
        """Test inserting a turn."""
        debate_id = db.debate_repo.create_debate("Test topic")
        turn_id = db.turn_repo.insert_turn(
            debate_id=debate_id,
            turn_id=1,
            round_num=1,
            speaker="Skeptic",
            speaker_role="skeptic",
            response="I question everything.",
            model="test-model",
        )
        assert turn_id > 0
        turns = db.turn_repo.get_turns(debate_id)
        assert len(turns) == 1
        assert turns[0]["speaker"] == "Skeptic"

    def test_search_turns(self, db):
        """Test searching turns."""
        debate_id = db.debate_repo.create_debate("Test topic")
        db.turn_repo.insert_turn(
            debate_id=debate_id,
            turn_id=1,
            round_num=1,
            speaker="Skeptic",
            speaker_role="skeptic",
            response="Consciousness is mysterious.",
        )
        results = db.turn_repo.search_turns(debate_id, "consciousness")
        assert len(results) == 1

    def test_save_memory(self, db):
        """Test saving memory entries."""
        debate_id = db.debate_repo.create_debate("Test topic")

        # Short-term
        db.memory_repo.save_short(debate_id, "Recent context", "turns 1-10")

        # Mid-term
        db.memory_repo.save_mid(debate_id, "period 1", {
            "main_arguments": ["Arg1"],
            "important_questions": ["Q1?"],
        })

        # Long-term
        db.memory_repo.save_long(debate_id, "key1", "category", "Content")

        # Verify retrieval
        short = db.memory_repo.get_recent_short(debate_id)
        assert len(short) == 1

        mid = db.memory_repo.get_mid(debate_id)
        assert len(mid) == 1

        long = db.memory_repo.get_long(debate_id)
        assert len(long) == 1

    def test_moderator_decision(self, db):
        """Test saving moderator decisions."""
        debate_id = db.debate_repo.create_debate("Test topic")
        db.moderator_repo.insert(
            debate_id=debate_id,
            turn_id=1,
            round_num=1,
            selected_speaker="Skeptic",
            challenge="Challenge text",
            reason="Reason text",
            question=None,
            detected_issues=None,
        )
        decisions = db.moderator_repo.get_recent(debate_id)
        assert len(decisions) == 1
        assert decisions[0]["selected_speaker"] == "Skeptic"
