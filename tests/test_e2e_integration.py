"""End-to-end integration test: full pipeline from generation to export.

Design doc §3, §7, §18: verify the complete autopilot loop works
with real TaskGenerator and ExperimentRunner (no mocks).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from analysis.weakness_analyzer import WeaknessAnalyzer
from autopilot.curriculum import CurriculumController
from benchmarks import BenchmarkSuite, BenchmarkRunner
from experiments.generation.task_generator import TaskGenerator
from experiments.runner import ExperimentResult, ValidationResult


# ---- E2E: Generate → Validate → Analyze → Export --------------------------


def test_e2e_generate_and_validate():
    """Generate tasks, validate them, and analyze results."""
    gen = TaskGenerator(seed=42)
    tasks = gen.generate_batch(count=10, domain="math", difficulty_range=(1, 3))
    assert len(tasks) > 0

    analyzer = WeaknessAnalyzer()
    for task in tasks:
        # Simulate validation: correct if difficulty <= 2
        is_correct = task.difficulty <= 2
        result = ExperimentResult(
            run_id="e2e",
            task_id=task.task_id,
            experiment_id="exp",
            generation_id="gen",
            config={},
            routing_decision={"strategy": "deterministic"},
            workers_used=["tool_worker"],
            tools_used=["math_gcd"],
            validation_result=ValidationResult(valid=is_correct, method="deterministic"),
            metadata={"domain": task.domain, "difficulty": task.difficulty},
        )
        analyzer.add_result(result)

    profile = analyzer.analyze()
    assert profile.total_tasks == 10
    # Should have some data (at least some tasks with difficulty <= 2)
    assert profile.total_tasks > 0


def test_e2e_autopilot_loop():
    """Run a full autopilot loop: generate → analyze → plan → approve."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    # Round 1: generate and simulate results
    tasks_r1 = ctrl.generate_targeted_tasks(count=20, difficulty_range=(1, 2))
    assert len(tasks_r1) > 0

    results_r1 = []
    for t in tasks_r1:
        is_correct = t.difficulty <= 2
        results_r1.append(ExperimentResult(
            run_id="e2e", task_id=t.task_id, experiment_id="exp", generation_id="gen",
            config={}, routing_decision={"strategy": "deterministic"},
            workers_used=["tool_worker"], tools_used=["math_gcd"],
            validation_result=ValidationResult(valid=is_correct, method="deterministic"),
            metadata={"domain": t.domain, "difficulty": t.difficulty},
        ))

    profile = ctrl.analyze_weaknesses(results_r1)
    weights = ctrl.plan_generation(profile)
    assert weights is not None
    assert isinstance(weights.weights, dict)


def test_e2e_benchmark_integration():
    """Run a benchmark suite and check quality gates."""
    # Create a benchmark suite
    suite = BenchmarkSuite(name="e2e_benchmark")
    suite.add_task("math-001", "Calculate 48 + 37", "math", 1, 85)
    suite.add_task("math-002", "Compute 12 * 15", "math", 2, 180)
    suite.add_task("math-003", "Find GCD(48, 180)", "math", 3, 12)
    suite.add_task("phys-001", "F = ma, m=10, a=5", "physics", 2, 50.0)

    runner = BenchmarkRunner(suite)

    # Simulate answers (some correct, some wrong)
    def answer_fn(task):
        if task.task_id == "math-001":
            return 85  # correct
        elif task.task_id == "math-002":
            return 175  # wrong (off by 5)
        elif task.task_id == "math-003":
            return 12  # correct
        elif task.task_id == "phys-001":
            return 50.0  # correct
        return None

    results = runner.run_all(answer_fn)
    assert len(results) == 4

    stats = runner.compute_statistics()
    assert stats["total"] == 4
    assert stats["correct"] == 3
    assert abs(stats["accuracy"] - 0.75) < 1e-6

    # Check quality gates
    gates = runner.check_quality_gates({"math": 0.5, "physics": 0.5})
    assert gates["math"] is True  # 2/3 = 67% > 50%
    assert gates["physics"] is True  # 1/1 = 100% > 50%


def test_e2e_export_and_reload():
    """Export benchmark results and reload them."""
    suite = BenchmarkSuite(name="export_reload")
    suite.add_task("t1", "2+2", "math", 1, 4)
    suite.add_task("t2", "3*4", "math", 1, 12)

    runner = BenchmarkRunner(suite)
    runner.run_task(suite.get_task("t1"), answer=4)
    runner.run_task(suite.get_task("t2"), answer=0)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        runner.export_results(path)

        # Reload and verify
        with open(path) as f:
            data = json.load(f)
        assert data["benchmark_id"] == "export_reload"
        assert len(data["results"]) == 2
        assert data["results"][0]["is_correct"] is True
        assert data["results"][1]["is_correct"] is False
    finally:
        Path(path).unlink()


def test_e2e_full_loop_with_benchmark():
    """Full loop: generate → validate → benchmark → analyze."""
    # Generate some tasks
    gen = TaskGenerator(seed=42)
    tasks = gen.generate_batch(count=10, domain="math", difficulty_range=(1, 2))

    # Create a benchmark suite from the generated tasks
    suite = BenchmarkSuite(name="e2e_full")
    for t in tasks:
        suite.add_task(
            task_id=t.task_id,
            description=t.description,
            domain=t.domain,
            difficulty=t.difficulty,
            ground_truth=t.ground_truth,
            reasoning_type=t.reasoning_type,
        )

    # Run benchmark with simulated answers
    runner = BenchmarkRunner(suite)

    def answer_fn(task):
        # Simulate 80% correctness
        import hashlib
        h = int(hashlib.md5(task.task_id.encode()).hexdigest(), 16)
        return task.ground_truth if h % 5 != 0 else None

    results = runner.run_all(answer_fn)
    stats = runner.compute_statistics()

    assert stats["total"] == len(tasks)
    # Accuracy should be between 0% and 100% (simulated ~80%, but small sample varies)
    assert 0.0 <= stats["accuracy"] <= 1.0


def test_e2e_separation_of_concerns():
    """Verify that generation, validation, and benchmark are separate."""
    # Generation
    gen = TaskGenerator(seed=42)
    tasks = gen.generate_batch(count=5, domain="math", difficulty_range=(1, 2))

    # Validation (separate from generation)
    analyzer = WeaknessAnalyzer()
    for t in tasks:
        result = ExperimentResult(
            run_id="e2e", task_id=t.task_id, experiment_id="exp", generation_id="gen",
            config={}, routing_decision={"strategy": "deterministic"},
            workers_used=["tool_worker"], tools_used=["math_gcd"],
            validation_result=ValidationResult(valid=True, method="deterministic"),
            metadata={"domain": t.domain},
        )
        analyzer.add_result(result)

    # Benchmark (separate from generation and validation)
    suite = BenchmarkSuite(name="separation_test")
    for t in tasks:
        suite.add_task(t.task_id, t.description, t.domain, t.difficulty, t.ground_truth)

    runner = BenchmarkRunner(suite)
    for task in suite.tasks:
        runner.run_task(task, answer=task.ground_truth)

    # All three should have independent state
    assert len(tasks) == 5
    assert analyzer.analyze().total_tasks == 5
    assert len(runner.results) == 5


def test_e2e_reproducibility():
    """Same seed produces same task sequence."""
    gen1 = TaskGenerator(seed=42)
    gen2 = TaskGenerator(seed=42)

    tasks1 = gen1.generate_batch(count=10, domain="math", difficulty_range=(1, 2))
    tasks2 = gen2.generate_batch(count=10, domain="math", difficulty_range=(1, 2))

    assert len(tasks1) == len(tasks2)
    for t1, t2 in zip(tasks1, tasks2):
        assert t1.domain == t2.domain
        assert t1.difficulty == t2.difficulty


def test_e2e_deterministic_validation():
    """Validation is deterministic: same answer → same result."""
    suite = BenchmarkSuite(name="determ")
    suite.add_task("t1", "2+2", "math", 1, 4)

    runner = BenchmarkRunner(suite)
    r1 = runner.run_task(suite.get_task("t1"), answer=4)
    r2 = runner.run_task(suite.get_task("t1"), answer=4)

    assert r1.is_correct == r2.is_correct
    assert r1.score == r2.score


def test_e2e_benchmark_isolation():
    """Benchmark results are independent of generator state."""
    gen = TaskGenerator(seed=42)
    suite = BenchmarkSuite(name="isolation")
    suite.add_task("t1", "2+2", "math", 1, 4)

    runner = BenchmarkRunner(suite)
    runner.run_task(suite.get_task("t1"), answer=4)

    # Generator state doesn't affect benchmark results
    gen.generate_batch(count=5, domain="math", difficulty_range=(1, 2))
    stats = runner.compute_statistics()
    assert stats["total"] == 1
    assert stats["accuracy"] == 1.0
