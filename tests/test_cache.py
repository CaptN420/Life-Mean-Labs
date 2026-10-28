"""Tests for core.cache module."""
from __future__ import annotations

import time

import pytest

from core.cache import ResultCache, CacheRegistry, hash_inputs, cached_tool


class TestResultCache:
    """Test ResultCache functionality."""

    def test_set_get(self):
        cache = ResultCache(max_size=10, ttl=60)
        cache.set("key1", {"result": "value"})
        assert cache.get("key1") == {"result": "value"}

    def test_miss(self):
        cache = ResultCache(max_size=10, ttl=60)
        assert cache.get("missing") is None

    def test_get_or_compute(self):
        cache = ResultCache(max_size=10, ttl=60)
        call_count = 0

        def compute(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = cache.get_or_compute("key", compute, x=5)
        assert result1 == 10
        assert call_count == 1

        # Second call should hit cache
        result2 = cache.get_or_compute("key", compute, x=5)
        assert result2 == 10
        assert call_count == 1  # Still 1, cached

    def test_expiry(self):
        cache = ResultCache(max_size=10, ttl=0.1)  # 100ms TTL
        cache.set("key", "value")
        time.sleep(0.2)
        assert cache.get("key") is None

    def test_lru_eviction(self):
        cache = ResultCache(max_size=3, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # Should evict "a"

        assert cache.get("a") is None
        assert cache.get("d") == 4

    def test_invalidate(self):
        cache = ResultCache(max_size=10, ttl=60)
        cache.set("key", "value")
        assert cache.invalidate("key") is True
        assert cache.get("key") is None
        assert cache.invalidate("missing") is False

    def test_clear(self):
        cache = ResultCache(max_size=10, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        count = cache.clear()
        assert count == 2
        assert len(cache) == 0

    def test_stats(self):
        cache = ResultCache(max_size=10, ttl=60)
        cache.set("key", "value")
        cache.get("key")
        cache.get("missing")

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 0.5

    def test_hash_inputs_deterministic(self):
        h1 = hash_inputs(x=1, y=2)
        h2 = hash_inputs(y=2, x=1)  # Same args, different order
        assert h1 == h2


class TestCacheRegistry:
    """Test CacheRegistry."""

    def test_get_or_create(self):
        CacheRegistry.get("test_cache", max_size=100, ttl=30)
        cache = CacheRegistry.get("test_cache")
        assert cache is not None
        assert cache._max_size == 100

    def test_clear_all(self):
        CacheRegistry.get("reg_test", max_size=10, ttl=60).set("key", "value")
        total = CacheRegistry.clear_all()
        assert total > 0


class TestCachedTool:
    """Test cached_tool decorator."""

    def test_caches_result(self):
        call_count = 0

        @cached_tool(ttl=60)
        def slow_add(x, y):
            nonlocal call_count
            call_count += 1
            return x + y

        r1 = slow_add(1, 2)
        r2 = slow_add(1, 2)
        assert r1 == 3
        assert r2 == 3
        assert call_count == 1  # Only called once

    def test_caches_kwargs(self):
        call_count = 0

        @cached_tool(ttl=60)
        def add_kwargs(x, y=0):
            nonlocal call_count
            call_count += 1
            return x + y

        r1 = add_kwargs(5, y=3)
        r2 = add_kwargs(5, y=3)
        assert r1 == 8
        assert r2 == 8
        assert call_count == 1
