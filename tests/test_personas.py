"""Tests for the unified persona management system."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.personas.manager import PersonaManager, PersonaValidationError
from core.personas.schema import DebateSessionConfig, ModelHealth, ModelSpec, PersonaConfig, PersonaType, ProviderType


class TestPersonaConfig:
    """Tests for PersonaConfig dataclass."""

    def test_create_valid_persona(self):
        persona = PersonaConfig(
            role_id="test_role",
            name="Test Role",
            persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
            description="A test persona",
            system_prompt="You are a philosopher.",
            color="#FF0000",
        )
        assert persona.role_id == "test_role"
        assert persona.name == "Test Role"
        assert persona.persona_type == PersonaType.ANALYTICAL_PHILOSOPHER
        assert persona.color == "#FF0000"

    def test_content_hash_deterministic(self):
        p1 = PersonaConfig(
            role_id="test",
            name="Test",
            persona_type=PersonaType.SKEPTIC,
            description="Desc",
            system_prompt="Prompt",
        )
        p2 = PersonaConfig(
            role_id="test",
            name="Test",
            persona_type=PersonaType.SKEPTIC,
            description="Desc",
            system_prompt="Prompt",
        )
        assert p1.content_hash() == p2.content_hash()

    def test_to_dict_roundtrip(self):
        original = PersonaConfig(
            role_id="test_role",
            name="Test",
            persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
            description="Desc",
            system_prompt="Prompt",
            color="#FF0000",
        )
        data = original.to_dict()
        restored = PersonaConfig.from_dict(data)
        assert restored.role_id == original.role_id
        assert restored.name == original.name
        assert restored.persona_type == original.persona_type
        assert restored.system_prompt == original.system_prompt


class TestPersonaManager:
    """Tests for PersonaManager."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = PersonaManager(storage_path=Path(self.tmpdir) / "personas.json")

    def test_create_persona(self):
        persona = self.manager.create_persona(
            role_id="philosopher",
            name="Philosopher",
            persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
            description="A philosopher",
            system_prompt="You are wise.",
        )
        assert persona.role_id == "philosopher"
        assert len(self.manager.list_personas()) == 1

    def test_get_persona(self):
        self.manager.create_persona(
            role_id="test",
            name="Test",
            persona_type=PersonaType.SKEPTIC,
            description="Desc",
            system_prompt="Prompt",
        )
        persona = self.manager.get_persona("test")
        assert persona is not None
        assert persona.name == "Test"

    def test_get_nonexistent_persona(self):
        assert self.manager.get_persona("nonexistent") is None

    def test_update_persona(self):
        self.manager.create_persona(
            role_id="test",
            name="Original",
            persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
            description="Desc",
            system_prompt="Prompt",
        )
        updated = self.manager.update_persona(
            role_id="test",
            name="Updated",
            color="#00FF00",
        )
        assert updated.name == "Updated"
        assert updated.color == "#00FF00"

    def test_delete_persona(self):
        self.manager.create_persona(
            role_id="test",
            name="Test",
            persona_type=PersonaType.SKEPTIC,
            description="Desc",
            system_prompt="Prompt",
        )
        assert self.manager.delete_persona("test") is True
        assert self.manager.get_persona("test") is None

    def test_delete_nonexistent(self):
        assert self.manager.delete_persona("nonexistent") is False

    def test_validate_persona_valid(self):
        self.manager.create_persona(
            role_id="test",
            name="Test",
            persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
            description="A valid persona",
            system_prompt="You are a philosopher.",
        )
        result = self.manager.validate_persona("test")
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_persona_not_found(self):
        result = self.manager.validate_persona("nonexistent")
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_persist_and_reload(self):
        self.manager.create_persona(
            role_id="test",
            name="Test",
            persona_type=PersonaType.SKEPTIC,
            description="Desc",
            system_prompt="Prompt",
        )
        # Create new manager pointing to same file
        new_manager = PersonaManager(storage_path=Path(self.tmpdir) / "personas.json")
        assert new_manager.get_persona("test") is not None
        assert new_manager.get_persona("test").name == "Test"


class TestDebateSessionConfig:
    """Tests for DebateSessionConfig."""

    def test_create_valid_config(self):
        config = DebateSessionConfig(
            topic="What is the meaning of life?",
            personas=["existentialist", "stoic"],
            model_pool=["model1", "model2"],
            max_turns=20,
        )
        assert config.topic == "What is the meaning of life?"
        assert len(config.personas) == 2

    def test_empty_topic_rejected(self):
        with pytest.raises(ValueError, match="topic must not be empty"):
            DebateSessionConfig(topic="")

    def test_invalid_routing_method(self):
        with pytest.raises(ValueError, match="invalid routing_method"):
            DebateSessionConfig(topic="Test", routing_method="invalid")

    def test_session_id_format(self):
        config = DebateSessionConfig(topic="Test topic")
        assert config.session_id.startswith("debate_")

    def test_to_dict_roundtrip(self):
        original = DebateSessionConfig(
            topic="Test",
            personas=["p1", "p2"],
            model_pool=["m1"],
            max_turns=10,
            routing_method="round_robin",
        )
        data = original.to_dict()
        restored = DebateSessionConfig.from_dict(data)
        assert restored.topic == original.topic
        assert restored.personas == original.personas
        assert restored.routing_method == original.routing_method


class TestModelSpec:
    """Tests for ModelSpec."""

    def test_create_model(self):
        spec = ModelSpec(
            model_id="llama-7b",
            provider=ProviderType.LOCAL,
            endpoint="http://localhost:1234/v1",
            context_window=8192,
        )
        assert spec.is_local
        assert not spec.is_available  # UNKNOWN health

    def test_record_success(self):
        spec = ModelSpec(
            model_id="test",
            provider=ProviderType.LOCAL,
        )
        spec.record_success(latency_ms=100.0)
        assert spec.avg_latency_ms == 10.0
        assert spec.total_requests == 1
        assert spec.health == ModelHealth.HEALTHY

    def test_record_failure(self):
        spec = ModelSpec(
            model_id="test",
            provider=ProviderType.LOCAL,
        )
        for _ in range(10):
            spec.record_failure()
        assert spec.success_rate < 0.5
        assert spec.health == ModelHealth.UNHEALTHY

    def test_to_dict_roundtrip(self):
        original = ModelSpec(
            model_id="llama-7b",
            provider=ProviderType.LOCAL,
            context_window=8192,
            tags=["local", "7b"],
        )
        data = original.to_dict()
        restored = ModelSpec.from_dict(data)
        assert restored.model_id == original.model_id
        assert restored.provider == original.provider
        assert restored.tags == original.tags
