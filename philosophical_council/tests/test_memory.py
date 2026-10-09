"""Tests for memory system."""

from __future__ import annotations

import pytest
from philosophical_council.memory.short_term import ShortTermMemory
from philosophical_council.memory.mid_term import MidTermEntry, MidTermMemory
from philosophical_council.memory.long_term import LongTermEntry, LongTermMemory


class TestShortTermMemory:
    """Tests for ShortTermMemory."""

    def test_add_and_retrieve(self) -> None:
        stm = ShortTermMemory(capacity=5)
        stm.add(1, 1, "Skeptic", "Test challenge?", "Response text")
        assert stm.count == 1
        context = stm.get_context()
        assert "Skeptic" in context
        assert "Response text" in context

    def test_capacity_limit(self) -> None:
        stm = ShortTermMemory(capacity=3)
        for i in range(5):
            stm.add(i, 1, f"Agent{i}", None, f"Response {i}")
        assert stm.count == 3
        context = stm.get_context()
        assert "Response 2" in context
        assert "Response 4" in context
        assert "Response 0" not in context

    def test_empty_context(self) -> None:
        stm = ShortTermMemory()
        context = stm.get_context()
        assert "No recent turns" in context

    def test_clear(self) -> None:
        stm = ShortTermMemory()
        stm.add(1, 1, "Test", None, "Response")
        stm.clear()
        assert stm.count == 0


class TestMidTermMemory:
    """Tests for MidTermMemory."""

    def test_add_entry(self) -> None:
        mtm = MidTermMemory()
        entry = MidTermEntry(
            period="turns 1-10",
            main_arguments=["Argument 1"],
            important_questions=["Question 1?"],
        )
        mtm.add(entry)
        assert mtm.get_context() != "(No mid-term memories yet.)"

    def test_get_entries(self) -> None:
        mtm = MidTermMemory()
        entry = MidTermEntry(period="test")
        mtm.add(entry)
        entries = mtm.get_entries()
        assert len(entries) == 1
        assert entries[0].period == "test"

    def test_clear(self) -> None:
        mtm = MidTermMemory()
        mtm.add(MidTermEntry(period="test"))
        mtm.clear()
        assert mtm.get_context() == "(No mid-term memories yet.)"


class TestLongTermMemory:
    """Tests for LongTermMemory."""

    def test_add_and_retrieve(self) -> None:
        ltm = LongTermMemory()
        entry = LongTermEntry(key="test_key", category="question", content="What is meaning?")
        ltm.add(entry)
        assert ltm.count == 1
        retrieved = ltm.get("test_key")
        assert retrieved is not None
        assert retrieved.content == "What is meaning?"

    def test_get_by_category(self) -> None:
        ltm = LongTermMemory()
        ltm.add(LongTermEntry(key="q1", category="question", content="Q1"))
        ltm.add(LongTermEntry(key="a1", category="argument", content="A1"))
        questions = ltm.get_by_category("question")
        assert len(questions) == 1
        assert questions[0].key == "q1"

    def test_clear(self) -> None:
        ltm = LongTermMemory()
        ltm.add(LongTermEntry(key="test", category="cat", content="content"))
        ltm.clear()
        assert ltm.count == 0
