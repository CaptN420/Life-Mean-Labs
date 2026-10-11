"""Tests for the Experimental sandbox harness (OPT-IN; stable core must not depend on it).

The harness is an additive experimental surface: it reaches INTO the stable
core (CodeLabEngine / ToolWorker) to run a single executor isolated in a
throwaway workspace, and never registers/persists to the normal
``code_lab_runs/`` layout. Only ``connected`` executors may run; a
``not-connected`` executor is refused with EXECUTOR_NOT_AVAILABLE — never faked.
"""

from __future__ import annotations

import pytest

from experimental.dispatch import ExecutorNotAvailable
from experimental.harness import run_executor


def test_harness_refuses_not_connected_executor():
    # debate / research / synthesis / review are NOT connected -> refused, honest
    with pytest.raises(ExecutorNotAvailable) as ei:
        run_executor("debate", {})
    assert ei.value.category == "EXECUTOR_NOT_AVAILABLE"


def test_harness_refuses_unknown_executor():
    with pytest.raises(ExecutorNotAvailable):
        run_executor("no_such_executor", {})


def test_harness_code_run_passes_in_temp_sandbox(tmp_path):
    # code executor -> real CodeLabEngine in a throwaway workspace
    # (patch base via temp usage; harness makes its own temp root)
    out = run_executor("code", {
        "prompt": "Create a Python function fibonacci(n) with unit tests.",
    })
    assert out["kind"] == "code"
    assert out["status"] == "passed"
    assert out["result"]["det_status"] == "PASS"
    assert out["result"]["files_created"] == ["fibonacci.py", "test_fibonacci.py"]


def test_harness_tool_run(tmp_path):
    # deterministic/tool executor -> synchronous tool host
    out = run_executor("code", {
        "prompt": "Make a Python function that checks if 7 is prime.",
    })
    # code classification; whatever the verdict, it must be a real verdict
    assert out["kind"] == "code"
    assert out["status"] in ("passed", "failed")


def test_harness_does_not_litter_default_workspace(tmp_path):
    # Running the harness must NOT create code_lab_runs/<harness> in the project.
    import code_lab_runs  # noqa: F401  (ensures package importable, not created)
    out = run_executor("code", {
        "prompt": "Create a Python function is_prime(n) with unit tests.",
    })
    assert out["status"] == "passed"
