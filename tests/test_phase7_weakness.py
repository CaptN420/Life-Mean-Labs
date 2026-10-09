"""Tests for WeaknessAnalyzer (design doc Phase 7, §7 §18 §40)."""

from __future__ import annotations

from experiments.runner import ExperimentResult, ValidationResult
from analysis.weakness_analyzer import WeaknessAnalyzer, WeaknessProfile


def _result(
    *,
    valid: bool,
    domain: str = "math",
    difficulty: int = 3,
    reasoning_type: str = "calculation",
    tools: list = None,
    error: str = None,
) -> ExperimentResult:
    vr = ValidationResult(valid=valid, method="deterministic", error=error)
    return ExperimentResult(
        run_id="run",
        task_id="task",
        experiment_id="exp",
        generation_id="gen",
        config={},
        routing_decision={},
        workers_used=["tool_worker"],
        tools_used=tools or ["math_gcd"],
        validation_result=vr,
        metadata={
            "domain": domain,
            "difficulty": difficulty,
            "reasoning_type": reasoning_type,
        },
    )


def test_profile_empty_when_no_results():
    analyzer = WeaknessAnalyzer()
    profile = analyzer.analyze()
    assert isinstance(profile, WeaknessProfile)
    assert profile.total_tasks == 0
    assert profile.overall_accuracy == 0.0


def test_overall_accuracy():
    analyzer = WeaknessAnalyzer()
    analyzer.add_results([
        _result(valid=True),
        _result(valid=False),
        _result(valid=True),
    ])
    profile = analyzer.analyze()
    assert profile.total_tasks == 3
    assert profile.total_passed == 2
    assert abs(profile.overall_accuracy - 2 / 3) < 1e-6


def test_by_domain_accuracy():
    analyzer = WeaknessAnalyzer()
    analyzer.add_results([
        _result(valid=True, domain="math"),
        _result(valid=False, domain="math"),
        _result(valid=True, domain="logic"),
    ])
    profile = analyzer.analyze()
    assert profile.by_domain["math"]["accuracy"] == 0.5
    assert profile.by_domain["logic"]["accuracy"] == 1.0
    assert profile.by_domain["math"]["passed"] == 1
    assert profile.by_domain["math"]["total"] == 2


def test_by_difficulty():
    analyzer = WeaknessAnalyzer()
    analyzer.add_results([
        _result(valid=True, difficulty=1),
        _result(valid=False, difficulty=5),
        _result(valid=True, difficulty=5),
    ])
    profile = analyzer.analyze()
    assert profile.by_difficulty["diff_1"]["accuracy"] == 1.0
    assert profile.by_difficulty["diff_5"]["accuracy"] == 0.5


def test_by_reasoning_type():
    analyzer = WeaknessAnalyzer()
    analyzer.add_results([
        _result(valid=True, reasoning_type="calculation"),
        _result(valid=False, reasoning_type="debugging"),
    ])
    profile = analyzer.analyze()
    assert profile.by_reasoning_type["calculation"]["accuracy"] == 1.0
    assert profile.by_reasoning_type["debugging"]["accuracy"] == 0.0


def test_by_tool():
    analyzer = WeaknessAnalyzer()
    analyzer.add_results([
        _result(valid=True, tools=["math_gcd"]),
        _result(valid=False, tools=["math_lcm"]),
    ])
    profile = analyzer.analyze()
    assert profile.by_tool["math_gcd"]["accuracy"] == 1.0
    assert profile.by_tool["math_lcm"]["accuracy"] == 0.0


def test_failure_reasons():
    analyzer = WeaknessAnalyzer()
    analyzer.add_results([
        _result(valid=True),
        _result(valid=False, error="No answer computed"),
        _result(valid=False, error="No answer computed"),
        _result(valid=False, error="tool execution failed"),
    ])
    profile = analyzer.analyze()
    assert profile.failure_reasons["No answer computed"] == 2
    assert profile.failure_reasons["tool execution failed"] == 1


def test_weak_domains_threshold():
    analyzer = WeaknessAnalyzer(accuracy_threshold=0.7)
    analyzer.add_results([
        _result(valid=True, domain="math"),
        _result(valid=False, domain="math"),
        _result(valid=True, domain="logic"),
    ])
    profile = analyzer.analyze()
    assert "math" in profile.weak_domains  # 0.5 < 0.7
    assert "logic" not in profile.weak_domains  # 1.0 >= 0.7


def test_weakest_dimension():
    analyzer = WeaknessAnalyzer()
    analyzer.add_results([
        _result(valid=False, domain="math"),
        _result(valid=True, domain="logic"),
    ])
    weakest = analyzer.weakest_dimension()
    assert weakest["domain"] == "math"
    assert weakest["accuracy"] == 0.0


def test_clear_resets():
    analyzer = WeaknessAnalyzer()
    analyzer.add_result(_result(valid=True))
    assert len(analyzer.get_results()) == 1
    analyzer.clear()
    assert len(analyzer.get_results()) == 0
    assert analyzer.analyze().total_tasks == 0


def test_profile_serialization():
    analyzer = WeaknessAnalyzer()
    analyzer.add_result(_result(valid=True, domain="math"))
    data = analyzer.analyze().to_dict()
    assert data["total_tasks"] == 1
    assert data["overall_accuracy"] == 1.0
    assert "by_domain" in data
    assert "weak_domains" in data