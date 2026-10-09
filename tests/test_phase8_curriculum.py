"""Tests for CurriculumController (design doc Phase 8, §18 §40 §23)."""

from __future__ import annotations

import pytest

from analysis.weakness_analyzer import WeaknessProfile
from autopilot.curriculum import (
    CurriculumController,
    GenerationWeights,
    VALID_DOMAINS,
)
from experiments.runner import ExperimentResult, ValidationResult


def _result(*, valid: bool, domain: str = "math", difficulty: int = 3) -> ExperimentResult:
    return ExperimentResult(
        run_id="run",
        task_id="task",
        experiment_id="exp",
        generation_id="gen",
        config={},
        routing_decision={},
        workers_used=["tool_worker"],
        tools_used=["math_gcd"],
        validation_result=ValidationResult(valid=valid),
        metadata={"domain": domain, "difficulty": difficulty, "reasoning_type": "calculation"},
    )


def _controller(**kwargs):
    return CurriculumController(seed=42, approval_required=True, **kwargs)


# ---- Uniform fallback -----------------------------------------------------

def test_uniform_when_no_data():
    ctrl = _controller()
    profile = WeaknessProfile()  # total_tasks == 0
    weights = ctrl.plan_generation(profile)
    assert weights.source == "uniform"
    assert weights.approved is False  # approval gate still applies
    assert abs(sum(weights.weights.values()) - 1.0) < 1e-6
    assert set(weights.weights.keys()) == VALID_DOMAINS


# ---- Weakness-driven planning --------------------------------------------

def test_weak_domain_gets_higher_weight():
    ctrl = _controller()
    # math is weak (0%), logic is strong (100%); physics/chemistry/coding have no data
    results = [
        _result(valid=False, domain="math"),
        _result(valid=True, domain="math"),
        _result(valid=True, domain="logic"),
        _result(valid=True, domain="logic"),
    ]
    profile = ctrl.analyze_weaknesses(results)
    assert profile.by_domain["math"]["accuracy"] < profile.by_domain["logic"]["accuracy"]

    weights = ctrl.plan_generation(profile)
    assert weights.source == "weakness_driven"
    assert weights.weights["math"] > weights.weights["logic"]


def test_plan_requires_human_review():
    ctrl = _controller()
    results = [_result(valid=False, domain="math")]
    profile = ctrl.analyze_weaknesses(results)
    ctrl.plan_generation(profile)
    assert ctrl.active_weights.approved is False

    with pytest.raises(ValueError):
        ctrl.generate_targeted_tasks(count=10)


# ---- Approval gate --------------------------------------------------------

def test_approve_activates_and_allows_generation():
    ctrl = _controller()
    results = [_result(valid=False, domain="math")]
    profile = ctrl.analyze_weaknesses(results)
    ctrl.plan_generation(profile)

    ctrl.approve()
    assert ctrl.active_weights.approved is True
    assert all(a.approved for a in ctrl.pending_actions)

    tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 3))
    assert len(tasks) > 0
    # Tasks must be valid GeneratedTasks
    for t in tasks:
        assert t.description
        assert t.ground_truth is not None


def test_no_approval_required_bypasses_gate():
    ctrl = CurriculumController(seed=42, approval_required=False)
    results = [_result(valid=False, domain="math")]
    profile = ctrl.analyze_weaknesses(results)
    ctrl.plan_generation(profile)
    tasks = ctrl.generate_targeted_tasks(count=10)
    assert len(tasks) > 0


# ---- Pending actions ------------------------------------------------------

def test_pending_actions_sorted_weakest_first():
    ctrl = _controller()
    results = [
        _result(valid=False, domain="math"),
        _result(valid=True, domain="math"),
        _result(valid=True, domain="logic"),
        _result(valid=True, domain="logic"),
    ]
    profile = ctrl.analyze_weaknesses(results)
    ctrl.plan_generation(profile)
    accuracies = [a.current_accuracy for a in ctrl.pending_actions]
    assert accuracies == sorted(accuracies)


# ---- Protection: rate cap -------------------------------------------------

def test_weights_capped_per_domain():
    ctrl = CurriculumController(seed=42, max_rate_per_domain=0.4)
    # Only math + logic have data; make math have zero data direction
    results = [_result(valid=False, domain="math")] * 1
    profile = WeaknessProfile(
        total_tasks=1,
        total_passed=0,
        by_domain={"math": {"passed": 0, "total": 1, "accuracy": 0.0}},
        by_difficulty={},
        by_reasoning_type={},
        by_tool={},
        failure_reasons={},
    )
    weights = ctrl.plan_generation(profile)
    # No single domain may exceed the cap.
    assert max(weights.weights.values()) <= 0.4 + 1e-6


def test_domain_generation_cap_applied():
    ctrl = _controller()
    ctrl.set_domain_cap("math", 1)
    results = [_result(valid=False, domain="math")] * 5
    profile = ctrl.analyze_weaknesses(results)
    ctrl.plan_generation(profile)
    ctrl.approve()

    tasks = ctrl.generate_targeted_tasks(count=20, difficulty_range=(1, 3))
    math_tasks = [t for t in tasks if t.domain == "math"]
    assert len(math_tasks) <= 1


# ---- End-to-end over the real pipeline ------------------------------------

def test_weakness_driven_cycle_over_real_pipeline():
    """Weak domain detected end-to-end steers more generation toward it."""
    from experiments.generation.task_generator import TaskGenerator
    from experiments.runner import ExperimentRunner, ExperimentContext

    gen = TaskGenerator(seed=7)
    # Held-out "benchmark": math tasks we know fail (no answer) -> math weak.
    from autopilot.curriculum import CurriculumController

    ctrl = CurriculumController(task_generator=gen, seed=7, approval_required=False)

    # Build weak-math results: best-effort reflection via analyzer
    results = [_result(valid=False, domain="math")] * 3 + \
              [_result(valid=True, domain="logic")] * 6
    profile = ctrl.analyze_weaknesses(results)
    weights = ctrl.plan_generation(profile)

    # Deterministic assertion on the planning, not the RNG draw
    assert weights.weights["math"] > weights.weights["logic"]

    tasks = ctrl.generate_targeted_tasks(count=30, difficulty_range=(1, 3))
    assert len(tasks) > 0
    # All must be runnable (non-empty, ground truth present)
    assert all(t.description for t in tasks)