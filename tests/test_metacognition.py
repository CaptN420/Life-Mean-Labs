"""Tests for metacognitive memory and monitor modules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from experiments.metacognition.memory import MetacognitiveMemory
from experiments.metacognition.monitor import MetacognitiveMonitor
from experiments.metacognition.schemas import ErrorPattern, RunMemory, StrategyComparison


class TestRunMemory:
    """Tests for RunMemory schema."""

    def test_create_run_memory(self) -> None:
        memory = RunMemory(
            run_id="test_run_001",
            project="test_project",
            status="failed",
            prompt="Create a function",
            constraints=["type hints", "docstring"],
            domain="coding",
            router_used="smart_router",
            errors_detected=[{"type": "empty_response", "description": "No output"}],
        )

        assert memory.run_id == "test_run_001"
        assert memory.status == "failed"
        assert len(memory.errors_detected) == 1

    def test_to_dict_roundtrip(self) -> None:
        original = RunMemory(
            run_id="test_run_002",
            project="test_project",
            status="passed",
            prompt="Build a calculator",
            constraints=["addition", "subtraction"],
            domain="math",
            router_used="smart_router",
            models_selected=["gpt-4"],
            plan_proposed="Step-by-step implementation",
            duration_seconds=120.5,
            iterations=3,
        )

        data = original.to_dict()
        restored = RunMemory.from_dict(data)

        assert restored.run_id == original.run_id
        assert restored.status == original.status
        assert restored.constraints == original.constraints
        assert restored.duration_seconds == original.duration_seconds

    def test_default_timestamps(self) -> None:
        memory = RunMemory(
            run_id="test_run_003",
            project="test_project",
            status="passed",
        )

        assert memory.created_at != ""
        assert memory.updated_at != ""


class TestMetacognitiveMemory:
    """Tests for MetacognitiveMemory storage."""

    @pytest.fixture
    def memory_store(self, tmp_path: Path) -> MetacognitiveMemory:
        storage = tmp_path / "metacognition" / "memory.json"
        return MetacognitiveMemory(storage_path=storage)

    def test_save_and_retrieve_run(self, memory_store: MetacognitiveMemory) -> None:
        memory = RunMemory(
            run_id="run_001",
            project="project_a",
            status="passed",
            prompt="Test prompt",
        )

        memory_store.save_run_memory(memory)
        retrieved = memory_store.get_run_memory("run_001")

        assert retrieved is not None
        assert retrieved.run_id == "run_001"
        assert retrieved.status == "passed"

    def test_list_runs_by_project(self, memory_store: MetacognitiveMemory) -> None:
        for i in range(3):
            memory = RunMemory(
                run_id=f"run_{i:03d}",
                project="project_a",
                status="passed" if i % 2 == 0 else "failed",
            )
            memory_store.save_run_memory(memory)

        runs = memory_store.list_runs_by_project("project_a")
        assert len(runs) == 3

    def test_detect_error_patterns(self, memory_store: MetacognitiveMemory) -> None:
        for i in range(3):
            memory = RunMemory(
                run_id=f"run_{i:03d}",
                project="project_a",
                status="failed",
                errors_detected=[{"type": "empty_response", "description": "No output"}],
            )
            memory_store.save_run_memory(memory)

        runs = memory_store.list_all_runs()
        patterns = memory_store.detect_error_patterns(runs)

        assert "empty_response" in patterns
        assert patterns["empty_response"].occurrence_count == 3

    def test_add_strategy_comparison(
        self, memory_store: MetacognitiveMemory
    ) -> None:
        comparison = StrategyComparison(
            strategy_a="router_a",
            strategy_b="router_b",
            tasks_compared=10,
            success_rate_a=0.8,
            success_rate_b=0.6,
            conclusion="router_a is better",
        )

        key = memory_store.add_strategy_comparison(comparison)
        retrieved = memory_store.get_strategy_comparison("router_a", "router_b")

        assert retrieved is not None
        assert retrieved.strategy_a == "router_a"
        assert retrieved.success_rate_a == 0.8

    def test_clear_project(self, memory_store: MetacognitiveMemory) -> None:
        for i in range(3):
            memory = RunMemory(
                run_id=f"run_{i:03d}",
                project="project_a",
                status="passed",
            )
            memory_store.save_run_memory(memory)

        removed = memory_store.clear_project("project_a")
        assert removed == 3
        assert len(memory_store.list_all_runs()) == 0

    def test_get_statistics(self, memory_store: MetacognitiveMemory) -> None:
        for i in range(5):
            memory = RunMemory(
                run_id=f"run_{i:03d}",
                project="project_a",
                status="passed" if i < 3 else "failed",
            )
            memory_store.save_run_memory(memory)

        stats = memory_store.get_statistics()
        assert stats["total_runs"] == 5
        assert stats["passed"] == 3
        assert stats["failed"] == 2
        assert stats["success_rate"] == 0.6


class TestMetacognitiveMonitor:
    """Tests for MetacognitiveMonitor analysis."""

    @pytest.fixture
    def monitor(self, tmp_path: Path) -> MetacognitiveMonitor:
        storage = tmp_path / "metacognition" / "memory.json"
        memory = MetacognitiveMemory(storage_path=storage)
        return MetacognitiveMonitor(memory)

    def test_analyze_run_success(self, monitor: MetacognitiveMonitor) -> None:
        memory = RunMemory(
            run_id="run_001",
            project="project_a",
            status="passed",
            agent_traces=[{"agent": "PLANNER", "ok": True}],
            test_results={"passed": 5, "total": 5},
            final_verdict="passed",
        )
        monitor._memory.save_run_memory(memory)

        analysis = monitor.analyze_run("run_001")
        assert analysis is not None
        assert analysis["success"] is True
        assert len(analysis["issues"]) == 0

    def test_analyze_run_failure(self, monitor: MetacognitiveMonitor) -> None:
        memory = RunMemory(
            run_id="run_002",
            project="project_a",
            status="failed",
            agent_traces=[
                {"agent": "PLANNER", "ok": True},
                {"agent": "DEVELOPER", "ok": False, "response": ""},
            ],
            errors_detected=[{"type": "empty_response", "description": "No output"}],
        )
        monitor._memory.save_run_memory(memory)

        analysis = monitor.analyze_run("run_002")
        assert analysis is not None
        assert analysis["success"] is False
        assert any(i["type"] == "empty_response" for i in analysis["issues"])

    def test_analyze_run_missing_with_retry(self, monitor: MetacognitiveMonitor) -> None:
        """Test that analyze_run retries when run is missing."""
        # Run should not exist
        analysis = monitor.analyze_run("nonexistent_run")
        assert analysis is None

    def test_analyze_run_insufficient_tokens(self, monitor: MetacognitiveMonitor) -> None:
        """Test fallback when tokens are insufficient."""
        memory = RunMemory(
            run_id="run_003",
            project="project_a",
            status="failed",
            tokens_used=None,
            duration_seconds=0.0,
            agent_traces=[],
        )
        monitor._memory.save_run_memory(memory)

        analysis = monitor.analyze_run("run_003")
        assert analysis is not None
        assert analysis["needs_retry"] is True
        assert "retry_message" in analysis
        assert "subsequent attempt" in analysis["retry_message"]

    def test_check_token_sufficiency(self, monitor: MetacognitiveMonitor) -> None:
        """Test token sufficiency checks."""
        # Insufficient: no tokens and no traces
        memory1 = RunMemory(
            run_id="run_004",
            project="project_a",
            status="failed",
            tokens_used=None,
            duration_seconds=0.0,
            agent_traces=[],
        )
        assert monitor._check_token_sufficiency(memory1) is True

        # Sufficient: has traces
        memory2 = RunMemory(
            run_id="run_005",
            project="project_a",
            status="passed",
            tokens_used=1000,
            duration_seconds=60.0,
            agent_traces=[{"agent": "PLANNER", "ok": True}],
        )
        assert monitor._check_token_sufficiency(memory2) is False

    def test_detect_recurring_errors(self, monitor: MetacognitiveMonitor) -> None:
        for i in range(3):
            memory = RunMemory(
                run_id=f"run_{i:03d}",
                project="project_a",
                status="failed",
                errors_detected=[{"type": "empty_response", "description": "No output"}],
            )
            monitor._memory.save_run_memory(memory)

        result = monitor.detect_recurring_errors()
        assert "empty_response" in result["recurring_errors"]
        assert len(result["recurring_errors"]["empty_response"]) == 3

    def test_compare_verdicts_to_tests(self, monitor: MetacognitiveMonitor) -> None:
        # Run with matching verdict
        memory1 = RunMemory(
            run_id="run_001",
            project="project_a",
            status="passed",
            test_results={"passed": 5, "total": 5},
            final_verdict="passed",
        )
        monitor._memory.save_run_memory(memory1)

        # Run with mismatched verdict
        memory2 = RunMemory(
            run_id="run_002",
            project="project_a",
            status="failed",
            test_results={"passed": 1, "total": 5},
            final_verdict="passed",
        )
        monitor._memory.save_run_memory(memory2)

        result = monitor.compare_verdicts_to_tests()
        assert result["total_compared"] == 2
        assert result["matches"] == 1
        assert result["mismatches"] == 1

    def test_generate_report(self, monitor: MetacognitiveMonitor) -> None:
        memory = RunMemory(
            run_id="run_001",
            project="project_a",
            status="passed",
            domain="coding",
            agent_traces=[{"agent": "PLANNER", "ok": True}],
            test_results={"passed": 5, "total": 5},
            final_verdict="passed",
        )
        monitor._memory.save_run_memory(memory)

        report = monitor.generate_report()
        assert "overall_stats" in report
        assert "recurring_errors" in report
        assert "verdict_accuracy" in report


class TestErrorPattern:
    """Tests for ErrorPattern schema."""

    def test_to_dict_roundtrip(self) -> None:
        pattern = ErrorPattern(
            error_type="empty_response",
            description="DEVELOPER returned empty output",
            occurrence_count=3,
            affected_runs=["run_001", "run_002", "run_003"],
        )

        data = pattern.to_dict()
        restored = ErrorPattern.from_dict(data)

        assert restored.error_type == pattern.error_type
        assert restored.occurrence_count == 3
        assert len(restored.affected_runs) == 3


class TestStrategyComparison:
    """Tests for StrategyComparison schema."""

    def test_to_dict_roundtrip(self) -> None:
        comparison = StrategyComparison(
            strategy_a="router_a",
            strategy_b="router_b",
            tasks_compared=10,
            success_rate_a=0.8,
            success_rate_b=0.6,
            conclusion="router_a is better",
        )

        data = comparison.to_dict()
        restored = StrategyComparison.from_dict(data)

        assert restored.strategy_a == comparison.strategy_a
        assert restored.success_rate_a == 0.8
        assert restored.conclusion == comparison.conclusion
