"""Compare V1 tests (design doc M1 / §26).

Covers: RAW loader (aggregation, NOT_REACHED != FAIL), pairwise comparability
classification (HIGHLY_CONTROLLED / PARTIALLY_CONTROLLED / EXPLORATORY /
NOT_DIRECTLY_COMPARABLE + minimal/legacy honesty), findings separation
(OBSERVATION / HYPOTHESIS / REPAIR_CANDIDATE), controlled-vs-exploratory
hypothesis gating, failure patterns, and the read-only property of Compare
(it never writes RAW).

Tests write their own RAW fixtures into a tmp directory — they never touch
the real data/raw_debates store.
"""

import json
import math

import pytest

from compare.comparability import compare_pair
from compare.loader import (
    CompareLoadError,
    aggregate,
    default_raw_dir,
    load_experiment,
    list_available_experiments,
    task_record_from_line,
)
from compare.models import (
    ComparabilityKind,
    FindingKind,
    RunMetrics,
    TaskRecord,
)
from compare.analyzer import CompareEngine


# ── RAW fixture helpers ────────────────────────────────────────────────────
def _line(experiment_id, run_id, task_id, valid, domain="math",
          difficulty=1, tools=None, score=1.0, method="deterministic",
          error=None):
    """Build one RAW JSONL object (matches the real schema)."""
    vr = {"valid": valid, "score": score, "method": method, "error": error,
          "evidence": {"answer": 1, "ground_truth": 1}}
    return {
        "run_id": run_id, "task_id": task_id, "experiment_id": experiment_id,
        "generation_id": f"gen_{experiment_id}",
        "config": {"domain": domain, "num_tasks": 100, "seed": 42,
                   "difficulty_range": [1, 5], "deterministic": True,
                   "debate": False},
        "tools_used": tools or ["math_gcd"],
        "workers_used": ["tool_worker"],
        "answer": 1, "ground_truth": 1,
        "validation_result": vr,
        "metadata": {"domain": domain, "difficulty": difficulty},
        "timestamp": 1791537757,
    }


def _write_raw(tmp_path, experiment_id, lines):
    p = tmp_path / f"{experiment_id}.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(json.dumps(ln) + "\n")
    return tmp_path


def _run(experiment_id, tasks=None, condition=None):
    from compare.loader import aggregate as _agg
    return _agg(tasks or [], condition or {"domain": "math", "num_tasks": 10, "seed": 1},
                experiment_id, f"run_{experiment_id}")


def _rec(valid, **kw):
    return TaskRecord(task_id=kw.get("task_id", "t"),
                      run_id="r", experiment_id="e", domain="math",
                      difficulty=1, valid=valid,
                      tools_used=kw.get("tools_used", []),
                      workers_used=[], failure_reason=kw.get("failure_reason", ""))


# ── loader ─────────────────────────────────────────────────────────────────
def test_load_experiment_aggregates_raw(tmp_path):
    _write_raw(tmp_path, "exp_a", [
        _line("exp_a", "run_a", "t1", True, difficulty=1),
        _line("exp_a", "run_a", "t2", False, difficulty=2,
              method="no_answer", score=0.0),
        _line("exp_a", "run_a", "t3", True, difficulty=3),
    ])
    m = load_experiment("exp_a", tmp_path)
    assert m.num_tasks == 3
    assert m.num_passed == 2
    assert m.num_failed == 1
    assert m.success_rate == pytest.approx(2 / 3)
    assert m.by_difficulty["diff_1"]["passed"] == 1
    assert m.failure_reasons.get("no_answer_computed") == 1


def test_no_verdict_is_not_fail(tmp_path):
    # A line with NO validation verdict is NOT_REACHED, never counted as FAIL.
    line = _line("exp_a", "run_a", "t1", None)
    del line["validation_result"]
    _write_raw(tmp_path, "exp_a", [line])
    m = load_experiment("exp_a", tmp_path)
    assert m.num_tasks == 1
    assert m.num_passed == 0
    assert m.num_failed == 0
    assert m.num_no_verdict == 1
    assert m.failure_reasons == {}


def test_task_record_from_line_tolerates_legacy_shapes():
    # Missing metadata / tools_used must not crash.
    line = {"task_id": "t", "experiment_id": "e", "run_id": "r",
            "validation_result": {"valid": "true", "score": "1.0"}}
    rec = task_record_from_line(line)
    assert rec.valid is True
    assert rec.tools_used == []
    assert rec.domain == ""


def test_aggregate_empty_is_honest():
    m = aggregate([], {}, "exp_x")
    assert m.num_tasks == 0 and m.success_rate == 0.0 and not m.has_verdicts


def test_load_missing_raises(tmp_path):
    with pytest.raises(CompareLoadError):
        load_experiment("exp_missing", tmp_path)


# ── comparability ──────────────────────────────────────────────────────────
def test_identical_conditions_highly_controlled():
    l = _run("a", [_rec(True)], condition={"domain": "math", "num_tasks": 5, "seed": 1})
    r = _run("b", [_rec(True)], condition={"domain": "math", "num_tasks": 5, "seed": 1})
    p = compare_pair(l, r)
    assert p.comparability == ComparabilityKind.HIGHLY_CONTROLLED
    assert p.changed_variables == {}


def test_single_var_diff_highly_controlled():
    l = _run("a", condition={"domain": "math", "num_tasks": 5, "seed": 1})
    r = _run("b", condition={"domain": "math", "num_tasks": 20, "seed": 1})
    p = compare_pair(l, r)
    assert p.comparability == ComparabilityKind.HIGHLY_CONTROLLED
    assert set(p.changed_variables) == {"num_tasks"}


def test_multi_var_diff_partially_controlled():
    l = _run("a", condition={"domain": "math", "num_tasks": 5, "seed": 1, "debate": True})
    r = _run("b", condition={"domain": "math", "num_tasks": 50, "seed": 2, "debate": False})
    p = compare_pair(l, r)
    assert p.comparability == ComparabilityKind.PARTIALLY_CONTROLLED


def test_different_domain_exploratory():
    l = _run("a", condition={"domain": "math", "num_tasks": 5, "seed": 1})
    r = _run("b", condition={"domain": "physics", "num_tasks": 5, "seed": 1})
    p = compare_pair(l, r)
    assert p.comparability == ComparabilityKind.EXPLORATORY


def test_minimal_legacy_condition_is_exploratory_not_controlled():
    # Only 'domain' recorded (legacy/minimal): we must NOT claim control
    # just because the single recorded var matches.
    l = _run("a", condition={"domain": "math"})
    r = _run("b", condition={"domain": "math"})
    assert l.condition == {"domain": "math"}
    p = compare_pair(l, r)
    assert p.comparability == ComparabilityKind.EXPLORATORY


def test_self_comparison_not_directly_comparable():
    l = _run("a", condition={"domain": "math", "num_tasks": 5, "seed": 1})
    p = compare_pair(l, l)
    assert p.comparability == ComparabilityKind.NOT_DIRECTLY_COMPARABLE


# ── findings: separation + controlled gating ───────────────────────────────
def test_controlled_diff_yields_observation_and_hypothesis():
    l = _run("a", [_rec(True, task_id="t1")],
             condition={"domain": "math", "num_tasks": 10, "seed": 1})
    r = _run("b", [_rec(False, task_id="t2", failure_reason="incorrect_answer")],
             condition={"domain": "math", "num_tasks": 10, "seed": 2})
    eng = CompareEngine()
    out = eng.compare(["a", "b"], runs=[l, r])
    kinds = {f.kind for f in out.findings}
    assert FindingKind.OBSERVATION in kinds
    assert FindingKind.HYPOTHESIS in kinds
    assert FindingKind.REPAIR_CANDIDATE not in kinds  # no failing tool signature


def test_exploratory_diff_never_yields_hypothesis():
    l = _run("a", [_rec(True)], condition={"domain": "math"})  # minimal
    r = _run("b", [_rec(False, task_id="t2", failure_reason="incorrect_answer")],
             condition={"domain": "physics"})
    eng = CompareEngine()
    out = eng.compare(["a", "b"], runs=[l, r])
    for f in out.findings:
        assert f.kind != FindingKind.HYPOTHESIS, f.message


def test_identical_conditions_diff_suggests_stochastic_variance():
    l = _run("a", [_rec(True)], condition={"domain": "math", "num_tasks": 5, "seed": 1})
    r = _run("b", [_rec(False, task_id="t2", failure_reason="incorrect_answer")],
             condition={"domain": "math", "num_tasks": 5, "seed": 1})
    out = CompareEngine().compare(["a", "b"], runs=[l, r])
    hyp = [f for f in out.findings if f.kind == FindingKind.HYPOTHESIS]
    assert hyp and "stochastic" in hyp[0].message


def test_tool_on_failing_task_is_repair_candidate():
    l = _run("a", [_rec(True)], condition={"domain": "math", "num_tasks": 3, "seed": 1})
    r = _run("b", [_rec(False, task_id="t2", tools_used=["tests.run"],
                       failure_reason="test_failure")],
             condition={"domain": "math", "num_tasks": 3, "seed": 1})
    out = CompareEngine().compare(["a", "b"], runs=[l, r])
    rc = [f for f in out.findings if f.kind == FindingKind.REPAIR_CANDIDATE]
    assert rc and "tests.run" in rc[0].message


def test_no_verdict_all_reported_not_fail():
    r = _run("a", [_rec(None, task_id="t1"), _rec(None, task_id="t2")],
             condition={"domain": "math", "num_tasks": 2, "seed": 1})
    out = CompareEngine().compare(["a"], runs=[r])
    obs = [f for f in out.findings if FindingKind.OBSERVATION]
    assert obs and "not a measured fail" in obs[-1].message


# ── failure patterns ───────────────────────────────────────────────────────
def test_failure_pattern_across_runs():
    runs = [
        _run("a", [_rec(False, task_id="t1", tools_used=["math_gcd"],
                        failure_reason="incorrect_answer")],
             condition={"domain": "math", "num_tasks": 2, "seed": 1}),
        _run("b", [_rec(False, task_id="t2", tools_used=["math_gcd"],
                        failure_reason="incorrect_answer")],
             condition={"domain": "math", "num_tasks": 2, "seed": 1}),
    ]
    out = CompareEngine().compare(["a", "b"], runs=runs)
    assert len(out.failure_patterns) == 1
    pat = out.failure_patterns[0]
    assert pat.failure_reason == "incorrect_answer"
    assert pat.runs == ["a", "b"] and pat.count == 2


# ── read-only guarantees ───────────────────────────────────────────────────
def test_compare_is_read_only_over_raw(tmp_path):
    _write_raw(tmp_path, "exp_a", [
        _line("exp_a", "run_a", "t1", True),
        _line("exp_a", "run_a", "t2", False, method="no_answer", score=0.0),
    ])
    before = (tmp_path / "exp_a.jsonl").read_bytes()
    CompareEngine().compare(["exp_a"], runs=[load_experiment("exp_a", tmp_path)])
    after = (tmp_path / "exp_a.jsonl").read_bytes()
    assert before == after  # Compare never rewrites RAW


def test_default_raw_dir_points_at_repo():
    d = default_raw_dir()
    assert d.name == "raw_debates"
    assert "Life_mean" in str(d)