"""Lightweight cache with TTL, LRU eviction, and thread safety.

Design:
  - Hash-based: hash(input) -> (result, expiry)
  - Size-limited: LRU eviction when full (default 1024 entries)
  - TTL expiration: entries expire after configurable seconds
  - Thread-safe: RLock for concurrent access
  - Memory-efficient: weak references where possible

Usage:
    cache = ResultCache(max_size=1024, ttl=300)
    result = cache.get_or_compute(key, compute_fn, **kwargs)
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

logger = logging.getLogger("core.cache")


@dataclass
class CacheEntry:
    """Single cache entry with expiry."""
    result: Any
    expires_at: float
    access_count: int = 0
    last_access: float = 0.0


F = TypeVar('F', bound=Callable)


class ResultCache:
    """Thread-safe LRU cache with TTL expiration.

    Args:
        max_size: Maximum number of entries (default 1024).
        ttl: Time-to-live in seconds (default 300 = 5 min).
    """

    def __init__(self, max_size: int = 1024, ttl: float = 300.0):
        self._max_size = max_size
        self._ttl = ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if present and not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None

            # Check expiry
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

            # Update access metadata
            entry.access_count += 1
            entry.last_access = time.time()
            self._cache.move_to_end(key)
            self._stats["hits"] += 1
            return entry.result

    def set(self, key: str, result: Any, ttl: Optional[float] = None) -> None:
        """Store a value in cache."""
        effective_ttl = ttl if ttl is not None else self._ttl
        expires_at = time.time() + effective_ttl

        with self._lock:
            # Evict LRU if full
            if len(self._cache) >= self._max_size:
                self._evict_lru()

            self._cache[key] = CacheEntry(
                result=result,
                expires_at=expires_at,
                access_count=1,
                last_access=time.time(),
            )

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[..., Any],
        ttl: Optional[float] = None,
        **kwargs,
    ) -> Any:
        """Get from cache or compute and store."""
        # Try cache first (outside lock for performance)
        cached = self.get(key)
        if cached is not None:
            return cached

        # Compute outside lock
        result = compute_fn(**kwargs)

        # Store with thread safety
        self.set(key, result, ttl)
        return result

    def invalidate(self, key: str) -> bool:
        """Remove a specific entry."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        """Remove all entries. Returns count cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if self._cache:
            self._cache.popitem(last=False)
            self._stats["evictions"] += 1

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._cache.items() if now > v.expires_at]
            for key in expired:
                del self._cache[key]
                self._stats["expirations"] += 1
            return len(expired)

    @property
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self._max_size,
                "hit_rate": (
                    self._stats["hits"] / max(1, self._stats["hits"] + self._stats["misses"])
                ),
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            return time.time() <= entry.expires_at


# Module-level singleton for tool results
_tool_cache: Optional[ResultCache] = None


def get_tool_cache() -> ResultCache:
    """Get the global tool result cache."""
    global _tool_cache
    if _tool_cache is None:
        _tool_cache = ResultCache(max_size=2048, ttl=600.0)  # 10 min TTL
    return _tool_cache


def hash_inputs(**kwargs) -> str:
    """Create a deterministic hash from keyword arguments."""
    # Sort keys for determinism, serialize values
    serialized = sorted(kwargs.items())
    raw = str(serialized).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def cached_tool(ttl: float = 600.0):
    """Decorator to cache tool function results.

    Usage:
        @cached_tool(ttl=600)
        def my_tool(x, y):
            return x + y
    """
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            cache = get_tool_cache()
            # Build hashable key from args and kwargs
            key_parts = [fn.__module__ + "." + fn.__name__]
            for i, arg in enumerate(args):
                key_parts.append(f"arg_{i}={arg!r}")
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v!r}")
            key = ":".join(key_parts)

            # Compute with args+kwargs
            def _compute(**kw):
                return fn(*args, **kw)
            return cache.get_or_compute(key, _compute, ttl=ttl, **kwargs)
        return wrapper
    return decorator


# ── Retry with exponential backoff ───────────────────────────────────────────

def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[type, ...] = (Exception,),
):
    """Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default 3).
        base_delay: Initial delay in seconds (default 1.0).
        max_delay: Maximum delay cap (default 30.0).
        exponential_base: Base for exponential backoff (default 2.0).
        exceptions: Tuple of exception types to catch (default all).

    Usage:
        @retry(max_attempts=3, base_delay=0.5)
        def flaky_api_call():
            return requests.get(url)
    """
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_attempts:
                        logger.warning(
                            "Retry exhausted for %s after %d attempts: %s",
                            fn.__name__, max_attempts, exc,
                        )
                        raise

                    delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)
                    logger.debug(
                        "Retry %d/%d for %s in %.2fs: %s",
                        attempt, max_attempts, fn.__name__, delay, exc,
                    )
                    time.sleep(delay)
            raise last_exception  # pragma: no cover
        return wrapper
    return decorator


# ── Fallback chain ───────────────────────────────────────────────────────────

class FallbackChain:
    """Execute functions in sequence until one succeeds.

    Usage:
        chain = FallbackChain([primary_fn, secondary_fn, tertiary_fn])
        result = chain.execute(input_data)
    """

    def __init__(self, functions: list):
        self._functions = functions
        self._history = []

    def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """Execute functions in order until one succeeds."""
        for fn in self._functions:
            try:
                result = fn(*args, **kwargs)
                self._history.append({
                    "function": fn.__name__,
                    "status": "success",
                    "result": result,
                })
                return {
                    "success": True,
                    "source": fn.__name__,
                    "result": result,
                    "fallback_used": len(self._history) > 1,
                }
            except Exception as exc:
                logger.warning("Fallback %s failed: %s", fn.__name__, exc)
                self._history.append({
                    "function": fn.__name__,
                    "status": "failed",
                    "error": str(exc),
                })

        # All failed
        return {
            "success": False,
            "source": None,
            "result": None,
            "fallback_used": True,
            "errors": [h["error"] for h in self._history if h["status"] == "failed"],
        }

    @property
    def history(self) -> list:
        return list(self._history)


# ── Pre-configured caches ────────────────────────────────────────────────────

class CacheRegistry:
    """Registry of named caches for different purposes."""

    _caches: Dict[str, ResultCache] = {}

    @classmethod
    def get(cls, name: str, max_size: int = 1024, ttl: float = 300.0) -> ResultCache:
        """Get or create a named cache."""
        if name not in cls._caches:
            cls._caches[name] = ResultCache(max_size=max_size, ttl=ttl)
        return cls._caches[name]

    @classmethod
    def clear_all(cls) -> int:
        """Clear all caches. Returns total entries cleared."""
        total = sum(len(c) for c in cls._caches.values())
        for cache in cls._caches.values():
            cache.clear()
        return total

    @classmethod
    def stats(cls) -> Dict[str, Any]:
        """Return statistics for all caches."""
        return {
            name: cache.stats
            for name, cache in cls._caches.items()
        }
