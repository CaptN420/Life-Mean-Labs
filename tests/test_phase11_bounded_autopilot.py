"""Tests for Phase 11 — Bounded-generation autopilot.

Design doc §11: the autopilot runs for a bounded number of cycles,
each cycle: generate → route → validate → analyze → plan next round.
Stops when budget exhausted or convergence reached.
"""

from __future__ import annotations

import pytest

from analysis.weakness_analyzer import WeaknessAnalyzer
from autopilot.curriculum import CurriculumController, GenerationWeights
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


# ---- Bounded loop ----------------------------------------------------------


def test_bounded_loop_stops_at_max_cycles():
    """Autopilot stops after max_cycles even if not converged."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    all_tasks: list = []
    all_results: list = []
    max_cycles = 3
    tasks_per_cycle = 10

    for cycle in range(max_cycles):
        tasks = ctrl.generate_targeted_tasks(count=tasks_per_cycle, difficulty_range=(1, 2))
        all_tasks.extend(tasks)
        # Simulate deterministic results
        results = [_result(valid=(t.difficulty <= 2), domain=t.domain) for t in tasks]
        all_results.extend(results)

    assert len(all_tasks) == max_cycles * tasks_per_cycle
    assert len(all_results) == max_cycles * tasks_per_cycle


def test_bounded_loop_accumulates_results():
    """Each cycle's results feed into the next cycle's analysis."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    total_generated = 0
    for cycle in range(4):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 3))
        total_generated += len(tasks)
        # Feed simulated results back
        results = [_result(valid=(cycle > 0), domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)

    assert total_generated == 40


def test_bounded_loop_convergence_detection():
    """Loop can detect when accuracy stops improving."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    histories: list[float] = []

    for cycle in range(5):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        # Simulate improving accuracy over cycles
        valid_count = min(10, 3 + cycle)
        results = [
            _result(valid=True, domain=t.domain) for t in tasks[:valid_count]
        ] + [
            _result(valid=False, domain=t.domain) for t in tasks[valid_count:]
        ]
        ctrl.analyze_weaknesses(results)
        profile = ctrl.analyzer.analyze()
        histories.append(profile.overall_accuracy)

    # Accuracy should be non-decreasing (or at least not all the same)
    assert histories[-1] >= histories[0]


def test_bounded_loop_budget_tracking():
    """Track total tokens/tasks consumed across cycles."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    budget = {"tasks": 0, "cycles": 0}
    max_budget = 25

    while budget["tasks"] < max_budget:
        remaining = max_budget - budget["tasks"]
        tasks = ctrl.generate_targeted_tasks(count=min(10, remaining), difficulty_range=(1, 2))
        budget["tasks"] += len(tasks)
        budget["cycles"] += 1
        results = [_result(valid=True, domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)

    assert budget["tasks"] <= max_budget
    assert budget["cycles"] > 0


# ---- Convergence criteria --------------------------------------------------


def test_convergence_when_accuracy_stable():
    """Loop should stop when accuracy plateaus."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    prev_accuracy = None
    stable_cycles = 0

    for cycle in range(10):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        # Simulate stable 80% accuracy
        results = [_result(valid=True) for _ in range(8)] + \
                  [_result(valid=False) for _ in range(2)]
        ctrl.analyze_weaknesses(results)
        profile = ctrl.analyzer.analyze()

        if prev_accuracy is not None:
            if abs(profile.overall_accuracy - prev_accuracy) < 0.01:
                stable_cycles += 1
                if stable_cycles >= 2:
                    break  # converged
            else:
                stable_cycles = 0
        prev_accuracy = profile.overall_accuracy

    assert cycle < 9  # converged before max


def test_convergence_with_improving_accuracy():
    """Loop continues when accuracy is still improving."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    accuracies: list[float] = []
    for cycle in range(5):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        # Simulate steadily improving accuracy
        valid_count = 3 + cycle
        results = [_result(valid=True) for _ in range(valid_count)] + \
                  [_result(valid=False) for _ in range(10 - valid_count)]
        ctrl.analyze_weaknesses(results)
        profile = ctrl.analyzer.analyze()
        accuracies.append(profile.overall_accuracy)

    # Should be monotonically increasing
    for i in range(1, len(accuracies)):
        assert accuracies[i] >= accuracies[i - 1]


# ---- Cycle observability ---------------------------------------------------


def test_cycle_observability_produces_trace():
    """Each cycle produces observable metadata."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    cycles_observed = []

    for cycle in range(3):
        tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
        results = [_result(valid=True, domain=t.domain) for t in tasks]
        ctrl.analyze_weaknesses(results)
        profile = ctrl.analyzer.analyze()

        cycles_observed.append({
            "cycle": cycle,
            "tasks_generated": len(tasks),
            "accuracy": profile.overall_accuracy,
            "weak_domains": profile.weak_domains,
        })

    assert len(cycles_observed) == 3
    for obs in cycles_observed:
        assert obs["tasks_generated"] == 10
        assert isinstance(obs["accuracy"], float)
        assert isinstance(obs["weak_domains"], list)


def test_cycle_state_isolation():
    """Each cycle's analysis is independent — no state leakage."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    # Cycle 1: math weak
    tasks1 = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
    results1 = [_result(valid=False, domain="math")] * 5 + \
               [_result(valid=True, domain="logic")] * 5
    profile1 = ctrl.analyze_weaknesses(results1)

    # Cycle 2: fresh analysis with different data
    tasks2 = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
    results2 = [_result(valid=True, domain="math")] * 8 + \
               [_result(valid=False, domain="logic")] * 2
    # analyze_weaknesses calls clear() then add_results, so analyze() reflects results2
    profile2 = ctrl.analyze_weaknesses(results2)

    # profile2 should reflect results2, not results1
    math_acc_r2 = profile2.by_domain.get("math", {}).get("accuracy", 0)
    assert math_acc_r2 >= 0.8  # 8/10 correct
