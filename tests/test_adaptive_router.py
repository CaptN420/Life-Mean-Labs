"""Tests for core.router.adaptive module."""
from __future__ import annotations

import pytest

from core.router.adaptive import (
    AdaptiveRouter,
    CostConfig,
    EngineType,
    ResultValidator,
    RouteDecision,
    TaskClassifier,
    TaskClassification,
    ValidationStatus,
    WorkerStats,
)


class TestTaskClassifier:
    """Test task classification."""

    def test_deterministic_math(self):
        classifier = TaskClassifier()
        result = classifier.classify("Calculate gcd of 48 and 180")
        assert result == TaskClassification.DETERMINISTIC

    def test_deterministic_tool(self):
        classifier = TaskClassifier()
        assert classifier.is_deterministic_tool("math_gcd")
        assert classifier.is_deterministic_tool("physics_force")
        assert not classifier.is_deterministic_tool("unknown_xyz")

    def test_computational(self):
        classifier = TaskClassifier()
        result = classifier.classify("Numerical integration using finite element method")
        assert result == TaskClassification.COMPUTATIONAL

    def test_reasoning(self):
        classifier = TaskClassifier()
        result = classifier.classify("Analyze the philosophical implications")
        assert result == TaskClassification.REASONING

    def test_unknown(self):
        classifier = TaskClassifier()
        result = classifier.classify("")
        assert result == TaskClassification.UNKNOWN

    def test_short_description(self):
        classifier = TaskClassifier()
        result = classifier.classify("calc")
        assert result == TaskClassification.DETERMINISTIC


class TestResultValidator:
    """Test result validation."""

    def test_valid_result(self):
        validator = ResultValidator()
        assert validator.validate("math_gcd", {"valid": True, "result": 12}) == ValidationStatus.VERIFIED

    def test_invalid_result(self):
        validator = ResultValidator()
        assert validator.validate("math_gcd", {"valid": False, "error": "bad input"}) == ValidationStatus.INVALID

    def test_none_result(self):
        validator = ResultValidator()
        assert validator.validate("math_gcd", None) == ValidationStatus.INVALID

    def test_primitive_result(self):
        validator = ResultValidator()
        assert validator.validate("math_gcd", 42) == ValidationStatus.VERIFIED


class TestWorkerStats:
    """Test worker statistics."""

    def test_success_rate_empty(self):
        stats = WorkerStats(name="test")
        assert stats.success_rate == 0.5  # Default

    def test_success_rate_calculation(self):
        stats = WorkerStats(name="test")
        stats.success_count = 8
        stats.failure_count = 2
        assert stats.success_rate == 0.8

    def test_avg_execution_ms(self):
        stats = WorkerStats(name="test")
        stats.success_count = 2
        stats.total_execution_ms = 100.0
        assert stats.avg_execution_ms == 50.0


class TestCostConfig:
    """Test cost configuration."""

    def test_default_scores(self):
        config = CostConfig()
        score = config.score(0.8, 1.0, 100, 50.0)
        assert score > 0

    def test_lower_is_better(self):
        config = CostConfig()
        good = config.score(0.9, 0.5, 50, 10.0)
        bad = config.score(0.5, 2.0, 200, 100.0)
        assert good < bad


class TestAdaptiveRouter:
    """Test adaptive router."""

    def test_route_deterministic(self):
        router = AdaptiveRouter()
        decision = router.route("task-001", "Calculate gcd of 48 and 180", tool_name="math_gcd", kwargs={"a": 48, "b": 180})
        assert decision.classification == TaskClassification.DETERMINISTIC
        assert decision.selected_engine in (EngineType.DETERMINISTIC, EngineType.CACHE)

    def test_route_computational(self):
        router = AdaptiveRouter()
        decision = router.route("task-002", "Numerical integration using finite element method")
        assert decision.classification == TaskClassification.COMPUTATIONAL

    def test_route_reasoning(self):
        router = AdaptiveRouter()
        decision = router.route("task-003", "Analyze philosophical argument", tool_name=None)
        assert decision.classification == TaskClassification.REASONING

    def test_stats_tracking(self):
        router = AdaptiveRouter()
        router.update_worker_stats("DETERMINISTIC", success=True, execution_ms=10.0)
        router.update_worker_stats("DETERMINISTIC", success=False, execution_ms=5.0)

        stats = router.get_worker_stats("DETERMINISTIC")
        assert stats is not None
        assert stats.success_rate == 0.5

    def test_get_stats(self):
        router = AdaptiveRouter()
        router.route("task-001", "Calculate gcd", tool_name="math_gcd", kwargs={"a": 1, "b": 2})
        stats = router.get_stats()
        assert "total_tasks" in stats
        assert stats["total_tasks"] == 1

    def test_clear_history(self):
        router = AdaptiveRouter()
        router.route("task-001", "Calculate gcd", tool_name="math_gcd")
        count = router.clear_history()
        assert count == 1
        assert len(router._task_history) == 0


class TestRouteDecision:
    """Test route decision serialization."""

    def test_to_dict(self):
        decision = RouteDecision(
            task_id="test-001",
            classification=TaskClassification.DETERMINISTIC,
            validation=ValidationStatus.VERIFIED,
            selected_engine=EngineType.CACHE,
            cache_hit=True,
        )
        d = decision.to_dict()
        assert d["task_id"] == "test-001"
        assert d["classification"] == "DETERMINISTIC"
        assert d["cache_hit"] is True

    def test_to_json(self):
        decision = RouteDecision(
            task_id="test-001",
            classification=TaskClassification.DETERMINISTIC,
            validation=ValidationStatus.VERIFIED,
            selected_engine=EngineType.CACHE,
        )
        json_str = decision.to_json()
        assert "test-001" in json_str
