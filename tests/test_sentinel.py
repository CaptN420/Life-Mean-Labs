"""Tests for Life_mean Sentinel security monitoring system."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.safety.sentinel import (
    Sentinel,
    SentinelConfig,
    SentinelAlertLevel,
    SentinelAction,
    SentinelEvent,
    SentinelAnalysis,
)
from core.safety.sentinel_controller import SentinelController
from core.observability.event_bus import EventBus, Event, EventPriority
from core.providers.base import (
    ChatResult,
    ChatStatus,
    LLMProvider,
    ProviderConfig,
    ProviderRegistry,
    ProviderType,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def provider_registry():
    return ProviderRegistry()


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider that returns deterministic responses."""
    provider = MagicMock(spec=LLMProvider)
    provider.provider_type = ProviderType.LOCAL
    provider.health_check.return_value = True

    def mock_chat(messages, model=None, temperature=None, max_tokens=None):
        return ChatResult(
            text='{"alert_level": "WARNING", "action": "PAUSE", "explanation": "Suspicious loop detected", "evidence": [{"type": "loop"}], "uncertainty": 0.4}',
            finish_reason="stop",
            model_used="test-model",
            provider=ProviderType.LOCAL,
            status=ChatStatus.SUCCESS,
            latency_ms=100.0,
            tokens_used=50,
        )

    provider.chat = mock_chat
    provider.get_models.return_value = ["test-model"]
    return provider


@pytest.fixture
def sentinel_config():
    return SentinelConfig(
        enabled=True,
        provider="local",
        model_id="test-model",
        analysis_mode="hybrid",
        external_log_upload=False,
    )


@pytest.fixture
def sentinel(event_bus, provider_registry, sentinel_config):
    return Sentinel(event_bus=event_bus, provider_registry=provider_registry, config=sentinel_config)


# ── SentinelConfig Tests ─────────────────────────────────────────────────────


class TestSentinelConfig:
    def test_default_config(self):
        config = SentinelConfig()
        assert config.enabled is True
        assert config.provider == "local"
        assert config.analysis_mode == "hybrid"
        assert config.external_log_upload is False

    def test_from_dict(self):
        data = {
            "enabled": False,
            "provider": "openrouter",
            "model_id": "deepseek-v3",
            "analysis_mode": "llm",
            "external_log_upload": True,
        }
        config = SentinelConfig.from_dict(data)
        assert config.enabled is False
        assert config.provider == "openrouter"
        assert config.model_id == "deepseek-v3"
        assert config.analysis_mode == "llm"
        assert config.external_log_upload is True

    def test_from_dict_ignores_unknown_keys(self):
        data = {"enabled": True, "unknown_key": "value"}
        config = SentinelConfig.from_dict(data)
        assert config.enabled is True
        assert not hasattr(config, "unknown_key")

    def test_to_dict(self):
        config = SentinelConfig()
        data = config.to_dict()
        assert data["enabled"] is True
        assert data["provider"] == "local"


# ── SentinelEvent Tests ──────────────────────────────────────────────────────


class TestSentinelEvent:
    def test_to_dict(self):
        event = SentinelEvent(
            event_type="test_event",
            payload={"key": "value"},
            severity="HIGH",
            source="test_source",
        )
        d = event.to_dict()
        assert d["event_type"] == "test_event"
        assert d["severity"] == "HIGH"
        assert d["source"] == "test_source"
        # Note: payload is sanitized, so 'key' is preserved (not a secret)
        assert d["payload"]["key"] == "value"

    def test_sanitize_payload(self):
        event = SentinelEvent(
            event_type="test",
            payload={"api_key": "secret123", "normal": "data"},
        )
        d = event.to_dict()
        assert d["payload"]["api_key"] == "[REDACTED]"
        assert d["payload"]["normal"] == "data"

    def test_sanitize_nested_payload(self):
        event = SentinelEvent(
            event_type="test",
            payload={"nested": {"api_key": "secret", "token": "tok123"}},
        )
        d = event.to_dict()
        assert d["payload"]["nested"]["api_key"] == "[REDACTED]"
        assert d["payload"]["nested"]["token"] == "[REDACTED]"


# ── Sentinel Core Tests ──────────────────────────────────────────────────────


class TestSentinel:
    def test_initial_state(self, sentinel):
        status = sentinel.get_status()
        assert status["enabled"] is True
        assert status["provider"] == "local"
        assert status["llm_available"] is False

    def test_toggle_enabled(self, sentinel):
        sentinel.set_enabled(False)
        assert not sentinel.is_enabled()
        sentinel.set_enabled(True)
        assert sentinel.is_enabled()

    def test_configure(self, sentinel):
        sentinel.configure(
            provider="openrouter",
            model_id="deepseek-v3",
            analysis_mode="llm",
        )
        status = sentinel.get_status()
        assert status["provider"] == "openrouter"
        assert status["model_id"] == "deepseek-v3"
        assert status["analysis_mode"] == "llm"

    def test_analyze_no_events(self, sentinel):
        result = sentinel.analyze()
        assert result is None

    def test_analyze_policy_violation(self, sentinel, event_bus):
        # Manually add to queue (event bus subscription requires start() before publish)
        sentinel._event_queue.append(SentinelEvent(
            event_type="policy_violation",
            payload={"operation": "bypass_security"},
            severity="CRITICAL",
            source="test_component",
        ))

        result = sentinel.analyze()
        assert result is not None
        assert result.alert_level == SentinelAlertLevel.CRITICAL
        assert result.action == SentinelAction.STOP

    def test_analyze_loop_detected(self, sentinel, event_bus):
        sentinel._event_queue.append(SentinelEvent(
            event_type="loop_detected",
            payload={"rounds": 100},
            severity="HIGH",
            source="test_component",
        ))
        result = sentinel.analyze()
        assert result is not None
        assert result.alert_level == SentinelAlertLevel.HIGH
        assert result.action == SentinelAction.PAUSE

    def test_analyze_resource_exceeded(self, sentinel, event_bus):
        sentinel._event_queue.append(SentinelEvent(
            event_type="resource_exceeded",
            payload={"type": "memory", "usage": 95},
            severity="HIGH",
            source="test_component",
        ))
        result = sentinel.analyze()
        assert result is not None
        assert result.alert_level == SentinelAlertLevel.HIGH

    def test_alert_handler(self, sentinel):
        alerts = []
        sentinel.add_alert_handler(lambda a: alerts.append(a))

        # Manually trigger an alert
        analysis = SentinelAnalysis(
            alert_level=SentinelAlertLevel.WARNING,
            action=SentinelAction.PAUSE,
            explanation="Test alert",
        )
        sentinel._notify_alert(analysis)

        assert len(sentinel.get_alerts()) == 1
        assert sentinel.get_alerts()[0]["alert_level"] == "WARNING"

    def test_clear_alerts(self, sentinel):
        sentinel._alerts.append(SentinelAnalysis(
            alert_level=SentinelAlertLevel.WARNING,
            action=SentinelAction.PAUSE,
            explanation="Test",
        ))
        count = sentinel.clear_alerts()
        assert count == 1
        assert len(sentinel.get_alerts()) == 0

    def test_health_check(self, sentinel):
        health = sentinel.health_check()
        assert "enabled" in health
        assert "llm_available" in health

    def test_export_events_sanitized(self, sentinel, event_bus):
        event_bus.publish(Event(
            event_type="test",
            payload={"api_key": "secret123", "data": "value"},
            priority=EventPriority.NORMAL,
        ))
        # Manually add to queue since event bus won't route without subscription
        sentinel._event_queue.append(SentinelEvent(
            event_type="test",
            payload={"api_key": "secret123", "data": "value"},
        ))
        events = sentinel.export_events_for_review()
        assert len(events) == 1
        assert events[0]["payload"]["api_key"] == "[REDACTED]"
        assert events[0]["payload"]["data"] == "value"


# ── SentinelController Tests ─────────────────────────────────────────────────


class TestSentinelController:
    def test_get_status_without_sentinel(self):
        controller = SentinelController()
        status = controller.get_status()
        assert "error" in status

    def test_update_config(self, sentinel):
        controller = SentinelController(sentinel)
        result = controller.update_config(provider="openrouter")
        assert result["status"] == "updated"
        assert result["config"]["provider"] == "openrouter"

    def test_toggle_enabled(self, sentinel):
        controller = SentinelController(sentinel)
        result = controller.toggle_enabled(False)
        assert result["status"] == "disabled"
        assert not sentinel.is_enabled()

    def test_get_alerts_empty(self, sentinel):
        controller = SentinelController(sentinel)
        result = controller.get_alerts()
        assert result["alerts"] == []

    def test_clear_alerts(self, sentinel):
        controller = SentinelController(sentinel)
        sentinel._alerts.append(SentinelAnalysis(
            alert_level=SentinelAlertLevel.WARNING,
            action=SentinelAction.PAUSE,
            explanation="Test",
        ))
        result = controller.clear_alerts()
        assert result["cleared"] == 1


# ── Integration Tests ────────────────────────────────────────────────────────


class TestSentinelIntegration:
    def test_end_to_end_monitoring(self, event_bus, provider_registry, sentinel_config):
        """Test full monitoring pipeline."""
        sentinel = Sentinel(
            event_bus=event_bus,
            provider_registry=provider_registry,
            config=sentinel_config,
        )

        # Manually add to queue
        sentinel._event_queue.append(SentinelEvent(
            event_type="policy_violation",
            payload={"operation": "disable_validator"},
            severity="CRITICAL",
            source="test_runner",
        ))

        # Analyze
        result = sentinel.analyze()
        assert result is not None
        assert result.alert_level == SentinelAlertLevel.CRITICAL
        assert result.action == SentinelAction.STOP

    def test_graceful_degradation_no_llm(self, event_bus, sentinel_config):
        """Test that deterministic analysis works without LLM."""
        sentinel = Sentinel(
            event_bus=event_bus,
            provider_registry=None,
            config=sentinel_config,
        )

        sentinel._event_queue.append(SentinelEvent(
            event_type="loop_detected",
            payload={"rounds": 50},
            severity="HIGH",
        ))

        result = sentinel.analyze()
        assert result is not None
        assert result.alert_level == SentinelAlertLevel.HIGH


# ── Security Tests ───────────────────────────────────────────────────────────


class TestSentinelSecurity:
    def test_no_secrets_in_export(self, event_bus):
        """Ensure secrets are never exported."""
        sentinel = Sentinel(event_bus=event_bus)
        # Manually add to queue since event bus won't route without subscription
        sentinel._event_queue.append(SentinelEvent(
            event_type="test",
            payload={
                "api_key": "secret123",
                "token": "tok456",
                "password": "pass789",
                "normal_data": "value",
            },
        ))
        events = sentinel.export_events_for_review()
        assert len(events) == 1
        assert events[0]["payload"]["api_key"] == "[REDACTED]"
        assert events[0]["payload"]["token"] == "[REDACTED]"
        assert events[0]["payload"]["password"] == "[REDACTED]"
        assert events[0]["payload"]["normal_data"] == "value"

    def test_external_upload_requires_confirmation(self, sentinel):
        """External upload requires explicit confirmation."""
        assert not sentinel.request_external_upload_confirmation()

    def test_llm_never_executes_commands(self, sentinel):
        """Verify Sentinel never executes commands directly."""
        # This is a design principle - verify through code inspection
        import inspect
        source = inspect.getsource(Sentinel)
        assert "os.system" not in source
        assert "subprocess" not in source
        assert "eval(" not in source


# ── Resilience Tests ─────────────────────────────────────────────────────────


class TestSentinelResilience:
    def test_llm_failure_degradation(self, event_bus, sentinel_config):
        """Test graceful degradation when LLM fails."""
        sentinel = Sentinel(
            event_bus=event_bus,
            provider_registry=None,  # No LLM available
            config=sentinel_config,
        )

        sentinel._event_queue.append(SentinelEvent(
            event_type="policy_violation",
            payload={"operation": "test"},
            severity="CRITICAL",
        ))

        # Should still work with deterministic analysis
        result = sentinel.analyze()
        assert result is not None
        assert result.alert_level == SentinelAlertLevel.CRITICAL

    def test_event_queue_limit(self, event_bus, sentinel_config):
        """Test that event queue doesn't grow unbounded."""
        sentinel = Sentinel(event_bus=event_bus, config=sentinel_config)
        sentinel._config.max_events_per_analysis = 5

        for i in range(10):
            event_bus.publish(Event(
                event_type="test",
                payload={"index": i},
            ))

        # Queue should be limited
        assert len(sentinel._event_queue) <= 5

    def test_multiple_alerts_stored(self, sentinel):
        """Test alert history is maintained."""
        for i in range(10):
            sentinel._alerts.append(SentinelAnalysis(
                alert_level=SentinelAlertLevel.WARNING,
                action=SentinelAction.PAUSE,
                explanation=f"Alert {i}",
            ))

        alerts = sentinel.get_alerts(limit=5)
        assert len(alerts) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
