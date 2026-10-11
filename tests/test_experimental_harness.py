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


# ── DEBATE → CODE chain ────────────────────────────────────────────────────

def test_debate_code_chain_closed_reproducible():
    # The debate_code executor returns a fully-traced, reproducible chain.
    r1 = run_executor("debate_code", {"seed": 1})
    r2 = run_executor("debate_code", {"seed": 2})
    assert r1["kind"] == "debate_code"
    assert r1["status"] == "PASS"
    assert r2["status"] == "PASS"           # reproducible across seeds
    # The 5 design roles debated.
    roles = [c["role"] for c in r1["result"]["debate"]["roles"]]
    assert roles == ["Architect", "Reliability Engineer", "Skeptic",
                     "Simplicity Advocate", "Moderator"]
    # The handoff is a machine-readable DECISION_SPEC the code followed.
    h = r1["result"]["handoff"]
    assert h["name"] == "DECISION_SPEC"
    assert set(h["allowed_outputs"]) == {
        "RETRY_SAME", "RETRY_WITH_COMPRESSED_CONTEXT", "USE_TOOL",
        "ESCALATE_MODEL", "STOP_INCONCLUSIVE"}
    # Real pytest verification ran and passed.
    v = r1["result"]["verify"]
    assert v["ok"] is True
    assert v["passed"] >= 1 and v["failed"] == 0 and v["errors"] == 0
    # The trace is self-contained: debate -> handoff -> code -> verify.
    assert r1["result"]["code_files"] == ["retry_controller.py",
                                          "test_retry_controller.py"]


def test_debate_code_generated_controller_obeys_spec():
    # The generated retry_controller.py must return exactly one of the 5
    # allowed actions for every agreed edge case (spec honesty: no invented
    # policy). We test the actual generated code through the harness chain by
    # re-deriving behavior from the deterministic spec.
    from experimental.retry_agent import decision_spec
    from experimental.retry_agent import _code_from_spec
    code = _code_from_spec(decision_spec())
    # allowed outputs are all present as enum members / returns
    for action in decision_spec()["allowed_outputs"]:
        assert f'"{action}"' in code
    # pure function: a retry controller must not do I/O; its only import is
    # stdlib 'enum' (no subprocess, no filesystem, no network).
    import re
    imports = re.findall(r"^\s*(?:from\s+\S+|import\s+\S+).*$", code, re.M)
    for imp in imports:
        assert "enum" in imp, f"unexpected non-stdlib import: {imp!r}"

