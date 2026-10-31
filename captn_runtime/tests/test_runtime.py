"""CaptN Runtime v1 — Tests."""

from __future__ import annotations

import pytest
from captn.runtime import CaptNRuntime, RuntimeConfig, RuntimeResult


class TestRuntimeConfig:
    def test_default_config(self):
        config = RuntimeConfig()
        assert config.default_model == "deepseek/deepseek-v4-flash"
        assert config.compression_enabled is True
        assert config.memory_enabled is True

    def test_custom_config(self):
        config = RuntimeConfig(
            default_model="openai/gpt-4",
            compression_enabled=False,
        )
        assert config.default_model == "openai/gpt-4"
        assert config.compression_enabled is False


class TestModelRouter:
    def test_route_coding(self):
        runtime = CaptNRuntime()
        model = runtime.router.route("Write a Python function", task_type="coding")
        assert "coder" in model or "gpt-4" in model

    def test_route_analysis(self):
        runtime = CaptNRuntime()
        model = runtime.router.route("Analyze this data", task_type="analysis")
        assert model

    def test_stats(self):
        runtime = CaptNRuntime()
        stats = runtime.router.stats()
        assert "routes" in stats
        assert "usage" in stats


class TestContextEngine:
    def test_compress_short_messages(self):
        config = RuntimeConfig(compression_enabled=True)
        engine = ContextEngine(config)
        messages = [{"role": "user", "content": "Hello"}]
        result = engine.compress(messages, 1000)
        assert result["compressed"] is False

    def test_compress_long_messages(self):
        config = RuntimeConfig(compression_enabled=True)
        engine = ContextEngine(config)
        messages = [{"role": "user", "content": f"Message {i}"} for i in range(20)]
        result = engine.compress(messages, 1000)
        assert result["compressed"] is True
        assert result["reduction"] > 0

    def test_history(self):
        config = RuntimeConfig()
        engine = ContextEngine(config)
        engine.add_to_history("user", "Hello")
        engine.add_to_history("assistant", "Hi")
        history = engine.get_history()
        assert len(history) == 2


class TestExperienceEngine:
    def test_store_and_retrieve(self):
        config = RuntimeConfig(experience_enabled=True)
        engine = ExperienceEngine(config)
        exp_id = engine.store_experience("test query", "test response", RuntimeResult())
        exp = engine.get_experience(exp_id)
        assert exp is not None
        assert exp["query"] == "test query"

    def test_find_similar(self):
        config = RuntimeConfig(experience_enabled=True)
        engine = ExperienceEngine(config)
        engine.store_experience("Python coding task", "response", RuntimeResult())
        similar = engine.find_similar("Python programming")
        assert len(similar) > 0

    def test_stats(self):
        config = RuntimeConfig()
        engine = ExperienceEngine(config)
        stats = engine.stats()
        assert "total_experiences" in stats


class TestTelemetryEngine:
    def test_record_event(self):
        config = RuntimeConfig(telemetry_enabled=True)
        telemetry = TelemetryEngine(config)
        event = TelemetryEvent(event_type="request", query_hash="test")
        telemetry.record_event(event)
        stats = telemetry.get_stats()
        assert stats["total_events"] == 1

    def test_save_to_disk(self, tmp_path):
        config = RuntimeConfig(telemetry_enabled=True)
        telemetry = TelemetryEngine(config)
        telemetry.record_event(TelemetryEvent(event_type="request"))
        path = tmp_path / "telemetry.jsonl"
        count = telemetry.save_to_disk(str(path))
        assert count == 1
        assert path.exists()


class TestCaptNRuntime:
    def test_run(self):
        runtime = CaptNRuntime()
        result = asyncio.run(runtime.run("Test query"))
        assert result.success
        assert result.model_used

    def test_get_status(self):
        runtime = CaptNRuntime()
        status = runtime.get_status()
        assert "config" in status
        assert "routing" in status
        assert "experience" in status
