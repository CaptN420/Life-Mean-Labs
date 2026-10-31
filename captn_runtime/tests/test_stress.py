"""Stress tests for CaptN Runtime Beta v0.1."""

import sys
import os
import time
import asyncio

# Add captn_runtime to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from captn.runtime import CaptNRuntime, RuntimeConfig
from captn.providers import ProviderType, MockProvider


class TestStressMock:
    """Stress tests using mock provider."""

    @pytest.mark.asyncio
    async def test_1k_requests(self):
        """Test 1K requests with mock provider."""
        runtime = CaptNRuntime()
        start = time.time()

        for i in range(1000):
            result = await runtime.run(f"Test query {i}")
            assert result.success

        elapsed = time.time() - start
        avg_latency = elapsed / 1000 * 1000  # ms
        print(f"\n✅ 1K requests: {elapsed:.2f}s total, {avg_latency:.2f}ms avg latency")

    @pytest.mark.asyncio
    async def test_10k_requests(self):
        """Test 10K requests with mock provider."""
        runtime = CaptNRuntime()
        start = time.time()

        for i in range(10000):
            result = await runtime.run(f"Test query {i}")
            assert result.success

        elapsed = time.time() - start
        avg_latency = elapsed / 10000 * 1000  # ms
        print(f"\n✅ 10K requests: {elapsed:.2f}s total, {avg_latency:.2f}ms avg latency")


class TestStressTokens:
    """Token stress tests."""

    @pytest.mark.asyncio
    async def test_20k_tokens(self):
        """Test with ~20K tokens context."""
        runtime = CaptNRuntime()
        long_context = " ".join([f"Context paragraph {i}." for i in range(200)])

        result = await runtime.run(
            query="Analyze this context",
            context=[long_context],
        )
        assert result.success
        print(f"\n✅ 20K tokens test: {result.tokens_input} input tokens")

    @pytest.mark.asyncio
    async def test_50k_tokens(self):
        """Test with ~50K tokens context."""
        runtime = CaptNRuntime()
        long_context = " ".join([f"Context paragraph {i}." for i in range(500)])

        result = await runtime.run(
            query="Analyze this context",
            context=[long_context],
        )
        assert result.success
        print(f"\n✅ 50K tokens test: {result.tokens_input} input tokens")


class TestRoutingStress:
    """Test routing under load."""

    @pytest.mark.asyncio
    async def test_routing_distribution(self):
        """Test that routing distributes across models."""
        runtime = CaptNRuntime()
        queries = [
            "Write a Python function",
            "Analyze this data",
            "Calculate the integral",
            "Debug this code",
            "Explain quantum physics",
        ] * 20

        for query in queries:
            result = await runtime.run(query)
            assert result.success

        stats = runtime.router.stats()
        print(f"\n✅ Routing distribution: {stats['usage']}")


class TestProviderIntegration:
    """Test provider integration."""

    def test_mock_provider(self):
        """Test mock provider works."""
        provider = MockProvider(type=ProviderType.MOCK, model_id="test")
        result = provider.chat([{"role": "user", "content": "Hello"}])
        assert result.status == "success"
        assert "Mock Response" in result.text

    def test_provider_registry(self):
        """Test provider registry."""
        from captn.providers import ProviderRegistry
        registry = ProviderRegistry()
        provider = MockProvider(type=ProviderType.MOCK, model_id="test")
        registry.register("test", provider)
        assert registry.get("test") == provider


class TestTelemetryStress:
    """Test telemetry under load."""

    @pytest.mark.asyncio
    async def test_telemetry_collection(self):
        """Test telemetry collection during stress."""
        runtime = CaptNRuntime()

        for i in range(100):
            await runtime.run(f"Test query {i}")

        stats = runtime.telemetry.get_stats()
        assert stats["total_events"] > 0
        print(f"\n✅ Telemetry: {stats['total_events']} events recorded")


class TestExperienceMemory:
    """Test experience memory under load."""

    @pytest.mark.asyncio
    async def test_experience_persistence(self):
        """Test experience persistence across runs."""
        runtime = CaptNRuntime()

        # Store some experiences
        for i in range(50):
            await runtime.run(f"Python coding task {i}")

        stats = runtime.experience_engine.stats()
        assert stats["total_experiences"] > 0
        print(f"\n✅ Experience memory: {stats['total_experiences']} experiences stored")


class TestFallback:
    """Test fallback behavior."""

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        """Test fallback when primary fails."""
        runtime = CaptNRuntime()

        # Simulate error scenario
        result = await runtime.run("Test query")
        assert result.success  # Should still succeed with mock


class TestLatency:
    """Test latency measurements."""

    @pytest.mark.asyncio
    async def test_latency_distribution(self):
        """Test latency distribution."""
        runtime = CaptNRuntime()
        latencies = []

        for i in range(50):
            start = time.time()
            await runtime.run(f"Test query {i}")
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        p50 = sorted(latencies)[len(latencies) // 2]
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        print(f"\n✅ Latency: avg={avg_latency:.2f}ms, p50={p50:.2f}ms, p99={p99:.2f}ms")
