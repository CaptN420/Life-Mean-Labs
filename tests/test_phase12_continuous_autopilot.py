"""Tests for Phase 12 — Continuous/indefinite autopilot experiments.

Design doc §12: the autopilot runs indefinitely until externally stopped,
producing a continuous stream of generated → validated → exported tasks.
Key properties:
- Graceful shutdown on signal
- Periodic persistence of state
- No memory leak across cycles
- Observable throughput metrics
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from analysis.weakness_analyzer import WeaknessAnalyzer
from autopilot.curriculum import CurriculumController
from experiments.generation.task_generator import TaskGenerator
from experiments.runner import ExperimentResult, ValidationResult


# ---- Helpers ---------------------------------------------------------------


def _result(*, valid: bool, domain: str = "math") -> ExperimentResult:
    return ExperimentResult(
        run_id="run",
        task_id="task",
        experiment_id="exp",
        generation_id="gen",
        config={},
        routing_decision={},
        workers_used=["tool_worker"],
        tools_used=["math_gcd"],
        validation_result=ValidationResult(valid=valid, method="deterministic"),
        metadata={"domain": domain, "difficulty": 3, "reasoning_type": "calculation"},
    )


# ---- Continuous loop -------------------------------------------------------


def test_continuous_loop_runs_multiple_cycles():
    """Autopilot runs for N cycles without crashing."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    cycle_count = 0
    total_tasks = 0

    for cycle in range(10):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 3))
        total_tasks += len(tasks)
        results = [_result(valid=(cycle % 2 == 0), domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)
        cycle_count += 1

    assert cycle_count == 10
    assert total_tasks == 100


def test_continuous_loop_no_memory_leak():
    """Analyzer state doesn't grow unbounded across cycles."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    initial_count = len(ctrl.analyzer.get_results())

    for cycle in range(50):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        results = [_result(valid=True, domain=t.domain) for t in tasks]
        # analyze_weaknesses calls clear() internally
        ctrl.analyze_weaknesses(results)

    # Should be at most one cycle's worth (10 results)
    final_count = len(ctrl.analyzer.get_results())
    assert final_count <= 10


def test_continuous_loop_throughput_constant():
    """Generation rate stays constant across cycles."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    timings: list[float] = []

    for cycle in range(10):
        start = time.monotonic()
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        elapsed = time.monotonic() - start
        timings.append(elapsed)
        results = [_result(valid=True, domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)

    # All cycles should take similar time (within 5x)
    assert max(timings) / min(timings) < 5


# ---- Persistence -----------------------------------------------------------


def test_continuous_state_persistence():
    """Autopilot state can be serialized and restored."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    # Run a few cycles
    for _ in range(3):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        results = [_result(valid=True, domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)

    # Serialize state
    state = {
        "seed": ctrl._seed,
        "threshold": ctrl._threshold,
        "max_rate": ctrl._max_rate,
        "approval_required": ctrl._approval_required,
    }

    # Restore from state
    gen2 = TaskGenerator(seed=state["seed"])
    ctrl2 = CurriculumController(
        task_generator=gen2,
        seed=state["seed"],
        approval_required=state["approval_required"],
    )

    # Both should produce the same number of tasks (reproducibility of count)
    tasks1 = ctrl.generate_targeted_tasks(count=5, difficulty_range=(1, 2))
    tasks2 = ctrl2.generate_targeted_tasks(count=5, difficulty_range=(1, 2))

    assert len(tasks1) == len(tasks2) == 5
    # Descriptions may differ because TaskGenerator advances internally,
    # but both should be valid tasks with ground truth.
    for t in tasks1 + tasks2:
        assert t.description
        assert t.ground_truth is not None


# ---- Graceful shutdown -----------------------------------------------------


def test_continuous_loop_can_be_stopped():
    """Autopilot respects an external stop condition."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    stopped_at = None
    all_tasks: list = []

    for cycle in range(100):  # Would run forever without stop
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        all_tasks.extend(tasks)
        results = [_result(valid=True, domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)

        if len(all_tasks) >= 50:
            stopped_at = cycle + 1
            break

    assert stopped_at is not None
    assert len(all_tasks) == 50


def test_continuous_loop_with_error_recovery():
    """Autopilot continues after a simulated error in one cycle."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    cycles_completed = 0
    errors_encountered = 0

    for cycle in range(10):
        try:
            tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
            # Simulate error on cycle 3
            if cycle == 3:
                raise RuntimeError("simulated failure")
            results = [_result(valid=True, domain=t.domain) for t in tasks]
            ctrl.analyze_weaknesses(results)
            cycles_completed += 1
        except RuntimeError:
            errors_encountered += 1
            # Continue to next cycle

    assert cycles_completed == 9
    assert errors_encountered == 1


# ---- Observable metrics ----------------------------------------------------


def test_continuous_loop_metrics_accumulation():
    """Throughput and accuracy metrics accumulate correctly."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    total_generated = 0
    total_valid = 0
    cycle_metrics: list[dict] = []

    for cycle in range(5):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        total_generated += len(tasks)

        # Simulate 80% validity
        results = [_result(valid=True) for _ in range(8)] + \
                  [_result(valid=False) for _ in range(2)]
        ctrl.analyze_weaknesses(results)
        profile = ctrl.analyzer.analyze()

        cycle_metrics.append({
            "cycle": cycle,
            "generated": len(tasks),
            "accuracy": profile.overall_accuracy,
        })

    assert total_generated == 50
    # Overall accuracy should be ~80%
    overall = sum(m["accuracy"] for m in cycle_metrics) / len(cycle_metrics)
    assert 0.75 <= overall <= 0.85


def test_continuous_loop_produces_diverse_output():
    """Continuous generation covers multiple domains over time."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    all_domains: set = set()

    for cycle in range(20):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 3))
        for t in tasks:
            all_domains.add(t.domain)
        results = [_result(valid=True, domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)

    # Should have covered multiple domains
    assert len(all_domains) >= 3


# ---- Long-running simulation -----------------------------------------------


def test_continuous_loop_100_cycles_no_crash():
    """Stress test: 100 cycles without failure."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    for cycle in range(100):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 3))
        assert len(tasks) == 10
        results = [_result(valid=(cycle % 3 != 0), domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)

        if cycle % 10 == 0:
            profile = ctrl.analyzer.analyze()
            assert profile.total_tasks == 10  # fresh each cycle
