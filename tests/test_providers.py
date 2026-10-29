"""Tests for the LLM provider abstraction and mixed routing."""

import pytest

from core.providers.base import (
    ChatResult,
    ChatStatus,
    LocalLLMProvider,
    MixedProviderRouter,
    MockLLMProvider,
    OpenAIProvider,
    ProviderConfig,
    ProviderRegistry,
    ProviderType,
)


class TestMockLLMProvider:
    """Tests for the mock provider."""

    def test_chat_success(self):
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-model",
        )
        provider = MockLLMProvider(config)
        result = provider.chat([{"role": "user", "content": "Hello"}])

        assert result.status == ChatStatus.SUCCESS
        assert result.model_used == "mock-model"
        assert "Mock Response" in result.text
        assert result.latency_ms > 0

    def test_get_models(self):
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-model",
        )
        provider = MockLLMProvider(config)
        models = provider.get_models()
        assert len(models) == 1
        assert models[0] == "mock-model"

    def test_health_check(self):
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-model",
        )
        provider = MockLLMProvider(config)
        assert provider.health_check() is True


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_register_and_get(self):
        registry = ProviderRegistry()
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-1",
        )
        provider = MockLLMProvider(config)
        registry.register("provider1", provider, config)

        assert registry.get("provider1") is provider
        assert registry.get("nonexistent") is None

    def test_list_providers(self):
        registry = ProviderRegistry()
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-1",
        )
        registry.register("p1", MockLLMProvider(config), config)
        registry.register("p2", MockLLMProvider(config), config)

        providers = registry.list_providers()
        assert "p1" in providers
        assert "p2" in providers

    def test_health_check_all(self):
        registry = ProviderRegistry()
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-1",
        )
        registry.register("p1", MockLLMProvider(config), config)
        registry.register("p2", MockLLMProvider(config), config)

        results = registry.health_check_all()
        assert results["p1"] is True
        assert results["p2"] is True


class TestMixedProviderRouter:
    """Tests for MixedProviderRouter."""

    def test_resolve_by_role(self):
        registry = ProviderRegistry()
        config1 = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-1",
        )
        config2 = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-2",
        )
        registry.register("provider1", MockLLMProvider(config1), config1)
        registry.register("provider2", MockLLMProvider(config2), config2)

        router = MixedProviderRouter(registry)
        router.add_role_mapping("role_a", "provider1")
        router.add_role_mapping("role_b", "provider2")

        provider = router.resolve_provider("role_a", None)
        assert provider is not None
        assert provider.config.model_id == "mock-1"

    def test_resolve_by_model(self):
        registry = ProviderRegistry()
        config1 = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="model-x",
        )
        config2 = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="model-y",
        )
        registry.register("p1", MockLLMProvider(config1), config1)
        registry.register("p2", MockLLMProvider(config2), config2)

        router = MixedProviderRouter(registry)
        router.add_model_mapping("model-x", "p1")
        router.add_model_mapping("model-y", "p2")

        provider = router.resolve_provider(None, "model-y")
        assert provider is not None
        assert provider.config.model_id == "model-y"

    def test_fallback_to_first(self):
        registry = ProviderRegistry()
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="fallback",
        )
        registry.register("fallback", MockLLMProvider(config), config)

        router = MixedProviderRouter(registry)
        provider = router.resolve_provider(None, None)
        assert provider is not None
        assert provider.config.model_id == "fallback"

    def test_route_chat(self):
        registry = ProviderRegistry()
        config = ProviderConfig(
            provider_type=ProviderType.MOCK,
            model_id="mock-1",
        )
        registry.register("p1", MockLLMProvider(config), config)

        router = MixedProviderRouter(registry)
        result = router.route_chat(
            messages=[{"role": "user", "content": "Hello"}],
            role_id="test_role",
        )

        assert result.status == ChatStatus.SUCCESS
        assert "Mock Response" in result.text


class TestChatResult:
    """Tests for ChatResult."""

    def test_to_dict(self):
        result = ChatResult(
            text="Hello",
            finish_reason="stop",
            model_used="test-model",
            provider=ProviderType.MOCK,
            status=ChatStatus.SUCCESS,
            latency_ms=100.0,
            tokens_used=50,
        )
        data = result.to_dict()
        assert data["text"] == "Hello"
        assert data["provider"] == "mock"
        assert data["status"] == "success"
        assert data["latency_ms"] == 100.0
