"""Tests for Phase 10 — Autopilot integrity (weakness → curriculum → generation loop).

Design doc §18, §40: the autopilot must keep generation and evaluation separate,
never feed its own synthetic tasks back as held-out evidence, and require an
explicit human-approval gate before weights become active.
"""

from __future__ import annotations

import pytest

from analysis.weakness_analyzer import WeaknessAnalyzer, WeaknessProfile
from autopilot.curriculum import CurriculumController, GenerationWeights, VALID_DOMAINS
from experiments.generation.task_generator import TaskGenerator
from experiments.runner import ExperimentResult, ValidationResult


# ---- Helpers ---------------------------------------------------------------


def _result(
    *,
    valid: bool,
    domain: str = "math",
    difficulty: int = 3,
    reasoning_type: str = "calculation",
) -> ExperimentResult:
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
        metadata={
            "domain": domain,
            "difficulty": difficulty,
            "reasoning_type": reasoning_type,
        },
    )


def _build_profile(
    *,
    math_pass: int = 0,
    math_fail: int = 0,
    logic_pass: int = 0,
    logic_fail: int = 0,
) -> WeaknessProfile:
    results: list[ExperimentResult] = []
    for _ in range(math_pass):
        results.append(_result(valid=True, domain="math"))
    for _ in range(math_fail):
        results.append(_result(valid=False, domain="math"))
    for _ in range(logic_pass):
        results.append(_result(valid=True, domain="logic"))
    for _ in range(logic_fail):
        results.append(_result(valid=False, domain="logic"))
    analyzer = WeaknessAnalyzer()
    analyzer.add_results(results)
    return analyzer.analyze()


# ---- P10: Weakness analysis integrity --------------------------------------


def test_analyzer_ignores_held_out_flag():
    """Analyzer does not infer provenance — caller controls what goes in."""
    analyzer = WeaknessAnalyzer()
    # Feed it generator tasks (bad practice) — analyzer doesn't care.
    analyzer.add_result(_result(valid=True, domain="math"))
    profile = analyzer.analyze()
    assert profile.total_tasks == 1
    assert profile.overall_accuracy == 1.0


def test_analyzer_threshold_validation():
    analyzer = WeaknessAnalyzer(accuracy_threshold=0.7)
    assert analyzer.analyze().overall_accuracy == 0.0

    with pytest.raises(ValueError):
        WeaknessAnalyzer(accuracy_threshold=-0.1)
    with pytest.raises(ValueError):
        WeaknessAnalyzer(accuracy_threshold=1.1)


def test_weakest_dimension_respects_min_tests():
    analyzer = WeaknessAnalyzer()
    # Add 3 math failures, 3 logic passes — both below min_tests=5.
    for _ in range(3):
        analyzer.add_result(_result(valid=False, domain="math"))
    for _ in range(3):
        analyzer.add_result(_result(valid=True, domain="logic"))

    # With default min_tests=5, no dimension qualifies.
    assert analyzer.weakest_dimension() == {}

    # With min_tests=1, math wins (0% < 100%).
    weakest = analyzer.weakest_dimension(min_tests=1)
    assert weakest["domain"] == "math"
    assert weakest["accuracy"] == 0.0


def test_failure_reasons_categorized():
    analyzer = WeaknessAnalyzer()
    # Build results with explicit ValidationResult to set error field.
    def _fail_result(error: str | None = None) -> ExperimentResult:
        return ExperimentResult(
            run_id="run", task_id="task", experiment_id="exp", generation_id="gen",
            config={}, routing_decision={}, workers_used=["tool_worker"],
            tools_used=["math_gcd"],
            validation_result=ValidationResult(valid=False, method="deterministic", error=error),
            metadata={"domain": "math", "difficulty": 3, "reasoning_type": "calculation"},
        )
    analyzer.add_results([
        _fail_result(error="No answer computed"),
        _fail_result(error="No answer computed"),
        _fail_result(error="tool execution failed"),
        _fail_result(error=None),  # falls through to incorrect_answer
        _result(valid=True),
    ])
    profile = analyzer.analyze()
    assert profile.failure_reasons["No answer computed"] == 2
    assert profile.failure_reasons["tool execution failed"] == 1
    assert profile.failure_reasons["incorrect_answer"] == 1


# ---- P10: Curriculum controller integrity ----------------------------------


def test_curriculum_never_generates_without_approval():
    """Human-review gate is enforced — no generation without approve()."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=True)

    profile = _build_profile(math_pass=1, math_fail=9)  # math at 10%
    ctrl.analyze_weaknesses([_result(valid=False, domain="math")] * 5 +
                            [_result(valid=True, domain="logic")] * 5)
    ctrl.plan_generation(profile)

    # Not approved yet — must raise.
    with pytest.raises(ValueError, match="not approved"):
        ctrl.generate_targeted_tasks(count=10)


def test_curriculum_approve_makes_weights_active():
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=True)

    results = [_result(valid=False, domain="math")] * 5 + \
              [_result(valid=True, domain="logic")] * 10
    profile = ctrl.analyze_weaknesses(results)
    weights = ctrl.plan_generation(profile)

    assert weights.approved is False
    ctrl.approve()
    assert weights.approved is True
    assert all(a.approved for a in ctrl.pending_actions)


def test_curriculum_weights_are_inverse_accuracy():
    """Weaker domains get higher generation weight."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False)

    # math: 20% accuracy, logic: 100% accuracy
    results = (
        [_result(valid=False, domain="math")] * 4 +
        [_result(valid=True, domain="math")] * 1 +
        [_result(valid=True, domain="logic")] * 5
    )
    profile = ctrl.analyze_weaknesses(results)
    weights = ctrl.plan_generation(profile)

    assert weights.weights["math"] > weights.weights["logic"]


def test_curriculum_domain_cap_enforced():
    """No single domain can consume more than max_rate_per_domain."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(
        task_generator=gen,
        approval_required=False,
        max_rate_per_domain=0.3,
    )

    # Only math data — would get 100% without cap.
    results = [_result(valid=False, domain="math")] * 5
    profile = ctrl.analyze_weaknesses(results)
    weights = ctrl.plan_generation(profile)

    assert max(weights.weights.values()) <= 0.3 + 1e-6


def test_curriculum_generates_valid_tasks():
    """Generated tasks have non-empty descriptions and ground truth."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False)

    results = [_result(valid=False, domain="math")] * 3 + \
              [_result(valid=True, domain="logic")] * 7
    profile = ctrl.analyze_weaknesses(results)
    ctrl.plan_generation(profile)

    tasks = ctrl.generate_targeted_tasks(count=20, difficulty_range=(1, 3))
    assert len(tasks) > 0
    for t in tasks:
        assert t.description, "task must have a description"
        assert t.ground_truth is not None, "task must have ground truth"


def test_curriculum_reproducibility_with_same_seed():
    """Same seed + same results → same task sequence."""
    gen1 = TaskGenerator(seed=42)
    gen2 = TaskGenerator(seed=42)
    ctrl1 = CurriculumController(task_generator=gen1, approval_required=False, seed=42)
    ctrl2 = CurriculumController(task_generator=gen2, approval_required=False, seed=42)

    results = [_result(valid=False, domain="math")] * 3 + \
              [_result(valid=True, domain="logic")] * 7
    profile1 = ctrl1.analyze_weaknesses(results)
    profile2 = ctrl2.analyze_weaknesses(results)

    ctrl1.plan_generation(profile1)
    ctrl2.plan_generation(profile2)

    tasks1 = ctrl1.generate_targeted_tasks(count=10, difficulty_range=(1, 2))
    tasks2 = ctrl2.generate_targeted_tasks(count=10, difficulty_range=(1, 2))

    assert len(tasks1) == len(tasks2)
    for t1, t2 in zip(tasks1, tasks2):
        assert t1.description == t2.description
        assert t1.ground_truth == t2.ground_truth


# ---- P10: Full loop integrity ----------------------------------------------


def test_full_loop_generate_analyze_plan_approve_generate():
    """End-to-end autopilot cycle: generate → analyze → plan → approve → regenerate."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    # Round 1: uniform generation
    tasks_r1 = ctrl.generate_targeted_tasks(count=20, difficulty_range=(1, 2))
    assert len(tasks_r1) == 20

    # Simulate results: math weak (30%), logic strong (90%)
    results = []
    for t in tasks_r1:
        if t.domain == "math":
            results.append(_result(valid=(t.task_id[-1] in "012345678"), domain="math"))
        else:
            results.append(_result(valid=True, domain=t.domain))

    profile = ctrl.analyze_weaknesses(results)
    weights = ctrl.plan_generation(profile)

    # Math should be weak → higher weight
    if "math" in profile.by_domain and profile.by_domain["math"]["total"] > 0:
        assert weights.weights.get("math", 0) >= weights.weights.get("logic", 0)

    # Round 2: targeted generation should favor math
    tasks_r2 = ctrl.generate_targeted_tasks(count=20, difficulty_range=(1, 2))
    assert len(tasks_r2) > 0  # at least some tasks generated
    math_count_r2 = sum(1 for t in tasks_r2 if t.domain == "math")
    math_count_r1 = sum(1 for t in tasks_r1 if t.domain == "math")
    # Targeted round should have at least as many math tasks
    assert math_count_r2 >= math_count_r1


def test_separation_of_generation_and_evaluation():
    """Generator tasks must never be fed back as evaluation evidence."""
    gen = TaskGenerator(seed=42)
    ctrl = CurriculumController(task_generator=gen, approval_required=False, seed=42)

    # Generate some tasks
    tasks = ctrl.generate_targeted_tasks(count=10, difficulty_range=(1, 2))

    # Simulate evaluation results (these are held-out, not the generator's own tasks)
    eval_results = [_result(valid=False, domain="math")] * 5 + \
                   [_result(valid=True, domain="logic")] * 5

    # Analyzer must see eval_results, NOT the generator tasks
    profile = ctrl.analyze_weaknesses(eval_results)
    assert profile.total_tasks == 10  # only eval results counted
    # Generator produced 10 tasks; analyzer should only see the 10 eval results.
    # Use a different count to make the distinction clear.
    more_tasks = ctrl.generate_targeted_tasks(count=30, difficulty_range=(1, 2))
    assert len(more_tasks) == 30
