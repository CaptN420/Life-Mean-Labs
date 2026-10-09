"""Tests for agents."""

from __future__ import annotations

import pytest

from philosophical_council.agents.existentialist import ExistentialistAgent
from philosophical_council.agents.stoic import StoicAgent
from philosophical_council.agents.nihilist import NihilistAgent
from philosophical_council.agents.spiritual import SpiritualAgent
from philosophical_council.agents.skeptic import SkepticAgent
from philosophical_council.agents.moderator import ModeratorAgent


class TestAgents:
    """Tests for philosophical agents."""

    def test_existentialist(self):
        agent = ExistentialistAgent()
        assert agent.name == "Existentialist"
        assert agent.role == "existentialist"
        assert agent.color == "#9370DB"
        assert "freedom" in agent.system_prompt.lower()

    def test_stoic(self):
        agent = StoicAgent()
        assert agent.name == "Stoic"
        assert agent.role == "stoic"
        assert "virtue" in agent.system_prompt.lower()

    def test_nihilist(self):
        agent = NihilistAgent()
        assert agent.name == "Nihilist"
        assert agent.role == "nihilist"
        # Nihilist should NOT automatically deny meaning
        assert "investigate" in agent.system_prompt.lower() or "question" in agent.system_prompt.lower()

    def test_spiritual(self):
        agent = SpiritualAgent()
        assert agent.name == "Spiritual"
        assert "consciousness" in agent.system_prompt.lower()

    def test_skeptic(self):
        agent = SkepticAgent()
        assert agent.name == "Skeptic"
        assert agent.role == "skeptic"
        assert "challenge" in agent.system_prompt.lower() or "contradiction" in agent.system_prompt.lower()

    def test_moderator(self):
        agent = ModeratorAgent()
        assert agent.name == "Moderator"
        assert agent.role == "moderator"
        # Should not participate as philosopher
        assert "moderator" in agent.system_prompt.lower()

    def test_agent_format_response(self):
        agent = ExistentialistAgent()
        prompt = agent.format_response("Test challenge", "Context here")
        assert "Test challenge" in prompt
        assert "Context here" in prompt
        assert "Existentialist" in prompt

    def test_agent_history(self):
        agent = StoicAgent()
        agent.add_to_history("First response")
        agent.add_to_history("Second response")
        history = agent.get_history()
        assert len(history) == 2
        assert history[0] == "First response"
