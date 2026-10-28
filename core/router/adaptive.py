"""Adaptive Router — intelligent task routing with validation and cost optimization.

Routes tasks through: CACHE → DETERMINISTIC → COMPUTATIONAL → LLM → ERROR
Validates results, tracks costs, and optimizes for reliability vs cost.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("core.router.adaptive")


# ── Enums ────────────────────────────────────────────────────────────────────

class TaskClassification(str, Enum):
    """Task classification based on nature."""
    DETERMINISTIC = "DETERMINISTIC"  # Exact calculation, explicit rules
    COMPUTATIONAL = "COMPUTATIONAL"   # Simulation, optimization, numerical
    REASONING = "REASONING"           # Complex analysis, multi-step
    AMBIGUOUS = "AMBIGUOUS"           # Insufficient data, multiple interpretations
    UNKNOWN = "UNKNOWN"               # Undetermined


class EngineType(str, Enum):
    """Engine selection."""
    CACHE = "CACHE"
    DETERMINISTIC = "DETERMINISTIC"
    COMPUTATIONAL = "COMPUTATIONAL"
    LLM = "LLM"
    ERROR = "ERROR"


class ValidationStatus(str, Enum):
    """Result validation status."""
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    INVALID = "INVALID"


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class RouteDecision:
    """Decision made by the router."""
    task_id: str
    classification: TaskClassification
    validation: ValidationStatus
    selected_engine: EngineType
    cache_hit: bool = False
    fallback_count: int = 0
    execution_ms: float = 0.0
    tokens_used: int = 0
    compute_cost: float = 0.0
    result_verified: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "classification": self.classification.value,
            "validation": self.validation.value,
            "selected_engine": self.selected_engine.value,
            "cache_hit": self.cache_hit,
            "fallback_count": self.fallback_count,
            "execution_ms": self.execution_ms,
            "tokens_used": self.tokens_used,
            "compute_cost": self.compute_cost,
            "result_verified": self.result_verified,
            "error": self.error,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class WorkerStats:
    """Statistics for a worker."""
    name: str
    success_count: int = 0
    failure_count: int = 0
    total_execution_ms: float = 0.0
    total_tokens: int = 0
    total_compute_cost: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5  # Default to 50% when no data
        return self.success_count / total

    @property
    def avg_execution_ms(self) -> float:
        if self.success_count + self.failure_count == 0:
            return 0.0
        return self.total_execution_ms / (self.success_count + self.failure_count)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "success_rate": round(self.success_rate, 3),
            "successes": self.success_count,
            "failures": self.failure_count,
            "avg_execution_ms": round(self.avg_execution_ms, 2),
            "total_tokens": self.total_tokens,
            "total_compute_cost": round(self.total_compute_cost, 4),
        }


@dataclass
class CostConfig:
    """Cost optimization configuration."""
    reliability_weight: float = 2.0
    compute_weight: float = 1.0
    token_weight: float = 0.01  # $ per token estimate
    latency_weight: float = 0.5  # $ per ms

    def score(
        self,
        success_rate: float,
        compute_cost: float,
        token_cost: float,
        latency_ms: float,
    ) -> float:
        """Lower is better."""
        return (
            self.reliability_weight * (1.0 - success_rate)
            + self.compute_weight * compute_cost
            + self.token_weight * token_cost
            + self.latency_weight * (latency_ms / 1000.0)
        )


# ── Classifier ───────────────────────────────────────────────────────────────

class TaskClassifier:
    """Classify tasks based on description and metadata."""

    # Keywords for classification
    _DETERMINISTIC_KEYWORDS = {
        "calculate", "compute", "gcd", "lcm", "prime", "fibonacci",
        "factorial", "equation", "solve", "evaluate", "transform",
        "sort", "search", "algorithm", "math", "physics", "chemistry",
    }
    _COMPUTATIONAL_KEYWORDS = {
        "simulate", "optimize", "numerical", "integration", "approximation",
        "monte carlo", "simulation", "model", "forecast", "predict",
    }
    _REASONING_KEYWORDS = {
        "analyze", "reason", "explain", "compare", "evaluate", "design",
        "architect", "debate", "discuss", "philosophy", "argument",
    }

    def classify(self, description: str, metadata: Optional[Dict[str, Any]] = None) -> TaskClassification:
        """Classify a task based on description."""
        if not description:
            return TaskClassification.UNKNOWN

        desc_lower = description.lower()
        words = set(desc_lower.split())

        # Check for tool-specific patterns (deterministic)
        if any(kw in words for kw in self._DETERMINISTIC_KEYWORDS):
            # Verify it's not just a discussion about math
            if any(kw in words for kw in self._REASONING_KEYWORDS):
                return TaskClassification.REASONING
            return TaskClassification.DETERMINISTIC

        # Check for computational patterns
        if any(kw in words for kw in self._COMPUTATIONAL_KEYWORDS):
            return TaskClassification.COMPUTATIONAL

        # Check for reasoning patterns
        if any(kw in words for kw in self._REASONING_KEYWORDS):
            return TaskClassification.REASONING

        # Default based on length and complexity indicators
        if len(description.strip()) < 10:
            return TaskClassification.DETERMINISTIC  # Short = likely simple calc

        return TaskClassification.UNKNOWN

    def is_deterministic_tool(self, tool_name: str) -> bool:
        """Check if a tool name indicates deterministic execution."""
        deterministic_prefixes = ("math_", "chemistry_", "physics_", "logic_")
        return any(tool_name.startswith(p) for p in deterministic_prefixes)


# ── Validator ────────────────────────────────────────────────────────────────

class ResultValidator:
    """Validate results from workers."""

    def __init__(self):
        self._validators: Dict[str, Callable[[Any], ValidationStatus]] = {}

    def register(self, tool_pattern: str, validator: Callable[[Any], ValidationStatus]) -> None:
        """Register a validator for a tool pattern."""
        self._validators[tool_pattern] = validator

    def validate(self, tool_name: str, result: Any) -> ValidationStatus:
        """Validate a result. Returns VERIFIED, PARTIAL, UNVERIFIED, or INVALID."""
        # Check if result is a dict with valid flag
        if isinstance(result, dict):
            if result.get("valid") is False:
                return ValidationStatus.INVALID
            if result.get("error"):
                return ValidationStatus.UNVERIFIED

        # Check for specific tool validators
        for pattern, validator in self._validators.items():
            if pattern in tool_name:
                try:
                    status = validator(result)
                    if status == ValidationStatus.INVALID:
                        logger.warning("Validation failed for %s: invalid result", tool_name)
                    return status
                except Exception as exc:
                    logger.warning("Validator error for %s: %s", tool_name, exc)
                    return ValidationStatus.UNVERIFIED

        # Default validation
        if result is None:
            return ValidationStatus.INVALID
        if isinstance(result, (int, float, str, bool)):
            return ValidationStatus.VERIFIED
        if isinstance(result, dict) and "result" in result:
            return ValidationStatus.VERIFIED

        return ValidationStatus.PARTIAL


# ── Adaptive Router ────────────────────────────────────────────────────────

class AdaptiveRouter:
    """Adaptive task router with validation and cost optimization.

    Routes tasks through: CACHE → DETERMINISTIC → COMPUTATIONAL → LLM → ERROR
    """

    def __init__(
        self,
        cost_config: Optional[CostConfig] = None,
        max_fallbacks: int = 3,
        budget_ms: float = 30000.0,
        budget_tokens: int = 100000,
    ):
        self._classifier = TaskClassifier()
        self._validator = ResultValidator()
        self._cost_config = cost_config or CostConfig()
        self._max_fallbacks = max_fallbacks
        self._budget_ms = budget_ms
        self._budget_tokens = budget_tokens

        # Worker statistics
        self._worker_stats: Dict[str, WorkerStats] = {}

        # Registered engines
        self._engines: Dict[EngineType, Callable[..., Any]] = {}

        # Task history for pattern learning
        self._task_history: List[RouteDecision] = []

    @property
    def classifier(self) -> TaskClassifier:
        return self._classifier

    @property
    def validator(self) -> ResultValidator:
        return self._validator

    @property
    def cost_config(self) -> CostConfig:
        return self._cost_config

    # ── Engine Registration ────────────────────────────────────────────────

    def register_engine(self, engine_type: EngineType, executor: Callable[..., Any]) -> None:
        """Register an engine executor."""
        self._engines[engine_type] = executor
        logger.info("Registered engine: %s", engine_type.value)

    def get_worker_stats(self, worker_name: str) -> Optional[WorkerStats]:
        """Get statistics for a worker."""
        return self._worker_stats.get(worker_name)

    def update_worker_stats(
        self,
        worker_name: str,
        success: bool,
        execution_ms: float,
        tokens: int = 0,
        compute_cost: float = 0.0,
    ) -> None:
        """Update worker statistics."""
        if worker_name not in self._worker_stats:
            self._worker_stats[worker_name] = WorkerStats(name=worker_name)

        stats = self._worker_stats[worker_name]
        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
        stats.total_execution_ms += execution_ms
        stats.total_tokens += tokens
        stats.total_compute_cost += compute_cost

    # ── Main Route Method ──────────────────────────────────────────────────

    def route(
        self,
        task_id: str,
        description: str,
        tool_name: Optional[str] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        llm_available: bool = False,
    ) -> RouteDecision:
        """Route a task through the adaptive pipeline.

        Returns a RouteDecision with classification, engine selection, and validation status.
        """
        start_time = time.time()
        kwargs = kwargs or {}

        # Step 1: Classify
        classification = self._classify_task(description, tool_name)

        # Step 2: Try cache first
        cache_result, cache_hit = self._try_cache(task_id, tool_name, kwargs)
        if cache_hit:
            execution_ms = (time.time() - start_time) * 1000
            decision = RouteDecision(
                task_id=task_id,
                classification=classification,
                validation=ValidationStatus.VERIFIED,
                selected_engine=EngineType.CACHE,
                cache_hit=True,
                execution_ms=execution_ms,
                result_verified=True,
            )
            self._log_decision(decision)
            return decision

        # Step 3: Select engine based on classification
        engine = self._select_engine(classification, llm_available, tool_name)

        # Step 4: Execute with fallback chain
        result, fallback_count, error = self._execute_with_fallback(
            task_id, description, tool_name, kwargs, engine, llm_available,
        )

        # Step 5: Validate result
        validation = self._validator.validate(tool_name or "unknown", result)

        # Step 6: Build decision
        execution_ms = (time.time() - start_time) * 1000
        decision = RouteDecision(
            task_id=task_id,
            classification=classification,
            validation=validation,
            selected_engine=engine,
            cache_hit=False,
            fallback_count=fallback_count,
            execution_ms=execution_ms,
            error=error,
            result_verified=(validation == ValidationStatus.VERIFIED),
        )

        # Step 7: Cache successful results
        if validation == ValidationStatus.VERIFIED and engine != EngineType.ERROR:
            self._cache_result(task_id, tool_name, kwargs, result)

        self._log_decision(decision)
        return decision

    # ── Classification ─────────────────────────────────────────────────────

    def _classify_task(
        self,
        description: str,
        tool_name: Optional[str],
    ) -> TaskClassification:
        """Classify task based on description and tool name."""
        if tool_name and self._classifier.is_deterministic_tool(tool_name):
            return TaskClassification.DETERMINISTIC
        return self._classifier.classify(description)

    # ── Cache Operations ───────────────────────────────────────────────────

    def _try_cache(
        self,
        task_id: str,
        tool_name: Optional[str],
        kwargs: Dict[str, Any],
    ) -> Tuple[Any, bool]:
        """Try to get result from cache."""
        if not tool_name:
            return None, False

        # Build cache key
        key_parts = [tool_name]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v!r}")
        cache_key = hashlib.sha256(":".join(key_parts).encode()).hexdigest()[:16]

        from core.cache import get_tool_cache
        cache = get_tool_cache()
        result = cache.get(cache_key)

        if result is not None:
            logger.debug("Cache HIT for task %s: %s", task_id, tool_name)
            return result, True

        logger.debug("Cache MISS for task %s: %s", task_id, tool_name)
        return None, False

    def _cache_result(self, task_id: str, tool_name: Optional[str], kwargs: Dict[str, Any], result: Any) -> None:
        """Store result in cache."""
        if not tool_name:
            return

        key_parts = [tool_name]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v!r}")
        cache_key = hashlib.sha256(":".join(key_parts).encode()).hexdigest()[:16]

        from core.cache import get_tool_cache
        cache = get_tool_cache()
        cache.set(cache_key, result, ttl=600.0)  # 10 min TTL

    # ── Engine Selection ───────────────────────────────────────────────────

    def _select_engine(
        self,
        classification: TaskClassification,
        llm_available: bool,
        tool_name: Optional[str],
    ) -> EngineType:
        """Select the best engine for a task."""
        # Deterministic tools always use deterministic engine
        if tool_name and self._classifier.is_deterministic_tool(tool_name):
            return EngineType.DETERMINISTIC

        # Use available engines based on classification
        if classification == TaskClassification.DETERMINISTIC:
            return EngineType.DETERMINISTIC
        elif classification == TaskClassification.COMPUTATIONAL:
            return EngineType.COMPUTATIONAL
        elif classification == TaskClassification.REASONING and llm_available:
            return EngineType.LLM
        elif llm_available:
            return EngineType.LLM
        else:
            return EngineType.ERROR

    # ── Execution with Fallback ────────────────────────────────────────────

    def _execute_with_fallback(
        self,
        task_id: str,
        description: str,
        tool_name: Optional[str],
        kwargs: Dict[str, Any],
        engine: EngineType,
        llm_available: bool,
    ) -> Tuple[Any, int, Optional[str]]:
        """Execute with fallback chain."""
        fallback_order = self._build_fallback_chain(engine, llm_available)

        for attempt, fallback_engine in enumerate(fallback_order):
            try:
                # Check budget
                if attempt > 0:
                    logger.info("Fallback %d/%d for task %s", attempt, len(fallback_order), task_id)

                executor = self._engines.get(fallback_engine)
                if executor is None:
                    continue

                result = executor(task_id=task_id, description=description, tool_name=tool_name, **kwargs)

                # Update stats
                self.update_worker_stats(
                    fallback_engine.value,
                    success=True,
                    execution_ms=10.0,  # Approximate
                )

                return result, attempt, None

            except Exception as exc:
                logger.warning("Engine %s failed for task %s: %s", fallback_engine.value, task_id, exc)
                self.update_worker_stats(
                    fallback_engine.value,
                    success=False,
                    execution_ms=0.0,
                )

                if attempt >= self._max_fallbacks - 1:
                    return None, attempt, str(exc)

        return None, len(fallback_order), "All engines exhausted"

    def _build_fallback_chain(
        self,
        primary: EngineType,
        llm_available: bool,
    ) -> List[EngineType]:
        """Build fallback chain based on primary engine."""
        chain = [primary]

        # Add fallbacks based on what's available
        if primary == EngineType.DETERMINISTIC:
            if EngineType.COMPUTATIONAL in self._engines:
                chain.append(EngineType.COMPUTATIONAL)
        elif primary == EngineType.COMPUTATIONAL:
            if llm_available and EngineType.LLM in self._engines:
                chain.append(EngineType.LLM)
        elif primary == EngineType.LLM:
            chain.append(EngineType.ERROR)

        return chain

    # ── Logging ────────────────────────────────────────────────────────────

    def _log_decision(self, decision: RouteDecision) -> None:
        """Log a route decision."""
        logger.info(
            "Task %s: %s → %s (cache=%s, fallback=%d, ms=%.1f, valid=%s)",
            decision.task_id[:8],
            decision.classification.value,
            decision.selected_engine.value,
            decision.cache_hit,
            decision.fallback_count,
            decision.execution_ms,
            decision.validation.value,
        )

        # Store in history
        self._task_history.append(decision)

    # ── Statistics ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics."""
        return {
            "total_tasks": len(self._task_history),
            "cache_hit_rate": self._cache_hit_rate(),
            "classification_distribution": self._classification_distribution(),
            "engine_distribution": self._engine_distribution(),
            "worker_stats": {
                name: stats.to_dict()
                for name, stats in self._worker_stats.items()
            },
        }

    def _cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if not self._task_history:
            return 0.0
        hits = sum(1 for d in self._task_history if d.cache_hit)
        return hits / len(self._task_history)

    def _classification_distribution(self) -> Dict[str, int]:
        """Get classification distribution."""
        dist: Dict[str, int] = {}
        for decision in self._task_history:
            key = decision.classification.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def _engine_distribution(self) -> Dict[str, int]:
        """Get engine selection distribution."""
        dist: Dict[str, int] = {}
        for decision in self._task_history:
            key = decision.selected_engine.value
            dist[key] = dist.get(key, 0) + 1
        return dist

    def clear_history(self) -> int:
        """Clear task history. Returns count cleared."""
        count = len(self._task_history)
        self._task_history.clear()
        return count
