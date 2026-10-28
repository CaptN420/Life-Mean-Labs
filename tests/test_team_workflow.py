"""Tests for team_workflow.py — verifies the 3-tier pipeline structure."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_lab.team_workflow import (
    ROLE_PROMPTS,
    TeamPipeline,
    TeamTurn,
    ValidatorResult,
    run_validator,
    _junior_task,
    _mid_task,
    _senior_task,
)


# ── Role prompt tests ──────────────────────────────────────────────────────

def test_role_prompts_defined():
    """All four roles have system prompts."""
    for role in ("ARCHITECT", "JUNIOR", "MID", "SENIOR"):
        assert role in ROLE_PROMPTS
        assert len(ROLE_PROMPTS[role]) > 50


def test_junior_task_contains_spec():
    task = _junior_task("build a calculator", "python", "modules: calc.py")
    assert "calculator" in task
    assert "calc.py" in task
    assert "```python" in task


def test_mid_task_contains_source():
    source = "def add(a, b): return a + b\n"
    task = _mid_task(source, "1 failed", "python")
    assert "def add" in task
    assert "1 failed" in task


def test_senior_task_contains_source():
    source = "def compute(x): return x * 2\n"
    task = _senior_task(source, "all passed", "python")
    assert "def compute" in task
    assert "REVIEW" in task


# ── Validator tests ────────────────────────────────────────────────────────

def test_validator_no_python_files(tmp_path: Path):
    result = run_validator(tmp_path, "main.py")
    assert not result.passed
    assert "no_python_files" in result.errors


def test_validator_syntax_error(tmp_path: Path):
    (tmp_path / "main.py").write_text("def broken((", encoding="utf-8")
    result = run_validator(tmp_path, "main.py")
    assert not result.passed
    assert not result.compile_ok


def test_validator_substantive_code(tmp_path: Path):
    """A file with only a dict literal is NOT substantive."""
    (tmp_path / "main.py").write_text("{}", encoding="utf-8")
    result = run_validator(tmp_path, "main.py")
    assert not result.passed
    assert "phantom_output" in result.errors


def test_validator_passes_with_test(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (tmp_path / "test_main.py").write_text(
        "from main import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8"
    )
    result = run_validator(tmp_path, "main.py", "test_main.py")
    assert result.passed
    assert result.pytest_passed == 1


def test_validator_compiles_but_no_tests(tmp_path: Path):
    """Compiles but no tests → not passed (no evidence)."""
    (tmp_path / "main.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    result = run_validator(tmp_path, "main.py")
    assert not result.passed  # no tests ran


# ── Pipeline structure tests ───────────────────────────────────────────────

def test_pipeline_initial_state():
    with tempfile.TemporaryDirectory() as tmp:
        pipe = TeamPipeline(Path(tmp), language="python")
        assert pipe.architect_spec == ""
        assert len(pipe.turns) == 0


def test_pipeline_run_full_no_llm_returns_failed(tmp_path: Path):
    """Without an LLM client the pipeline fails gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
        pipe = TeamPipeline(ws, language="python")
        result = pipe.run_full("build calculator")
        assert result["final_status"] in ("architect_failed", "junior_failed",
                                           "mid_failed", "senior_failed")


def test_pipeline_turn_summary():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        pipe = TeamPipeline(ws, language="python")
        # Manually add a turn to test summary
        v = ValidatorResult(passed=True, compile_ok=True,
                            pytest_passed=3, pytest_failed=0, pytest_total=3)
        pipe.turns.append(TeamTurn(role="JUNIOR", phase=1, response="code", validator=v))
        summary = pipe.get_turn_summary()
        assert "JUNIOR" in summary
        assert "PASS" in summary


# ── ValidatorResult serialization ─────────────────────────────────────────

def test_validator_result_to_dict():
    v = ValidatorResult(passed=True, compile_ok=True,
                        pytest_passed=5, pytest_failed=1, pytest_total=6,
                        output="some output", errors=["e1"])
    d = v.to_dict()
    assert d["passed"] is True
    assert d["pytest_passed"] == 5
    assert d["errors"] == ["e1"]
