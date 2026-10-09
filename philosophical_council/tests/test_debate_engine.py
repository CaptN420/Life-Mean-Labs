"""Tests for debate engine."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock

from philosophical_council.core.debate_engine import DebateEngine
from philosophical_council.core.debate_state import DebateState
from philosophical_council.core.turn_manager import TurnManager


class TestDebateState:
    """Tests for DebateState."""

    def test_start(self):
        state = DebateState(topic="Test topic")
        state.start()
        assert state.status == "running"
        assert state.started_at is not None

    def test_pause_resume(self):
        state = DebateState()
        state.start()
        state.pause()
        assert state.status == "paused"
        state.resume()
        assert state.status == "running"

    def test_stop(self):
        state = DebateState()
        state.start()
        state.stop()
        assert state.status == "stopped"
        assert state.finished_at is not None

    def test_advance_turn(self):
        state = DebateState()
        turn_id = state.advance_turn()
        assert turn_id == 1
        assert state.total_turns == 1

    def test_serialize_deserialize(self):
        state = DebateState(topic="Test", status="running", turn_id=5)
        data = state.to_dict()
        restored = DebateState.from_dict(data)
        assert restored.topic == "Test"
        assert restored.turn_id == 5


class TestTurnManager:
    """Tests for TurnManager."""

    def test_next_turn(self):
        tm = TurnManager()
        turn = tm.next_turn("Skeptic", "skeptic")
        assert turn.speaker == "Skeptic"
        assert turn.turn_id == 1

    def test_complete_turn(self):
        tm = TurnManager()
        turn = tm.next_turn("Stoic", "stoic")
        tm.complete_turn(turn.turn_id, "Virtue is good", 5.0)
        assert turn.response == "Virtue is good"
        assert turn.duration_seconds == 5.0

    def test_get_recent(self):
        tm = TurnManager()
        for i in range(10):
            tm.next_turn(f"Agent{i}", "agent")
        recent = tm.get_recent_turns(5)
        assert len(recent) == 5
        assert recent[0].turn_id == 6

    def test_clear(self):
        tm = TurnManager()
        tm.next_turn("Test", "test")
        tm.clear()
        assert tm.turn_count == 0


class TestDebateEngine:
    """Tests for DebateEngine."""

    def test_init(self):
        config = Mock()
        config.debate.topic = "Test topic"
        config.debate.temperature = 0.8
        config.debate.max_tokens = 700
        config.models = Mock()
        config.models.existentialist = ""
        config.models.stoic = ""
        config.models.nihilist = ""
        config.models.spiritual = ""
        config.models.skeptic = ""
        config.models.moderator = ""

        db = Mock()
        llm = Mock()

        engine = DebateEngine(config, db, llm)
        assert engine.config == config
        assert engine.db == db
        assert engine.llm == llm

    def test_register_agent(self):
        config = Mock()
        config.debate.topic = "Test"
        config.debate.temperature = 0.8
        config.debate.max_tokens = 700
        config.models = Mock()
        for attr in ["existentialist", "stoic", "nihilist", "spiritual", "skeptic", "moderator"]:
            setattr(config.models, attr, "")

        engine = DebateEngine(config, Mock(), Mock())
        agent = Mock()
        agent.role = "test"
        engine.register_agent(agent)
        assert "test" in engine._agents

    def test_add_callback(self):
        config = Mock()
        config.debate.topic = "Test"
        config.debate.temperature = 0.8
        config.debate.max_tokens = 700
        config.models = Mock()
        for attr in ["existentialist", "stoic", "nihilist", "spiritual", "skeptic", "moderator"]:
            setattr(config.models, attr, "")

        engine = DebateEngine(config, Mock(), Mock())
        callback = Mock()
        engine.add_callback(callback)
        assert callback in engine._callbacks
