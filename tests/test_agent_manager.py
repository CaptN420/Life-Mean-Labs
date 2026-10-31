"""Tests for AgentManager."""

import pytest
import json
from life_mean_studio.engine.agent_manager import AgentManager, TestResult
from life_mean_studio.engine.storage import StudioStorage


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test_agents.db"
    return StudioStorage(db_path=str(db_path))


@pytest.fixture
def agent_manager(storage):
    return AgentManager(storage)


class TestAgentCRUD:
    def test_create_agent(self, agent_manager):
        result = agent_manager.create(
            name="Test Agent",
            system_prompt="You are a test agent.",
            persona="researcher",
        )
        assert result.success
        assert "id" in result.data

    def test_list_agents(self, agent_manager):
        agent_manager.create(name="Agent A", system_prompt="Prompt A")
        agents = agent_manager.list_all()
        assert len(agents) >= 1

    def test_get_agent(self, agent_manager):
        result = agent_manager.create(name="Get Me", system_prompt="Hello")
        agent = agent_manager.get(result.data["id"])
        assert agent is not None
        assert agent["name"] == "Get Me"

    def test_update_agent(self, agent_manager):
        result = agent_manager.create(name="Update Me", system_prompt="Original")
        update_result = agent_manager.update(result.data["id"], {"name": "Updated"})
        assert update_result.success
        agent = agent_manager.get(result.data["id"])
        assert agent["name"] == "Updated"

    def test_delete_agent(self, agent_manager):
        result = agent_manager.create(name="Delete Me", system_prompt="Bye")
        delete_result = agent_manager.delete(result.data["id"])
        assert delete_result.success
        assert agent_manager.get(result.data["id"]) is None

    def test_duplicate_agent(self, agent_manager):
        result = agent_manager.create(name="Original", system_prompt="Content")
        dup_result = agent_manager.duplicate(result.data["id"])
        assert dup_result.success
        original = agent_manager.get(result.data["id"])
        duplicate = agent_manager.get(dup_result.data["id"])
        assert original is not None
        assert duplicate is not None
        assert original["system_prompt"] == duplicate["system_prompt"]
        assert original["name"] != duplicate["name"]

    def test_search_agents(self, agent_manager):
        agent_manager.create(name="Search Test", system_prompt="Find me")
        results = agent_manager.search("Search")
        assert len(results) >= 1
        assert any(r["name"] == "Search Test" for r in results)


class TestAgentConfig:
    def test_create_with_config(self, agent_manager):
        result = agent_manager.create(
            name="Configured Agent",
            system_prompt="You are configured.",
            model="qwen3.5-2b",
            provider="lm-studio",
            config={"temperature": 0.7},
        )
        assert result.success
        agent = agent_manager.get(result.data["id"])
        assert agent["model"] == "qwen3.5-2b"
        assert agent["provider"] == "lm-studio"
        assert agent["config"] == {"temperature": 0.7}

    def test_toggle_enabled(self, agent_manager):
        result = agent_manager.create(name="Enabled Agent", system_prompt="Hi")
        agent_manager.update(result.data["id"], {"enabled": False})
        agent = agent_manager.get(result.data["id"])
        assert not agent["enabled"]
        assert len(agent_manager.list_all(enabled_only=True)) == 0
