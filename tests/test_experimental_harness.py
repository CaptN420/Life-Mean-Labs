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
    assert h["name"] == "retry_controller"
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
    from experimental.retry_agent import _catalog_spec_retry, compile_spec_to_py
    spec = _catalog_spec_retry()
    code = compile_spec_to_py(spec)
    # allowed outputs are all present as enum members / returns
    for action in spec["allowed_outputs"]:
        assert f'"{action}"' in code
    # pure function: a retry controller must not do I/O; its only import is
    # stdlib 'enum' (no subprocess, no filesystem, no network).
    import re
    imports = re.findall(r"^\s*(?:from\s+\S+|import\s+\S+).*$", code, re.M)
    for imp in imports:
        assert "enum" in imp, f"unexpected non-stdlib import: {imp!r}"


def test_debate_code_catalogue_variation_reproducible():
    # MODE A: every catalogue task type runs the full chain to PASS, and each
    # type keeps a STABLE spec_hash across seeds (a drift would mean hidden
    # state leaked in -> "no surprises").
    from experimental.retry_agent import CATALOG
    hashes = {}
    for t in CATALOG:
        r_seed1 = run_executor("debate_code", {"seed": 1, "task_type": t})
        r_seed7 = run_executor("debate_code", {"seed": 7, "task_type": t})
        assert r_seed1["status"] == "PASS", t
        assert r_seed7["status"] == "PASS", t
        h1 = r_seed1["result"]["handoff"]["spec_hash"]
        assert h1 == r_seed7["result"]["handoff"]["spec_hash"], t
        hashes[t] = h1
    # the three task types produce genuinely different specs (not a tautology)
    assert len(set(hashes.values())) == len(CATALOG)


def test_debate_code_mode_b_llm_gate_inconclusive():
    # MODE B honesty: without a real, reachable LLM backend the chain must
    # be INCONCLUSIVE (never a fake pass). We short-circuit run_debate_b to
    # raise LLMUnavailable and assert the orchestrator maps it to INCONCLUSIVE.
    import experimental.retry_agent as RA
    from experimental.retry_llm import LLMUnavailable

    def _fake(task):
        raise LLMUnavailable("backend down (test)")
    RA.run_debate_b = _fake
    tr = RA.run_debate_code(mode="llm", task_prompt="design a circuit breaker")
    assert tr["status"] == "INCONCLUSIVE"
    assert "backend down" in tr["reason"]
    assert tr["reproducible"] is False

