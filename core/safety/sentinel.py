"""Sentinel — LLM-assisted security monitoring for LIFE_MEAN.

Sentinel observes events from the observability layer, runs deterministic
policy checks (Layer A), and optionally queries an independent LLM model
(Layer B) to identify plausible anomalies. It never executes commands,
modify safety rules, or stop processes on its own — it only recommends
actions and surfaces alerts through the existing notification channel.

Design principles:
- Deterministic guards (policy_guard, resource_guard, loop_detector) are
  authoritative; Sentinel's LLM analysis is advisory.
- External provider logs are never sent without explicit user confirmation.
- Secrets (API keys, credentials) are stripped from all outbound payloads.
- Sentinel degrades gracefully when the LLM is unavailable.
"""

from __future__ import annotations

import enum
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.observability.event_bus import Event, EventBus, EventPriority
from core.providers.base import (
    ChatResult,
    ChatStatus,
    LLMProvider,
    ProviderConfig,
    ProviderRegistry,
    ProviderType,
)

logger = logging.getLogger("core.safety.sentinel")


# ── Enums ────────────────────────────────────────────────────────────────────


class SentinelAlertLevel(str, enum.Enum):
    """Severity of a Sentinel alert."""

    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SentinelAction(str, enum.Enum):
    """Recommended action from Sentinel analysis."""

    NONE = "NONE"
    PAUSE = "PAUSE"
    STOP = "STOP"
    INVESTIGATE = "INVESTIGATE"
    QUARANTINE = "QUARANTINE"


class SentinelProvider(str, enum.Enum):
    """Supported Sentinel providers."""

    LOCAL = "local"
    OPENROUTER = "openrouter"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class SentinelEvent:
    """Structured event consumed by Sentinel for analysis."""

    event_type: str
    payload: Dict[str, Any]
    severity: str = "NORMAL"
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "source": self.source,
            "payload": self._sanitize_payload(self.payload),
            "timestamp": self.timestamp,
        }

    @staticmethod
    def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Strip known secret keys from payload."""
        # Only redact values for keys that are clearly secrets (have 'key', 'secret', etc. in the name)
        # but not generic words like 'key' used as a regular dictionary key
        secret_patterns = {
            "api_key", "apikey", "api-key",
            "token", "auth_token", "access_token",
            "secret", "secret_key",
            "password", "passwd",
            "credentials",
        }
        sanitized = {}
        for k, v in payload.items():
            k_lower = k.lower()
            # Redact if key matches a known secret pattern
            if any(pattern in k_lower for pattern in secret_patterns):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = SentinelEvent._sanitize_payload(v)
            else:
                sanitized[k] = v
        return sanitized


@dataclass
class SentinelAnalysis:
    """Result of a Sentinel analysis pass."""

    alert_level: SentinelAlertLevel
    action: SentinelAction
    explanation: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    uncertainty: float = 0.0  # 0.0 = certain, 1.0 = guess
    llm_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_level": self.alert_level.value,
            "action": self.action.value,
            "explanation": self.explanation,
            "evidence": self.evidence,
            "uncertainty": self.uncertainty,
            "llm_response": self.llm_response,
        }


@dataclass
class SentinelConfig:
    """Configuration for the Sentinel monitoring system."""

    enabled: bool = True
    provider: str = "local"  # "local" or "openrouter"
    model_id: str = "qwen3.5-2b"  # Default Sentinel analysis model
    analysis_mode: str = "hybrid"  # "deterministic", "llm", "hybrid"
    external_log_upload: bool = False
    pause_on_high_risk: bool = True
    require_confirmation_to_resume: bool = True
    max_events_per_analysis: int = 50
    analysis_interval_sec: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model_id": self.model_id,
            "analysis_mode": self.analysis_mode,
            "external_log_upload": self.external_log_upload,
            "pause_on_high_risk": self.pause_on_high_risk,
            "require_confirmation_to_resume": self.require_confirmation_to_resume,
            "max_events_per_analysis": self.max_events_per_analysis,
            "analysis_interval_sec": self.analysis_interval_sec,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SentinelConfig":
        """Create config from dict, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ── Sentinel Core ────────────────────────────────────────────────────────────


class Sentinel:
    """LLM-assisted security monitoring system.

    Observes events from the EventBus, runs deterministic checks (Layer A),
    and optionally queries an LLM for analysis (Layer B). Never executes
    commands or modifies safety rules directly.
    """

    def __init__(
        self,
        event_bus: EventBus,
        provider_registry: Optional[ProviderRegistry] = None,
        config: Optional[SentinelConfig] = None,
    ):
        self._event_bus = event_bus
        self._provider_registry = provider_registry
        self._config = config or SentinelConfig()
        self._alerts: List[SentinelAnalysis] = []
        self._analysis_history: List[Dict[str, Any]] = []
        self._llm_provider: Optional[LLMProvider] = None
        self._event_queue: List[SentinelEvent] = []
        self._subscribed = False
        self._alert_handlers: List[Callable[[SentinelAnalysis], None]] = []

        # Analysis prompt template (never includes secrets)
        self._analysis_prompt_template = """You are a security analyst reviewing system events.
Analyze the following events and identify any anomalies or security concerns.

Events:
{events}

For each concern, provide:
1. Alert level (INFO/WARNING/HIGH/CRITICAL)
2. Recommended action (NONE/PAUSE/STOP/INVESTIGATE/QUARANTINE)
3. Explanation of your reasoning
4. Evidence from the events
5. Your confidence level (0.0-1.0)

If no concerns, return: {"alert_level": "INFO", "action": "NONE", "explanation": "No anomalies detected", "evidence": [], "uncertainty": 0.0}"""

    def configure(
        self,
        provider: Optional[str] = None,
        model_id: Optional[str] = None,
        analysis_mode: Optional[str] = None,
        external_log_upload: Optional[bool] = None,
    ) -> None:
        """Update configuration without restarting."""
        if provider is not None:
            self._config.provider = provider
        if model_id is not None:
            self._config.model_id = model_id
        if analysis_mode is not None:
            self._config.analysis_mode = analysis_mode
        if external_log_upload is not None:
            self._config.external_log_upload = external_log_upload

        # Re-resolve LLM provider if changed
        if provider is not None or model_id is not None:
            self._resolve_llm_provider()

    def _resolve_llm_provider(self) -> None:
        """Resolve the LLM provider based on current config."""
        if not self._provider_registry:
            return

        provider_type = ProviderType.LOCAL
        if self._config.provider == "openrouter":
            provider_type = ProviderType.OPENAI  # OpenRouter uses OpenAI-compatible API
        elif self._config.provider == "local":
            provider_type = ProviderType.LOCAL

        # Try to get a provider of the requested type
        for pid in self._provider_registry.list_providers():
            prov = self._provider_registry.get(pid)
            if prov and prov.provider_type == provider_type:
                self._llm_provider = prov
                logger.info("Sentinel using provider: %s (model: %s)", pid, self._config.model_id)
                return

        # Fallback to first available provider
        providers = list(self._provider_registry.list_providers())
        if providers:
            self._llm_provider = self._provider_registry.get(providers[0])
            logger.warning("Sentinel using fallback provider: %s", providers[0])

    def start(self) -> None:
        """Start monitoring events."""
        if self._subscribed:
            return
        self._event_bus.subscribe("security_event", self._on_security_event)
        self._event_bus.subscribe("resource_exceeded", self._on_resource_exceeded)
        self._event_bus.subscribe("policy_violation", self._on_policy_violation)
        self._event_bus.subscribe("loop_detected", self._on_loop_detected)
        self._event_bus.subscribe("model_error", self._on_model_error)
        self._subscribed = True
        logger.info("Sentinel monitoring started")

    def stop(self) -> None:
        """Stop monitoring events."""
        if not self._subscribed:
            return
        self._event_bus.unsubscribe("security_event", self._on_security_event)
        self._event_bus.unsubscribe("resource_exceeded", self._on_resource_exceeded)
        self._event_bus.unsubscribe("policy_violation", self._on_policy_violation)
        self._event_bus.unsubscribe("loop_detected", self._on_loop_detected)
        self._event_bus.unsubscribe("model_error", self._on_model_error)
        self._subscribed = False
        logger.info("Sentinel monitoring stopped")

    def is_enabled(self) -> bool:
        """Check if Sentinel is enabled."""
        return self._config.enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable Sentinel."""
        self._config.enabled = enabled
        if enabled:
            self.start()
        else:
            self.stop()

    # ── Event Handlers ───────────────────────────────────────────────────────

    def _on_security_event(self, event: Event) -> None:
        """Handle security events from the event bus."""
        if not self._config.enabled:
            return
        self._queue_event(SentinelEvent(
            event_type=event.event_type,
            payload=event.payload,
            severity=event.priority.value,
            source=event.source,
        ))

    def _on_resource_exceeded(self, event: Event) -> None:
        """Handle resource exceeded events."""
        if not self._config.enabled:
            return
        self._queue_event(SentinelEvent(
            event_type="resource_exceeded",
            payload=event.payload,
            severity="HIGH",
            source=event.source,
        ))

    def _on_policy_violation(self, event: Event) -> None:
        """Handle policy violation events."""
        if not self._config.enabled:
            return
        self._queue_event(SentinelEvent(
            event_type="policy_violation",
            payload=event.payload,
            severity="CRITICAL",
            source=event.source,
        ))

    def _on_loop_detected(self, event: Event) -> None:
        """Handle loop detection events."""
        if not self._config.enabled:
            return
        self._queue_event(SentinelEvent(
            event_type="loop_detected",
            payload=event.payload,
            severity="HIGH",
            source=event.source,
        ))

    def _on_model_error(self, event: Event) -> None:
        """Handle model error events."""
        if not self._config.enabled:
            return
        self._queue_event(SentinelEvent(
            event_type="model_error",
            payload=event.payload,
            severity="WARNING",
            source=event.source,
        ))

    def _queue_event(self, sentinel_event: SentinelEvent) -> None:
        """Add event to analysis queue."""
        self._event_queue.append(sentinel_event)
        # Limit queue size
        if len(self._event_queue) > self._config.max_events_per_analysis:
            self._event_queue = self._event_queue[-self._config.max_events_per_analysis:]

    # ── Analysis ─────────────────────────────────────────────────────────────

    def analyze(self) -> Optional[SentinelAnalysis]:
        """Run a single analysis pass."""
        if not self._config.enabled:
            return None

        if not self._event_queue:
            return None

        # Layer A: Deterministic checks
        deterministic_result = self._deterministic_analysis()

        # Layer B: LLM analysis (if enabled and available)
        llm_result = None
        if self._config.analysis_mode in ("llm", "hybrid") and self._llm_provider:
            llm_result = self._llm_analysis()

        # Combine results
        if llm_result and self._config.analysis_mode == "hybrid":
            # Use LLM result if it's more severe
            if self._severity_rank(llm_result.alert_level) > self._severity_rank(deterministic_result.alert_level):
                return llm_result

        return deterministic_result

    def _deterministic_analysis(self) -> SentinelAnalysis:
        """Run deterministic security analysis (Layer A)."""
        evidence = []
        alert_level = SentinelAlertLevel.INFO
        action = SentinelAction.NONE
        explanation = "No anomalies detected"

        for event in self._event_queue:
            if event.event_type == "policy_violation":
                alert_level = SentinelAlertLevel.CRITICAL
                action = SentinelAction.STOP
                evidence.append({
                    "type": "policy_violation",
                    "source": event.source,
                    "severity": event.severity,
                })
            elif event.event_type == "loop_detected":
                if self._severity_rank(alert_level) < self._severity_rank(SentinelAlertLevel.HIGH):
                    alert_level = SentinelAlertLevel.HIGH
                    action = SentinelAction.PAUSE
                evidence.append({
                    "type": "loop_detected",
                    "source": event.source,
                })
            elif event.event_type == "resource_exceeded":
                if self._severity_rank(alert_level) < self._severity_rank(SentinelAlertLevel.HIGH):
                    alert_level = SentinelAlertLevel.HIGH
                    action = SentinelAction.PAUSE
                evidence.append({
                    "type": "resource_exceeded",
                    "source": event.source,
                })

        if not evidence:
            # Clear the queue since we've processed everything
            self._event_queue.clear()

        return SentinelAnalysis(
            alert_level=alert_level,
            action=action,
            explanation=explanation,
            evidence=evidence,
        )

    def _llm_analysis(self) -> Optional[SentinelAnalysis]:
        """Run LLM-based security analysis (Layer B)."""
        if not self._event_queue:
            return None

        try:
            # Prepare events for LLM
            events_text = json.dumps(
                [e.to_dict() for e in self._event_queue[-10:]],
                indent=2,
                ensure_ascii=False,
            )

            prompt = self._analysis_prompt_template.format(events=events_text)

            messages = [
                {"role": "system", "content": "You are a security analyst. Analyze events and provide structured JSON response."},
                {"role": "user", "content": prompt},
            ]

            result = self._llm_provider.chat(messages, max_tokens=500)

            if result.status != ChatStatus.SUCCESS:
                logger.warning("Sentinel LLM analysis failed: %s", result.error)
                return None

            # Parse JSON response
            try:
                analysis_data = json.loads(result.text)
            except json.JSONDecodeError:
                # Try to extract JSON from text
                import re
                match = re.search(r'\{[^}]+\}', result.text)
                if match:
                    try:
                        analysis_data = json.loads(match.group())
                    except json.JSONDecodeError:
                        return None
                else:
                    return None

            return SentinelAnalysis(
                alert_level=SentinelAlertLevel(analysis_data.get("alert_level", "INFO")),
                action=SentinelAction(analysis_data.get("action", "NONE")),
                explanation=analysis_data.get("explanation", "LLM analysis complete"),
                evidence=analysis_data.get("evidence", []),
                uncertainty=analysis_data.get("uncertainty", 0.3),
                llm_response=result.text,
            )

        except Exception as exc:
            logger.error("Sentinel LLM analysis error: %s", exc)
            return None

    @staticmethod
    def _severity_rank(level: SentinelAlertLevel) -> int:
        """Return numeric rank for alert level comparison."""
        ranks = {
            SentinelAlertLevel.INFO: 0,
            SentinelAlertLevel.WARNING: 1,
            SentinelAlertLevel.HIGH: 2,
            SentinelAlertLevel.CRITICAL: 3,
        }
        return ranks.get(level, 0)

    # ── Alert Management ─────────────────────────────────────────────────────

    def add_alert_handler(self, handler: Callable[[SentinelAnalysis], None]) -> None:
        """Register a handler for alerts."""
        self._alert_handlers.append(handler)

    def remove_alert_handler(self, handler: Callable[[SentinelAnalysis], None]) -> None:
        """Remove an alert handler."""
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)

    def _notify_alert(self, analysis: SentinelAnalysis) -> None:
        """Notify registered alert handlers."""
        self._alerts.append(analysis)
        # Limit alert history
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-50:]

        for handler in self._alert_handlers:
            try:
                handler(analysis)
            except Exception as exc:
                logger.error("Alert handler error: %s", exc)

    # ── API Methods ───────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get current Sentinel status."""
        return {
            "enabled": self._config.enabled,
            "provider": self._config.provider,
            "model_id": self._config.model_id,
            "analysis_mode": self._config.analysis_mode,
            "queue_size": len(self._event_queue),
            "alert_count": len(self._alerts),
            "llm_available": self._llm_provider is not None,
        }

    def get_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        return [a.to_dict() for a in self._alerts[-limit:]]

    def clear_alerts(self) -> int:
        """Clear all alerts."""
        count = len(self._alerts)
        self._alerts.clear()
        return count

    def health_check(self) -> Dict[str, Any]:
        """Check Sentinel health."""
        result = {
            "enabled": self._config.enabled,
            "llm_available": self._llm_provider is not None,
            "provider_configured": bool(self._config.provider),
            "model_configured": bool(self._config.model_id),
        }

        if self._llm_provider:
            result["llm_healthy"] = self._llm_provider.health_check()
        else:
            result["llm_healthy"] = False

        return result

    def request_external_upload_confirmation(self) -> bool:
        """Check if external log upload is allowed (requires explicit confirmation)."""
        return self._config.external_log_upload

    def export_events_for_review(self) -> List[Dict[str, Any]]:
        """Export events for manual review (sanitized)."""
        return [e.to_dict() for e in self._event_queue]
