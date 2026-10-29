"""LLM Provider abstraction — unified interface for multiple backends.

This module provides a consistent interface for different LLM providers:
- Local models (LM Studio, ollama, llama.cpp)
- OpenAI API (gpt-4, gpt-3.5-turbo)
- Anthropic API (Claude)
- Azure OpenAI
- Mock provider (for testing)

The MixedProviderRouter enables using different providers for different
roles in the same debate session.
"""

from __future__ import annotations

import abc
import enum
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.providers.base")


# ── Enums ────────────────────────────────────────────────────────────────────


class ProviderType(str, enum.Enum):
    """Types of LLM providers."""

    LOCAL = "local"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    MOCK = "mock"


class ChatStatus(str, enum.Enum):
    """Status of a chat completion."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ChatResult:
    """Result of a chat completion."""

    text: str
    finish_reason: str
    model_used: str
    provider: ProviderType
    status: ChatStatus
    latency_ms: float
    tokens_used: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "finish_reason": self.finish_reason,
            "model_used": self.model_used,
            "provider": self.provider.value,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "error": self.error,
        }


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""

    provider_type: ProviderType
    model_id: str
    endpoint: str = ""
    api_key_env: str = ""
    temperature: float = 0.8
    max_tokens: int = 2000
    timeout_sec: float = 60.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_api_key(self) -> str:
        """Get API key from environment."""
        if not self.api_key_env:
            return ""
        return os.environ.get(self.api_key_env, "")


# ── Abstract Base Class ─────────────────────────────────────────────────────


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._last_model_used: str = ""
        self._request_count: int = 0
        self._error_count: int = 0

    @property
    def provider_type(self) -> ProviderType:
        return self.config.provider_type

    @property
    def last_model_used(self) -> str:
        return self._last_model_used

    @abc.abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResult:
        """Send a chat completion request."""

    @abc.abstractmethod
    def get_models(self) -> List[str]:
        """Return list of available model IDs."""

    @abc.abstractmethod
    def health_check(self) -> bool:
        """Check if provider is healthy."""

    def record_success(self, latency_ms: float, tokens: int = 0) -> None:
        """Record a successful request."""
        self._request_count += 1
        self._last_model_used = self.config.model_id

    def record_failure(self, error: str) -> None:
        """Record a failed request."""
        self._error_count += 1
        logger.warning("Provider %s failure: %s", self.provider_type.value, error)


# ── Provider Implementations ────────────────────────────────────────────────


class LocalLLMProvider(LLMProvider):
    """Provider for local models via OpenAI-compatible API (LM Studio, ollama)."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = None
        self._models: List[str] = []

    def _ensure_client(self) -> None:
        """Lazy initialize the OpenAI client."""
        if self._client is not None:
            return

        try:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.config.endpoint.rstrip("/") + "/v1",
                api_key=self.config.get_api_key() or "lm-studio",
            )
        except ImportError:
            raise ImportError("openai package required for LocalLLMProvider")

    def chat(self, messages, model=None, temperature=None, max_tokens=None):
        start = time.time()
        try:
            self._ensure_client()
            effective_model = model or self.config.model_id
            response = self._client.chat.completions.create(
                model=effective_model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
            )
            choice = response.choices[0]
            text = choice.message.content or ""
            finish_reason = choice.finish_reason or "stop"
            tokens = getattr(choice.usage, 'total', 0) or 0

            latency_ms = (time.time() - start) * 1000
            self.record_success(latency_ms, tokens)

            return ChatResult(
                text=text.strip(),
                finish_reason=finish_reason,
                model_used=effective_model,
                provider=self.provider_type,
                status=ChatStatus.SUCCESS,
                latency_ms=latency_ms,
                tokens_used=tokens,
            )
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            self.record_failure(str(e))
            return ChatResult(
                text=f"[Error: {e}]",
                finish_reason="error",
                model_used=model or self.config.model_id,
                provider=self.provider_type,
                status=ChatStatus.ERROR,
                latency_ms=latency_ms,
                error=str(e),
            )

    def get_models(self) -> List[str]:
        if self._models:
            return self._models
        try:
            self._ensure_client()
            resp = self._client.models.list()
            self._models = [m.id for m in resp.data]
        except Exception as e:
            logger.warning("Failed to fetch models: %s", e)
            self._models = []
        return self._models

    def health_check(self) -> bool:
        try:
            models = self.get_models()
            return len(models) > 0
        except Exception:
            return False


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI API (gpt-4, gpt-3.5-turbo)."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI
            api_key = self.config.get_api_key()
            if not api_key:
                raise ValueError("API key not configured (set OPENAI_API_KEY env var)")
            self._client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai package required for OpenAIProvider")

    def chat(self, messages, model=None, temperature=None, max_tokens=None):
        start = time.time()
        try:
            self._ensure_client()
            effective_model = model or self.config.model_id
            response = self._client.chat.completions.create(
                model=effective_model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
            )
            choice = response.choices[0]
            text = choice.message.content or ""
            finish_reason = choice.finish_reason or "stop"
            tokens = getattr(choice.usage, 'total', 0) or 0

            latency_ms = (time.time() - start) * 1000
            self.record_success(latency_ms, tokens)

            return ChatResult(
                text=text.strip(),
                finish_reason=finish_reason,
                model_used=effective_model,
                provider=self.provider_type,
                status=ChatStatus.SUCCESS,
                latency_ms=latency_ms,
                tokens_used=tokens,
            )
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            self.record_failure(str(e))
            return ChatResult(
                text=f"[Error: {e}]",
                finish_reason="error",
                model_used=model or self.config.model_id,
                provider=self.provider_type,
                status=ChatStatus.ERROR,
                latency_ms=latency_ms,
                error=str(e),
            )

    def get_models(self) -> List[str]:
        try:
            self._ensure_client()
            resp = self._client.models.list()
            return [m.id for m in resp.data]
        except Exception as e:
            logger.warning("Failed to fetch OpenAI models: %s", e)
            return []

    def health_check(self) -> bool:
        try:
            models = self.get_models()
            return len(models) > 0
        except Exception:
            return False


class MockLLMProvider(LLMProvider):
    """Mock provider for testing — returns deterministic responses."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._response_index = 0

    def chat(self, messages, model=None, temperature=None, max_tokens=None):
        # Deterministic response based on message content
        last_msg = messages[-1]["content"] if messages else ""
        response_text = f"[Mock Response] Analyzing: {last_msg[:100]}..."

        latency_ms = 10.0  # Simulated latency
        self.record_success(latency_ms)

        return ChatResult(
            text=response_text,
            finish_reason="stop",
            model_used=self.config.model_id,
            provider=self.provider_type,
            status=ChatStatus.SUCCESS,
            latency_ms=latency_ms,
        )

    def get_models(self) -> List[str]:
        return [self.config.model_id]

    def health_check(self) -> bool:
        return True


# ── Provider Registry ───────────────────────────────────────────────────────


class ProviderRegistry:
    """Registry for managing LLM providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, LLMProvider] = {}
        self._configs: Dict[str, ProviderConfig] = {}

    def register(self, provider_id: str, provider: LLMProvider, config: ProviderConfig) -> None:
        """Register a provider."""
        self._providers[provider_id] = provider
        self._configs[provider_id] = config
        logger.info("Registered provider '%s' (type=%s, model=%s)",
                     provider_id, provider.provider_type.value, config.model_id)

    def get(self, provider_id: str) -> Optional[LLMProvider]:
        """Get a provider by ID."""
        return self._providers.get(provider_id)

    def list_providers(self) -> List[str]:
        """List all registered provider IDs."""
        return list(self._providers.keys())

    def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers."""
        return {pid: p.health_check() for pid, p in self._providers.items()}


# ── Mixed Provider Router ───────────────────────────────────────────────────


class MixedProviderRouter:
    """Routes requests to different providers based on role/model mapping.

    Enables using different providers (e.g., OpenAI for one role, local for
    another) within the same debate session.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry
        self._role_mapping: Dict[str, str] = {}  # role_id -> provider_id
        self._model_mapping: Dict[str, str] = {}  # model_id -> provider_id
        self._fallback_provider: Optional[str] = None

    def add_role_mapping(self, role_id: str, provider_id: str) -> None:
        """Map a role to a specific provider."""
        self._role_mapping[role_id] = provider_id

    def add_model_mapping(self, model_id: str, provider_id: str) -> None:
        """Map a model to a specific provider."""
        self._model_mapping[model_id] = provider_id

    def set_fallback(self, provider_id: str) -> None:
        """Set the fallback provider ID."""
        self._fallback_provider = provider_id

    def resolve_provider(self, role_id: Optional[str], model_id: Optional[str]) -> Optional[LLMProvider]:
        """Resolve which provider to use for a given role/model."""
        # Try role mapping first
        if role_id and role_id in self._role_mapping:
            provider_id = self._role_mapping[role_id]
            return self._registry.get(provider_id)

        # Try model mapping
        if model_id and model_id in self._model_mapping:
            provider_id = self._model_mapping[model_id]
            return self._registry.get(provider_id)

        # Try fallback
        if self._fallback_provider:
            return self._registry.get(self._fallback_provider)

        # Return first available provider
        providers = list(self._registry.list_providers())
        if providers:
            return self._registry.get(providers[0])

        return None

    def route_chat(
        self,
        messages: List[Dict[str, str]],
        role_id: Optional[str] = None,
        model_id: Optional[str] = None,
        **kwargs,
    ) -> ChatResult:
        """Route a chat request to the appropriate provider."""
        provider = self.resolve_provider(role_id, model_id)
        if provider is None:
            return ChatResult(
                text="[Error: No provider available]",
                finish_reason="error",
                model_used=model_id or "unknown",
                provider=ProviderType.MOCK,
                status=ChatStatus.ERROR,
                latency_ms=0.0,
                error="No provider available",
            )

        return provider.chat(messages, model=model_id, **kwargs)
