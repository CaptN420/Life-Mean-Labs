"""Tests for benchmark infrastructure (design doc §7, §18, §40)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from benchmarks import BenchmarkSuite, BenchmarkRunner, BenchmarkTask, BenchmarkResult


# ---- BenchmarkTask ---------------------------------------------------------


def test_benchmark_task_creation():
    task = BenchmarkTask(
        task_id="math-001",
        description="Calculate 2 + 2",
        domain="math",
        difficulty=1,
        reasoning_type="calculation",
        ground_truth=4,
    )
    assert task.task_id == "math-001"
    assert task.ground_truth == 4
    assert task.to_dict()["task_id"] == "math-001"


def test_benchmark_task_serialization_roundtrip():
    original = BenchmarkTask(
        task_id="phys-002",
        description="F = ma, m=10, a=5",
        domain="physics",
        difficulty=2,
        reasoning_type="calculation",
        ground_truth=50.0,
        metadata={"source": "manual"},
    )
    restored = BenchmarkTask.from_dict(original.to_dict())
    assert restored.task_id == original.task_id
    assert restored.ground_truth == original.ground_truth
    assert restored.metadata == original.metadata


# ---- BenchmarkSuite --------------------------------------------------------


def test_suite_add_and_retrieve():
    suite = BenchmarkSuite(name="test")
    suite.add_task("t1", "2+2", "math", 1, 4)
    suite.add_task("t2", "3*5", "math", 1, 15)
    suite.add_task("t3", "F=ma, m=10, a=5", "physics", 2, 50.0)

    assert suite.size == 3
    assert suite.get_task("t1") is not None
    assert suite.get_task("nonexistent") is None
    assert len(suite.by_domain("math")) == 2
    assert len(suite.by_domain("physics")) == 1


def test_suite_save_and_load():
    suite = BenchmarkSuite(name="persist_test")
    suite.add_task("t1", "gcd(48, 180)", "math", 3, 12)
    suite.add_task("t2", "sin(0 degrees)", "math", 1, 0.0)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        suite.save(path)
        loaded = BenchmarkSuite.from_json(path)
        assert loaded.name == "persist_test"
        assert loaded.size == 2
        assert loaded.get_task("t1").ground_truth == 12
    finally:
        Path(path).unlink()


def test_suite_to_dict_structure():
    suite = BenchmarkSuite(name="struct")
    suite.add_task("t1", "desc", "math", 1, 42)
    data = suite.to_dict()
    assert data["name"] == "struct"
    assert data["task_count"] == 1
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["ground_truth"] == 42


# ---- BenchmarkRunner -------------------------------------------------------


def test_run_single_task_correct():
    suite = BenchmarkSuite(name="run_test")
    suite.add_task("t1", "2+2", "math", 1, 4)
    runner = BenchmarkRunner(suite)
    result = runner.run_task(suite.get_task("t1"), answer=4)
    assert result.is_correct is True
    assert result.score == 1.0


def test_run_single_task_incorrect():
    suite = BenchmarkSuite(name="run_test")
    suite.add_task("t1", "2+2", "math", 1, 4)
    runner = BenchmarkRunner(suite)
    result = runner.run_task(suite.get_task("t1"), answer=5)
    assert result.is_correct is False
    # Partial score for near-miss (diff=1, ground_truth=4 → score ≈ 0.75)
    assert result.score > 0.0


def test_run_single_task_no_answer():
    suite = BenchmarkSuite(name="run_test")
    suite.add_task("t1", "2+2", "math", 1, 4)
    runner = BenchmarkRunner(suite)
    result = runner.run_task(suite.get_task("t1"), answer=None)
    assert result.is_correct is False
    assert result.error == "No answer provided"


def test_run_all_tasks():
    suite = BenchmarkSuite(name="batch")
    suite.add_task("t1", "2+2", "math", 1, 4)
    suite.add_task("t2", "3*4", "math", 1, 12)
    suite.add_task("t3", "5-3", "math", 1, 2)
    runner = BenchmarkRunner(suite)

    def answer_fn(task):
        return task.ground_truth  # perfect answers

    results = runner.run_all(answer_fn)
    assert len(results) == 3
    assert all(r.is_correct for r in results)


def test_run_all_with_errors():
    suite = BenchmarkSuite(name="error_test")
    suite.add_task("t1", "2+2", "math", 1, 4)
    runner = BenchmarkRunner(suite)

    def answer_fn(task):
        if task.task_id == "t1":
            raise ValueError("simulated failure")
        return task.ground_truth

    results = runner.run_all(answer_fn)
    assert len(results) == 1
    assert results[0].error is not None
    assert results[0].is_correct is False


# ---- Statistics ------------------------------------------------------------


def test_compute_statistics():
    suite = BenchmarkSuite(name="stats")
    suite.add_task("t1", "2+2", "math", 1, 4)
    suite.add_task("t2", "3*4", "math", 1, 12)
    suite.add_task("t3", "5-3", "math", 2, 2)
    runner = BenchmarkRunner(suite)

    # t1 correct, t2 wrong, t3 correct
    runner.run_task(suite.get_task("t1"), answer=4)
    runner.run_task(suite.get_task("t2"), answer=0)
    runner.run_task(suite.get_task("t3"), answer=2)

    stats = runner.compute_statistics()
    assert stats["total"] == 3
    assert stats["correct"] == 2
    assert abs(stats["accuracy"] - 2 / 3) < 1e-6


def test_compute_statistics_by_domain():
    suite = BenchmarkSuite(name="domain_stats")
    suite.add_task("m1", "2+2", "math", 1, 4)
    suite.add_task("m2", "3*4", "math", 1, 12)
    suite.add_task("p1", "F=ma", "physics", 2, 50.0)
    runner = BenchmarkRunner(suite)

    runner.run_task(suite.get_task("m1"), answer=4)
    runner.run_task(suite.get_task("m2"), answer=0)  # wrong
    runner.run_task(suite.get_task("p1"), answer=50.0)

    stats = runner.compute_statistics()
    assert stats["by_domain"]["math"]["accuracy"] == 0.5
    assert stats["by_domain"]["physics"]["accuracy"] == 1.0


def test_compute_statistics_empty():
    runner = BenchmarkRunner(BenchmarkSuite(name="empty"))
    stats = runner.compute_statistics()
    assert stats["total"] == 0
    assert stats["accuracy"] == 0.0


# ---- Quality Gates ---------------------------------------------------------


def test_quality_gates_pass():
    suite = BenchmarkSuite(name="gates")
    suite.add_task("m1", "2+2", "math", 1, 4)
    suite.add_task("m2", "3*4", "math", 1, 12)
    runner = BenchmarkRunner(suite)
    runner.run_task(suite.get_task("m1"), answer=4)
    runner.run_task(suite.get_task("m2"), answer=12)

    gates = runner.check_quality_gates({"math": 0.7})
    assert gates["math"] is True


def test_quality_gates_fail():
    suite = BenchmarkSuite(name="gates_fail")
    suite.add_task("m1", "2+2", "math", 1, 4)
    suite.add_task("m2", "3*4", "math", 1, 12)
    runner = BenchmarkRunner(suite)
    runner.run_task(suite.get_task("m1"), answer=0)  # wrong
    runner.run_task(suite.get_task("m2"), answer=0)  # wrong

    gates = runner.check_quality_gates({"math": 0.7})
    assert gates["math"] is False


def test_quality_gates_missing_domain():
    """Domains with no results get 0.0 accuracy → fail the gate."""
    suite = BenchmarkSuite(name="gates_miss")
    suite.add_task("m1", "2+2", "math", 1, 4)
    runner = BenchmarkRunner(suite)
    runner.run_task(suite.get_task("m1"), answer=4)

    gates = runner.check_quality_gates({"math": 0.7, "physics": 0.7})
    assert gates["math"] is True
    # physics has no data → 0.0 accuracy → gate fails
    assert gates["physics"] is False


# ---- Export ----------------------------------------------------------------


def test_export_results():
    suite = BenchmarkSuite(name="export_test")
    suite.add_task("t1", "2+2", "math", 1, 4)
    runner = BenchmarkRunner(suite)
    runner.run_task(suite.get_task("t1"), answer=4)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        runner.export_results(path)
        with open(path) as f:
            data = json.load(f)
        assert data["benchmark_id"] == "export_test"
        assert len(data["results"]) == 1
        assert data["results"][0]["is_correct"] is True
        assert "statistics" in data
    finally:
        Path(path).unlink()
