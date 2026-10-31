"""CaptN Runtime LLM Provider adapters.

Adapts the existing core.providers.base implementations for use by CaptN Runtime.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("captn.providers")


# ── Provider Types ───────────────────────────────────────────────────────────


class ProviderType:
    """Provider type enum."""

    LM_STUDIO = "lm_studio"
    OPENROUTER = "openrouter"
    MOCK = "mock"


# ── Data Structures ──────────────────────────────────────────────────────────


@dataclass
class ChatResult:
    """Result of a chat completion."""

    text: str
    finish_reason: str = "stop"
    model_used: str = ""
    provider: str = ""
    status: str = "success"
    latency_ms: float = 0.0
    tokens_used: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "finish_reason": self.finish_reason,
            "model_used": self.model_used,
            "provider": self.provider,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "error": self.error,
        }


@dataclass
class ProviderConfig:
    """Configuration for a CaptN provider."""

    provider_type: str
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


# ── Provider Base ────────────────────────────────────────────────────────────


class LLMProvider:
    """Base class for CaptN LLM providers."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._last_model_used: str = ""
        self._request_count: int = 0
        self._error_count: int = 0

    @property
    def provider_type(self) -> str:
        return self.config.provider_type

    @property
    def last_model_used(self) -> str:
        return self._last_model_used

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResult:
        raise NotImplementedError

    def get_models(self) -> List[str]:
        return [self.config.model_id]

    def health_check(self) -> bool:
        return True

    def record_success(self, latency_ms: float, tokens: int = 0) -> None:
        self._request_count += 1
        self._last_model_used = self.config.model_id

    def record_failure(self, error: str) -> None:
        self._error_count += 1
        logger.warning("Provider %s failure: %s", self.provider_type, error)


# ── LM Studio Provider ───────────────────────────────────────────────────────


class LmStudioProvider(LLMProvider):
    """Provider for local models via OpenAI-compatible API (LM Studio)."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = None
        self._models: List[str] = []

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI
            api_key = self.config.get_api_key() or "lm-studio"
            endpoint = self.config.endpoint.rstrip("/") + "/v1"
            self._client = OpenAI(base_url=endpoint, api_key=api_key)
        except ImportError:
            raise ImportError("openai package required for LmStudioProvider")

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

            # Handle tokens - some providers don't return usage
            tokens = 0
            if hasattr(choice, 'usage') and choice.usage is not None:
                tokens = getattr(choice.usage, 'total', 0) or 0

            latency_ms = (time.time() - start) * 1000
            self.record_success(latency_ms, tokens)

            return ChatResult(
                text=text.strip(),
                finish_reason=finish_reason,
                model_used=effective_model,
                provider=self.provider_type,
                status="success",
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
                status="error",
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


# ── OpenRouter Provider ──────────────────────────────────────────────────────


class OpenRouterProvider(LLMProvider):
    """Provider for OpenRouter API."""

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
                raise ValueError("OpenRouter API key not configured")
            endpoint = self.config.endpoint or "https://openrouter.ai/api/v1"
            self._client = OpenAI(base_url=endpoint, api_key=api_key)
        except ImportError:
            raise ImportError("openai package required for OpenRouterProvider")

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

            # Handle tokens - some providers don't return usage
            tokens = 0
            if hasattr(choice, 'usage') and choice.usage is not None:
                tokens = getattr(choice.usage, 'total', 0) or 0

            latency_ms = (time.time() - start) * 1000
            self.record_success(latency_ms, tokens)

            return ChatResult(
                text=text.strip(),
                finish_reason=finish_reason,
                model_used=effective_model,
                provider=self.provider_type,
                status="success",
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
                status="error",
                latency_ms=latency_ms,
                error=str(e),
            )

    def get_models(self) -> List[str]:
        try:
            self._ensure_client()
            resp = self._client.models.list()
            return [m.id for m in resp.data]
        except Exception as e:
            logger.warning("Failed to fetch OpenRouter models: %s", e)
            return []

    def health_check(self) -> bool:
        try:
            models = self.get_models()
            return len(models) > 0
        except Exception:
            return False


# ── Mock Provider ────────────────────────────────────────────────────────────


class MockProvider(LLMProvider):
    """Mock provider for testing — returns deterministic responses."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._response_index = 0

    def chat(self, messages, model=None, temperature=None, max_tokens=None):
        last_msg = messages[-1]["content"] if messages else ""
        response_text = f"[Mock Response] Analyzing: {last_msg[:100]}..."

        latency_ms = 10.0
        self.record_success(latency_ms)

        return ChatResult(
            text=response_text,
            finish_reason="stop",
            model_used=self.config.model_id,
            provider=self.provider_type,
            status="success",
            latency_ms=latency_ms,
        )

    def get_models(self) -> List[str]:
        return [self.config.model_id]

    def health_check(self) -> bool:
        return True


# ── Provider Factory ─────────────────────────────────────────────────────────


class ProviderFactory:
    """Factory for creating CaptN providers."""

    @staticmethod
    def create(provider_type: str, config: Optional[ProviderConfig] = None) -> LLMProvider:
        """Create a provider by type."""
        if config is None:
            config = ProviderConfig(
                provider_type=provider_type,
                model_id="default",
            )

        if provider_type == ProviderType.LM_STUDIO:
            return LmStudioProvider(config)
        elif provider_type == ProviderType.OPENROUTER:
            return OpenRouterProvider(config)
        elif provider_type == ProviderType.MOCK:
            return MockProvider(config)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

    @staticmethod
    def from_credentials(provider_type: str, base_url: str = "", api_key: str = "") -> LLMProvider:
        """Create a provider from credentials."""
        if provider_type == ProviderType.LM_STUDIO:
            config = ProviderConfig(
                provider_type=provider_type,
                model_id="local-model",
                endpoint=base_url or "http://localhost:1234",
                api_key_env="LIFE_MEAN_LLM_API_KEY",
            )
        elif provider_type == ProviderType.OPENROUTER:
            config = ProviderConfig(
                provider_type=provider_type,
                model_id="openrouter-model",
                endpoint=base_url or "https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
            )
        else:
            config = ProviderConfig(
                provider_type=provider_type,
                model_id="default",
            )

        return ProviderFactory.create(provider_type, config)


# ── Provider Registry ────────────────────────────────────────────────────────


class ProviderRegistry:
    """Registry for managing CaptN providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, LLMProvider] = {}
        self._configs: Dict[str, ProviderConfig] = {}

    def register(self, provider_id: str, provider: LLMProvider, config: ProviderConfig) -> None:
        """Register a provider."""
        self._providers[provider_id] = provider
        self._configs[provider_id] = config
        logger.info("Registered provider '%s' (type=%s, model=%s)",
                     provider_id, provider.provider_type, config.model_id)

    def get(self, provider_id: str) -> Optional[LLMProvider]:
        """Get a provider by ID."""
        return self._providers.get(provider_id)

    def list_providers(self) -> List[str]:
        """List all registered provider IDs."""
        return list(self._providers.keys())

    def health_check_all(self) -> Dict[str, bool]:
        """Check health of all providers."""
        return {pid: p.health_check() for pid, p in self._providers.items()}
