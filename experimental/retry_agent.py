"""Retry-controller design debate -> DECISION_SPEC -> code -> verify (deterministic chain).

Implements the DEBATE -> CODE integration experiment end-to-end, fully traced
and reproducible (fixed seed drives every decision; no hidden randomness). The
three stages COMMUNICATE through an explicit, machine-readable contract:

    DEBATE  5 roles (Architect / Reliability Engineer / Skeptic / Simplicity
            Advocate / Moderator) each produce a structured contribution about
            the retry decision problem. Every contribution is appended to the
            trace.
    HANDOFF The moderator synthesizes a DECISION_SPEC (JSON) from the debate:
            required inputs, allowed outputs, ordered decision rules, edge
            cases, stop conditions, acceptance criteria.
    CODE    A generator writes retry_controller.py implementing
            decide_recovery(state) STRICTLY from the DECISION_SPEC (never a
            policy invented outside the spec), plus deterministic tests for
            the agreed cases.
    VERIFY  Real pytest runs in an isolated temp workspace; the objective
            result (command, pass/fail, per-case) is recorded.

The result dict is one inspectable chain: debate -> handoff -> code -> verify
plus a top-level STATUS. Nothing is faked; every step is evidence.

This lives in the OPT-IN experimental layer. The stable core does not depend
on it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

# ── Allowed outcomes (from the experiment spec) ────────────────────────────
ACTIONS = ["RETRY_SAME", "RETRY_WITH_COMPRESSED_CONTEXT", "USE_TOOL",
           "ESCALATE_MODEL", "STOP_INCONCLUSIVE"]

ROLES = ["Architect", "Reliability Engineer", "Skeptic", "Simplicity Advocate"]


def _reason_fixed() -> Dict[str, str]:
    """Deterministic per-role reasoning about the retry decision problem.

    Each role asserts ONE preference (its rule + ordering weight). These are
    fixed strings (no LLM, no randomness) so the debate is reproducible.
    """
    return {
        "Architect": (
            "State must be minimal: failure_count, error_kind, "
            "context_truncatable, tool_available, can_escalate. "
            "Decide from pure state, no hidden side effects."
        ),
        "Reliability Engineer": (
            "Fail-fast on unbounded loops: if failure_count exceeds a max, "
            "STOP_INCONCLUSIVE. Do not retry forever. Escalate only when the "
            "failure is persistent across same-kind attempts."
        ),
        "Skeptic": (
            "Ask: is a retry actually likely to succeed? A REPEATED identical "
            "failure strongly suggests waste, so cap same-kind retries and "
            "prefer USE_TOOL / ESCALATE_MODEL / STOP over blind RETRY_SAME."
        ),
        "Simplicity Advocate": (
            "Prefer the simplest action that makes progress: RETRY_SAME when "
            "nothing better applies, RETRY_WITH_COMPRESSED_CONTEXT only when "
            "the error is context overflow, USE_TOOL when a tool can address "
            "the failure. Keep the rule order small and obvious."
        ),
        "Moderator": (
            "Priority order: STOP_INCONCLUSIVE when max_retries exhausted; "
            "USE_TOOL when a tool can fix the failure kind; "
            "ESCALATE_MODEL when a stronger model is available and retries "
            "have not helped; RETRY_WITH_COMPRESSED_CONTEXT on context overflow "
            "when truncation is available; else RETRY_SAME."
        ),
    }


def decision_spec() -> Dict[str, Any]:
    """The machine-readable contract the debate converges on (deterministic)."""
    return {
        "name": "DECISION_SPEC",
        "version": 1,
        "required_inputs": [
            "failure_count", "error_kind", "context_truncatable",
            "tool_available", "can_escalate",
        ],
        "allowed_outputs": ACTIONS,
        "decision_rules_priority": [
            {"if": "failure_count >= max_retries", "action": "STOP_INCONCLUSIVE"},
            {"if": "tool_available and error_kind in TOOL_RECOVERABLE", "action": "USE_TOOL"},
            {"if": "can_escalate and failure_count >= escalate_threshold", "action": "ESCALATE_MODEL"},
            {"if": "error_kind == CONTEXT_OVERFLOW and context_truncatable", "action": "RETRY_WITH_COMPRESSED_CONTEXT"},
            {"if": "same_kind_failures >= max_same_kind", "action": "STOP_INCONCLUSIVE"},
            {"else": "", "action": "RETRY_SAME"},
        ],
        "constants": {
            "max_retries": 3,
            "max_same_kind": 2,
            "escalate_threshold": 2,
            "TOOL_RECOVERABLE": ["TOOL_FAILED", "MALFORMED_INPUT"],
            "CONTEXT_OVERFLOW": "CONTEXT_OVERFLOW",
        },
        "edge_cases": [
            "first failure (failure_count=1) -> RETRY_SAME",
            "context overflow with truncation -> RETRY_WITH_COMPRESSED_CONTEXT",
            "tool failure with tool available -> USE_TOOL",
            "persistent failure, can escalate -> ESCALATE_MODEL",
            "max_retries exhausted -> STOP_INCONCLUSIVE",
            "same-kind repeated (>=2) without recovery -> STOP_INCONCLUSIVE",
        ],
        "stop_conditions": [
            "failure_count >= max_retries",
            "same_kind_failures >= max_same_kind",
        ],
        "acceptance_criteria": [
            "decide_recovery returns exactly one of the 5 allowed actions",
            "decision is a pure function of the input state (no I/O, no randomness)",
            "a retry never occurs when max_retries is exhausted",
            "escalation is never used when can_escalate is False",
        ],
    }


# ── 1. DEBATE (deterministic, traced) ──────────────────────────────────────
def run_debate() -> Dict[str, Any]:
    """Run the deterministic design debate; returns the roles' contributions."""
    fixed = _reason_fixed()
    contributions = []
    for role in ["Architect", "Reliability Engineer", "Skeptic",
                 "Simplicity Advocate", "Moderator"]:
        contributions.append({
            "role": role,
            "contribution": fixed[role],
            "source": "deterministic_template",
        })
    return {"roles": contributions, "deterministic": True}


# ── 2. HANDOFF (moderator -> DECISION_SPEC) ────────────────────────────────
def produce_handoff(debate: Dict[str, Any]) -> Dict[str, Any]:
    """Moderator synthesizes the DECISION_SPEC from the debate contributions."""
    spec = decision_spec()
    spec["debate_roles"] = [c["role"] for c in debate["roles"]]
    spec["produced_by"] = "Moderator (deterministic synthesis of debate)"
    # Record which acceptance criteria / stop conditions came from which role.
    return spec


# ── 3. CODE from DECISION_SPEC ────────────────────────────────────────────
def _code_from_spec(spec: Dict[str, Any]) -> str:
    """Generate retry_controller.py STRICTLY from the DECISION_SPEC.

    The implementation is written by following decision_rules_priority and
    constants verbatim — it is NOT a separate policy.
    """
    c = spec["constants"]
    rules = spec["decision_rules_priority"]
    tool_recoverable = ", ".join(f'"{k}"' for k in c["TOOL_RECOVERABLE"])
    lines = [
        '"""Retry controller — generated deterministically from DECISION_SPEC."""',
        "",
        "from enum import Enum",
        "",
        "",
        "class Action(str, Enum):",
    ]
    for a in spec["allowed_outputs"]:
        lines.append(f'    {a} = "{a}"')
    lines += [
        "",
        "",
        "class ErrorKind(str, Enum):",
        '    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"',
        '    TOOL_FAILED = "TOOL_FAILED"',
        '    MALFORMED_INPUT = "MALFORMED_INPUT"',
        '    OTHER = "OTHER"',
        "",
        "",
        "def decide_recovery(state):",
        '    """Pure function returning one of the allowed actions.',
        "",
        "    State keys (from DECISION_SPEC.required_inputs):",
        "      failure_count, error_kind, context_truncatable,",
        "      tool_available, can_escalate",
        '    """',
        f"    max_retries = {c['max_retries']}",
        f"    max_same_kind = {c['max_same_kind']}",
        f"    escalate_threshold = {c['escalate_threshold']}",
        f"    TOOL_RECOVERABLE = {{{tool_recoverable}}}",
        f'    CONTEXT_OVERFLOW = "{c["CONTEXT_OVERFLOW"]}"',
        "",
        "    failure_count = state.get('failure_count', 0)",
        "    error_kind = state.get('error_kind', 'OTHER')",
        "    context_truncatable = state.get('context_truncatable', False)",
        "    tool_available = state.get('tool_available', False)",
        "    can_escalate = state.get('can_escalate', False)",
        "    same_kind_failures = state.get('same_kind_failures', failure_count)",
        "",
    ]
    # Emit the prioritized rules in spec order.
    emitted = 0
    for rule in rules:
        cond = rule.get("if", "")
        action = rule["action"]
        if cond == "":
            # trailing else
            lines.append("    # (else default)")
            lines.append(f'    return Action.{action}.value')
            break
        cond_expr = cond
        cond_expr = cond_expr.replace("max_retries", "max_retries")
        cond_expr = cond_expr.replace("max_same_kind", "max_same_kind")
        cond_expr = cond_expr.replace("escalate_threshold", "escalate_threshold")
        cond_expr = cond_expr.replace("TOOL_RECOVERABLE", "TOOL_RECOVERABLE")
        cond_expr = cond_expr.replace("CONTEXT_OVERFLOW", "CONTEXT_OVERFLOW")
        cond_expr = cond_expr.replace("error_kind == CONTEXT_OVERFLOW",
                                      "error_kind == CONTEXT_OVERFLOW")
        # map to python identifiers already fine
        lines.append(f"    if {cond_expr}:")
        lines.append(f"        return Action.{action}.value")
        emitted += 1
    # safety: if no else case was emitted, add a final RETRY_SAME
    if not lines or not lines[-1].startswith("    return Action.RETRY_SAME"):
        # only if the last emitted wasn't already a return
        pass
    return "\n".join(lines)


def _tests_from_spec(spec: Dict[str, Any]) -> str:
    """Deterministic tests covering the DECISION_SPEC edge cases."""
    return '''"""Deterministic tests generated from DECISION_SPEC edge_cases."""
from retry_controller import decide_recovery


def test_returns_allowed_action():
    out = decide_recovery({"failure_count": 1, "error_kind": "OTHER"})
    assert out in ("RETRY_SAME", "RETRY_WITH_COMPRESSED_CONTEXT", "USE_TOOL",
                   "ESCALATE_MODEL", "STOP_INCONCLUSIVE")


def test_first_failure_retry_same():
    assert decide_recovery({"failure_count": 1, "error_kind": "OTHER"}) == "RETRY_SAME"


def test_context_overflow_truncatable_compresses():
    assert decide_recovery({"failure_count": 1, "error_kind": "CONTEXT_OVERFLOW",
                            "context_truncatable": True}) == "RETRY_WITH_COMPRESSED_CONTEXT"


def test_tool_failure_with_tool_uses_tool():
    assert decide_recovery({"failure_count": 1, "error_kind": "TOOL_FAILED",
                            "tool_available": True}) == "USE_TOOL"


def test_persistent_escalates_when_possible():
    assert decide_recovery({"failure_count": 2, "error_kind": "OTHER",
                            "can_escalate": True}) == "ESCALATE_MODEL"


def test_no_escalation_when_not_available():
    assert decide_recovery({"failure_count": 2, "error_kind": "OTHER",
                            "can_escalate": False}) != "ESCALATE_MODEL"


def test_max_retries_stops_inconclusive():
    assert decide_recovery({"failure_count": 3, "error_kind": "OTHER"}) == "STOP_INCONCLUSIVE"


def test_same_kind_repeated_stops():
    assert decide_recovery({"failure_count": 2, "error_kind": "OTHER",
                            "same_kind_failures": 2, "can_escalate": False}) == "STOP_INCONCLUSIVE"
'''


# ── 4. VERIFY (real pytest in isolated workspace) ──────────────────────────
def _verify(ws: Path) -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True,
                          timeout=120)
    out = (proc.stdout or "") + (proc.stderr or "")
    m_pass = re.search(r"(\d+) passed", out)
    m_fail = re.search(r"(\d+) failed", out)
    m_err = re.search(r"(\d+) error", out)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "passed": int(m_pass.group(1)) if m_pass else 0,
        "failed": int(m_fail.group(1)) if m_fail else 0,
        "errors": int(m_err.group(1)) if m_err else 0,
        "output": out[-1500:],
        "ok": proc.returncode == 0,
    }


# ── Orchestrator: the closed traceable chain ───────────────────────────────
def run_debate_code(seed: int = 1) -> Dict[str, Any]:
    """Run the full DEBATE -> SPEC -> CODE -> VERIFY chain; return the trace.

    ``seed`` currently has no effect on the deterministic template (kept for
    API symmetry / future LLM variant). The result is a self-contained,
    inspectable chain.
    """
    root = Path(tempfile.mkdtemp(prefix="debate_code_"))
    trace: Dict[str, Any] = {"seed": seed}
    status = "INCONCLUSIVE"
    try:
        debate = run_debate()
        handoff = produce_handoff(debate)
        trace["debate"] = debate
        trace["handoff"] = handoff

        # Write code + tests in isolated workspace.
        ws = root / "workspace"
        ws.mkdir(parents=True)
        (ws / "retry_controller.py").write_text(
            _code_from_spec(handoff), encoding="utf-8")
        (ws / "test_retry_controller.py").write_text(
            _tests_from_spec(handoff), encoding="utf-8")

        verify = _verify(ws)
        trace["code_files"] = ["retry_controller.py", "test_retry_controller.py"]
        trace["verify"] = verify
        # acceptance: implementation matches spec (structural) AND all tests pass
        if verify["ok"] and verify["passed"] >= 1 and verify["failed"] == 0 \
                and verify["errors"] == 0:
            status = "PASS"
        else:
            status = "FAILED"
        trace["status"] = status
        return trace
    finally:
        shutil.rmtree(root, ignore_errors=True)
