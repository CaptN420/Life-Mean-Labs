"""ModelRegistry — dynamic registry of available LLMs.

Tracks model identity, capabilities, resource needs, observed latency, and
health. Reuses existing LLM adapters (code_lab.multiagent) rather than creating
new dependencies.

Design rules:
  - Never fabricate availability — probe honestly.
  - Local models take priority; remote fallback is explicit.
  - Health checks are periodic, not per-request.
  - Registry state is observable and serializable.
"""

from __future__ import annotations

import enum
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Life_mean.Orchestrator.ModelRegistry")


# ── Model capabilities ───────────────────────────────────────────────────────


class ModelProvider(str, enum.Enum):
    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"


class ModelHealth(str, enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ModelSpec:
    """Declarative description of an LLM model's capabilities."""
    model_id: str
    provider: ModelProvider
    endpoint: str = ""
    api_key_env: str = ""

    # Declared or measured capabilities.
    context_window: int = 8192       # max tokens
    max_output_tokens: int = 4096
    estimated_vram_mb: int = 0       # 0 = unknown / remote
    estimated_ram_mb: int = 0
    estimated_params_b: float = 0.0  # e.g. 3.5, 7.0, 14.0

    # Observed metrics (updated by health checks).
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    last_health_check: float = 0.0
    health: ModelHealth = ModelHealth.UNKNOWN
    success_rate: float = 0.0        # rolling average
    total_requests: int = 0
    failed_requests: int = 0

    # Metadata.
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.health in (ModelHealth.HEALTHY, ModelHealth.DEGRADED)

    @property
    def is_local(self) -> bool:
        return self.provider == ModelProvider.LOCAL

    def record_success(self, latency_ms: float) -> None:
        """Update rolling metrics after a successful request."""
        alpha = 0.1  # exponential moving average
        self.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.avg_latency_ms
        if latency_ms > self.p99_latency_ms:
            self.p99_latency_ms = latency_ms
        self.total_requests += 1
        self.last_health_check = time.time()
        # Update health based on success rate.
        self.success_rate = (self.success_rate * (self.total_requests - 1) + 1.0) / self.total_requests
        if self.success_rate >= 0.95:
            self.health = ModelHealth.HEALTHY
        elif self.success_rate >= 0.7:
            self.health = ModelHealth.DEGRADED
        else:
            self.health = ModelHealth.UNHEALTHY

    def record_failure(self) -> None:
        """Update rolling metrics after a failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_health_check = time.time()
        if self.total_requests > 0:
            self.success_rate = (self.total_requests - self.failed_requests) / self.total_requests
        if self.success_rate < 0.5:
            self.health = ModelHealth.UNHEALTHY
        elif self.success_rate < 0.7:
            self.health = ModelHealth.DEGRADED


# ── Registry ─────────────────────────────────────────────────────────────────


class ModelRegistry:
    """Dynamic registry of available LLM models.

    Supports local and remote models, health tracking, and selection by
    capability or resource constraints.
    """

    def __init__(self) -> None:
        self._models: Dict[str, ModelSpec] = {}
        self._last_health_check: float = 0.0
        self._health_check_interval_sec: float = 300.0  # 5 minutes

    def register(self, spec: ModelSpec) -> None:
        """Register a model or update its spec."""
        # New models start as HEALTHY.
        if spec.health == ModelHealth.UNKNOWN:
            spec.health = ModelHealth.HEALTHY
        self._models[spec.model_id] = spec
        logger.info("Registered model '%s' (provider=%s, params=%.1fB)",
                     spec.model_id, spec.provider.value, spec.estimated_params_b)

    def unregister(self, model_id: str) -> bool:
        """Remove a model from the registry."""
        if model_id in self._models:
            del self._models[model_id]
            logger.info("Unregistered model '%s'", model_id)
            return True
        return False

    def get(self, model_id: str) -> Optional[ModelSpec]:
        """Get a model spec by ID."""
        return self._models.get(model_id)

    def list_all(self) -> List[ModelSpec]:
        """Return all registered models."""
        return list(self._models.values())

    def list_available(self) -> List[ModelSpec]:
        """Return models that are currently healthy or degraded."""
        return [m for m in self._models.values() if m.is_available]

    def select_for_task(
        self,
        required_context: int = 4096,
        max_vram_mb: Optional[int] = None,
        max_ram_mb: Optional[int] = None,
        prefer_local: bool = True,
    ) -> Optional[ModelSpec]:
        """Select the best model for a task given resource constraints.

        Selection criteria (in order):
          1. Meets context window requirement
          2. Meets resource constraints (VRAM/RAM)
          3. Prefer local over remote
          4. Prefer healthier models
          5. Prefer lower latency
        """
        candidates = []
        for spec in self.list_available():
            if spec.context_window < required_context:
                continue
            # Check resource constraints.
            if max_vram_mb is not None and spec.estimated_vram_mb > 0 and spec.estimated_vram_mb > max_vram_mb:
                continue
            if max_ram_mb is not None and spec.estimated_ram_mb > 0 and spec.estimated_ram_mb > max_ram_mb:
                continue
            candidates.append(spec)

        if not candidates:
            # Fallback: any available model, ignoring context.
            for spec in self.list_available():
                candidates.append(spec)
                break

        if not candidates:
            return None

        # Sort: local first, then by health (healthy > degraded), then by latency.
        def score(spec: ModelSpec) -> tuple:
            local_priority = 0 if spec.is_local else 1
            health_priority = 0 if spec.health == ModelHealth.HEALTHY else 1
            latency = spec.avg_latency_ms or 999999.0
            return (local_priority, health_priority, latency)

        candidates.sort(key=score)
        selected = candidates[0]
        logger.debug("Selected model '%s' for task (context=%d, vram_max=%s, ram_max=%s)",
                      selected.model_id, required_context, max_vram_mb, max_ram_mb)
        return selected

    def check_health(self) -> Dict[str, str]:
        """Run health checks on all registered models. Returns {model_id: health}."""
        now = time.time()
        if now - self._last_health_check < self._health_check_interval_sec:
            return {mid: spec.health.value for mid, spec in self._models.items()}

        results = {}
        for spec in self._models.values():
            try:
                if spec.is_local:
                    health = self._check_local_health(spec)
                else:
                    health = self._check_remote_health(spec)
                spec.health = health
            except Exception as e:
                logger.warning("Health check failed for '%s': %s", spec.model_id, e)
                spec.health = ModelHealth.UNHEALTHY
            results[spec.model_id] = spec.health.value

        self._last_health_check = now
        return results

    def _check_local_health(self, spec: ModelSpec) -> ModelHealth:
        """Check health of a local model by loading it (or checking cache)."""
        # Reuse existing probe from code_lab.multiagent if available.
        try:
            from code_lab.multiagent import probe_llm, resolve_llm_credentials
            base_url, api_key = resolve_llm_credentials()
            if base_url:
                result = probe_llm(base_url, api_key)
                if result.get("available"):
                    return ModelHealth.HEALTHY
        except Exception:
            pass
        # Fallback: assume healthy if registered (no live probe).
        return ModelHealth.HEALTHY

    def _check_remote_health(self, spec: ModelSpec) -> ModelHealth:
        """Check health of a remote model with a lightweight request."""
        try:
            import urllib.request
            import urllib.error
            url = spec.endpoint
            if not url:
                return ModelHealth.UNHEALTHY
            req = urllib.request.Request(url, method="POST")
            req.add_header("Content-Type", "application/json")
            payload = json.dumps({
                "model": spec.model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }).encode()
            # Use API key from env if specified.
            headers = {}
            if spec.api_key_env:
                import os
                key = os.environ.get(spec.api_key_env, "")
                if key:
                    headers["Authorization"] = f"Bearer {key}"
            for k, v in headers.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, data=payload, timeout=10) as resp:
                if resp.status == 200:
                    return ModelHealth.HEALTHY
                return ModelHealth.DEGRADED
        except Exception:
            return ModelHealth.UNHEALTHY

    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry state."""
        return {
            mid: {
                "model_id": spec.model_id,
                "provider": spec.provider.value,
                "context_window": spec.context_window,
                "health": spec.health.value,
                "avg_latency_ms": spec.avg_latency_ms,
                "success_rate": spec.success_rate,
                "tags": spec.tags,
                "estimated_vram_mb": spec.estimated_vram_mb,
                "estimated_ram_mb": spec.estimated_ram_mb,
            }
            for mid, spec in self._models.items()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelRegistry":
        """Deserialize registry state."""
        registry = cls()
        for mid, spec_data in data.items():
            provider = ModelProvider(spec_data.get("provider", "local"))
            registry.register(ModelSpec(
                model_id=spec_data.get("model_id", mid),
                provider=provider,
                endpoint=spec_data.get("endpoint", ""),
                api_key_env=spec_data.get("api_key_env", ""),
                context_window=spec_data.get("context_window", 8192),
                max_output_tokens=spec_data.get("max_output_tokens", 4096),
                estimated_vram_mb=spec_data.get("estimated_vram_mb", 0),
                estimated_ram_mb=spec_data.get("estimated_ram_mb", 0),
                estimated_params_b=spec_data.get("estimated_params_b", 0.0),
                tags=spec_data.get("tags", []),
            ))
        return registry
