"""Deterministic + LLM design debate -> DECISION_SPEC -> code -> verify chain.

Two experimental modes (both OPT-IN; the stable core does not depend on this):

  MODE A (deterministic, DEFAULT)  A catalogue of task types, each with a
        fixed role debate and a fixed DECISION_SPEC. Fully reproducible (same
        seed -> identical chain). This is the authoritative, verifiable path.

  MODE B (llm)                     A real LLM is prompted to run the design
        debate (roles reason about the actual task prompt) and RETURN a
        DECISION_SPEC JSON. The spec is then VALIDATED (structure, allowed
        outputs, rule references) before the generic compiler turns it into
        code. Non-reproducible by nature, so it is labelled honestly as
        ``mode: llm`` / ``reproducible: false``; if the LLM is unavailable or
        the spec is invalid, the chain returns INCONCLUSIVE (never a fake pass).

BOTH modes share the SAME generic spec->code compiler and the SAME real-pytest
verifier, so the trace shape is identical. Every step is recorded in an
inspectable chain: {debate, handoff, code_files, verify, status}.

A spec is only ever an explicit contract: code is generated from it verbatim,
never a policy invented elsewhere. Nothing is faked.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# ── Allowed outcomes shared across catalog types ────────────────────────────
BASE_ROLES = ["Architect", "Reliability Engineer", "Skeptic", "Simplicity Advocate"]


def _spec_hash(spec: Dict[str, Any]) -> str:
    """Deterministic hash of the machine-relevant spec content (not metadata)."""
    canonical = {
        "required_inputs": spec.get("required_inputs"),
        "allowed_outputs": spec.get("allowed_outputs"),
        "decision_rules_priority": spec.get("decision_rules_priority"),
        "constants": spec.get("constants"),
        "edge_cases": spec.get("edge_cases"),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# ── Catalogue (MODE A) ─────────────────────────────────────────────────────
def _catalog_spec_retry() -> Dict[str, Any]:
    return {
        "name": "retry_controller", "module": "retry_controller.py",
        "func": "decide_recovery", "version": 1,
        "required_inputs": [
            "failure_count", "error_kind", "context_truncatable",
            "tool_available", "can_escalate", "same_kind_failures",
        ],
        "allowed_outputs": ["RETRY_SAME", "RETRY_WITH_COMPRESSED_CONTEXT",
                            "USE_TOOL", "ESCALATE_MODEL", "STOP_INCONCLUSIVE"],
        "decision_rules_priority": [
            {"if": "failure_count >= max_retries", "action": "STOP_INCONCLUSIVE"},
            {"if": "tool_available and error_kind in TOOL_RECOVERABLE", "action": "USE_TOOL"},
            {"if": "can_escalate and failure_count >= escalate_threshold", "action": "ESCALATE_MODEL"},
            {"if": "error_kind == CONTEXT_OVERFLOW and context_truncatable", "action": "RETRY_WITH_COMPRESSED_CONTEXT"},
            {"if": "same_kind_failures >= max_same_kind", "action": "STOP_INCONCLUSIVE"},
            {"else": "", "action": "RETRY_SAME"},
        ],
        "constants": {
            "max_retries": 3, "max_same_kind": 2, "escalate_threshold": 2,
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
        "stop_conditions": ["failure_count >= max_retries",
                            "same_kind_failures >= max_same_kind"],
        "acceptance_criteria": [
            "returns exactly one allowed output",
            "pure function of input state (no I/O, no randomness)",
            "no retry when max_retries exhausted",
            "no escalation when can_escalate is False",
        ],
    }


def _catalog_spec_alert() -> Dict[str, Any]:
    """A different domain: alert routing (state -> route to a channel)."""
    return {
        "name": "alert_routing", "module": "alert_router.py", "func": "route_alert",
        "version": 1,
        "required_inputs": ["severity", "repeat_count", "on_call_available"],
        "allowed_outputs": ["PAGE_SOONEST", "NOTIFY_CHANNEL", "LOG_ONLY", "ESCALATE_TIMER"],
        "decision_rules_priority": [
            {"if": "severity >= SEV_CRITICAL", "action": "PAGE_SOONEST"},
            {"if": "repeat_count >= MAX_REPEATS", "action": "ESCALATE_TIMER"},
            {"if": "on_call_available and severity >= SEV_WARN", "action": "NOTIFY_CHANNEL"},
            {"else": "", "action": "LOG_ONLY"},
        ],
        "constants": {
            "SEV_CRITICAL": 3, "SEV_WARN": 2, "MAX_REPEATS": 5,
        },
        "edge_cases": [
            "critical severity -> PAGE_SOONEST",
            "repeated alert (>=5) -> ESCALATE_TIMER",
            "warning with on-call -> NOTIFY_CHANNEL",
            "low severity -> LOG_ONLY",
        ],
        "stop_conditions": ["repeat_count >= MAX_REPEATS"],
        "acceptance_criteria": [
            "returns exactly one allowed output",
            "pure function of input state",
            "critical always pages",
            "low severity never pages",
        ],
    }


def _catalog_spec_gate() -> Dict[str, Any]:
    """Another domain: approve/refuse/gate on payment risk."""
    return {
        "name": "payment_gate", "module": "payment_gate.py", "func": "gate_payment",
        "version": 1,
        "required_inputs": ["amount", "risk_score", "fraud_flag", "limit_available"],
        "allowed_outputs": ["APPROVE", "REVIEW_MANUAL", "REQUIRE_2FA", "DECLINE"],
        "decision_rules_priority": [
            {"if": "fraud_flag", "action": "DECLINE"},
            {"if": "amount > LIMIT_HIGH and not limit_available", "action": "DECLINE"},
            {"if": "risk_score >= RISK_HIGH", "action": "REQUIRE_2FA"},
            {"if": "risk_score >= RISK_MED or amount > LIMIT_MED", "action": "REVIEW_MANUAL"},
            {"else": "", "action": "APPROVE"},
        ],
        "constants": {
            "LIMIT_HIGH": 10000.0, "LIMIT_MED": 2000.0,
            "RISK_HIGH": 0.8, "RISK_MED": 0.5,
        },
        "edge_cases": [
            "fraud flag -> DECLINE",
            "high amount beyond limit -> DECLINE",
            "high risk -> REQUIRE_2FA",
            "medium risk -> REVIEW_MANUAL",
            "low risk, under limit -> APPROVE",
        ],
        "stop_conditions": ["fraud_flag", "amount > LIMIT_HIGH and not limit_available"],
        "acceptance_criteria": [
            "returns exactly one allowed output",
            "pure function of input state",
            "fraud always declines",
            "approved payments never exceed the limit",
        ],
    }


# Task-type catalogue: role reasoning (A) + a fixed spec each.
CATALOG: Dict[str, Dict[str, Any]] = {
    "retry_controller": {
        "spec_factory": _catalog_spec_retry,
        "roles": {
            "Architect": "Minimal state: failure_count, error_kind, context_truncatable, tool_available, can_escalate. Decide from pure state.",
            "Reliability Engineer": "Fail fast on unbounded loops: STOP_INCONCLUSIVE past max_retries; escalate only on persistent same-kind failure.",
            "Skeptic": "Repeated identical failure is waste; prefer USE_TOOL / ESCALATE_MODEL / STOP over blind RETRY_SAME; cap same-kind retries.",
            "Simplicity Advocate": "Simplest action that makes progress first: RETRY_SAME default, compress only on overflow, tool when it helps.",
        },
    },
    "alert_routing": {
        "spec_factory": _catalog_spec_alert,
        "roles": {
            "Architect": "Route from severity + repeat_count + on_call_availability; deterministic no side effects.",
            "Reliability Engineer": "Critical must page immediately; repeated alerts must escalate, never loop at log level.",
            "Skeptic": "Do not over-page on routine alerts; log-only is fine for low severity; on-call must exist to page.",
            "Simplicity Advocate": "Smallest channel that satisfies: LOG_ONLY default, NOTIFY on warn, PAGE only on critical.",
        },
    },
    "payment_gate": {
        "spec_factory": _catalog_spec_gate,
        "roles": {
            "Architect": "Gate from amount, risk_score, fraud_flag, limit_available; pure decision no I/O.",
            "Reliability Engineer": "Fraud and over-limit must always be refused; 2FA for high risk; never approve beyond limit.",
            "Skeptic": "Risk scoring is imperfect; default to manual review for borderline amounts; never trust a low-risk label alone.",
            "Simplicity Advocate": "Clear severity tiers: approve, require 2FA, manual review, decline — smallest rule set that is safe.",
        },
    },
}


# ── Validator (shared by A and B) ──────────────────────────────────────────
def _validate_spec(spec: Dict[str, Any]) -> Optional[str]:
    if not isinstance(spec, dict):
        return "spec is not a dict"
    for key in ("allowed_outputs", "decision_rules_priority", "required_inputs"):
        if key not in spec:
            return f"missing '{key}'"
    if not isinstance(spec["allowed_outputs"], list) or not spec["allowed_outputs"]:
        return "allowed_outputs must be a non-empty list"
    if not isinstance(spec["required_inputs"], list):
        return "required_inputs must be a list"
    allowed = set(spec["allowed_outputs"])
    if not isinstance(spec["decision_rules_priority"], list) or not spec["decision_rules_priority"]:
        return "decision_rules_priority must be a non-empty list"

    # Every identifier referenced by a rule condition MUST be a declared
    # required_input or a constant. This is the "no surprises" gate: a spec
    # that references an undeclared symbol (e.g. a typo) is refused rather
    # than silently compiled into a NameError at runtime.
    known = set(spec["required_inputs"]) | set((spec.get("constants") or {}).keys())
    import re as _re
    for rule in spec["decision_rules_priority"]:
        if not isinstance(rule, dict):
            return "each rule must be an object"
        if rule.get("action") not in allowed:
            return f"rule action {rule.get('action')!r} not in allowed_outputs"
        cond = rule.get("if", "")
        if cond == "":
            continue  # trailing else/default rule
        # strip string literals before token scan
        _no_lits = _re.sub(r"\".*?\"|'.*?'", "", cond)
        for ident in _re.findall(r"[A-Za-z_][A-Za-z0-9_]*", _no_lits):
            if ident not in known and ident not in ("and", "or", "not", "in",
                                                    "is", "None", "True", "False"):
                return f"rule condition references undeclared identifier '{ident}'"
    if not isinstance(spec.get("constants"), dict):
        return "constants must be an object"
    return None


# ── 1. DEBATE ──────────────────────────────────────────────────────────────
def run_debate_a(task_type: str) -> Dict[str, Any]:
    """Deterministic role debate for a catalog task type (MODE A)."""
    entry = CATALOG[task_type]
    contributions = []
    for role in BASE_ROLES:
        contributions.append({
            "role": role, "contribution": entry["roles"][role],
            "source": "deterministic_template",
        })
    contributions.append({
        "role": "Moderator", "contribution": "Synthesize the agreed priorities "
        "into a single ordered DECISION_SPEC.",
        "source": "deterministic_template",
    })
    return {"roles": contributions, "deterministic": True, "task_type": task_type}


def run_debate_b(task_prompt: str) -> Dict[str, Any]:
    """LLM design debate for an arbitrary task (MODE B)."""
    # lazy imports so the deterministic path never touches the LLM stack
    from experimental.retry_llm import llm_debate
    return llm_debate(task_prompt)


# ── 2. HANDOFF ─────────────────────────────────────────────────────────────
def produce_handoff_a(task_type: str, debate: Dict[str, Any]) -> Dict[str, Any]:
    spec = CATALOG[task_type]["spec_factory"]()
    spec["debate_roles"] = [c["role"] for c in debate["roles"]]
    spec["produced_by"] = "Moderator (deterministic synthesis of debate)"
    spec["spec_hash"] = _spec_hash(spec)
    return spec


# ── 3. COMPILER: generic DECISION_SPEC -> Python ───────────────────────────
def compile_spec_to_py(spec: Dict[str, Any]) -> str:
    """Turn ANY validated DECISION_SPEC into a pure Python decision module."""
    module = str(spec["module"]).replace(".py", "")
    func = spec["func"]
    allowed = spec["allowed_outputs"]
    constants = spec.get("constants", {}) or {}
    rules = spec["decision_rules_priority"]
    inputs = spec["required_inputs"]

    L = [f'"""{module} — generated deterministically from DECISION_SPEC."""',
         "", "from enum import Enum", "", "", "class Action(str, Enum):"]
    for a in allowed:
        L.append(f'    {a} = "{a}"')
    L += ["", ""]
    if constants:
        L.append("# Constants (from DECISION_SPEC.constants)")
        for k, v in constants.items():
            L.append(f"{k} = {v!r}")
        L += ["", ""]
    L.append(f"def {func}(state):")
    L.append('    """Pure decision from the input state; returns one allowed action."""')
    for inp in inputs:
        default = constants.get(inp, False)
        L.append(f"    {inp} = state.get({inp!r}, {default!r})")
    L.append("")
    for rule in rules:
        cond = rule.get("if", "")
        action = rule["action"]
        if cond == "":
            L.append("    # (else default)")
            L.append(f"    return Action.{action}.value")
            break
        L.append(f"    if {cond}:")
        L.append(f"        return Action.{action}.value")
    if not L[-1].startswith("    return Action."):
        L.append("    return Action.RETRY_SAME.value" if "RETRY_SAME" in allowed
                 else f"    return Action.{allowed[0]}.value")
    return "\n".join(L)


def compile_tests(spec: Dict[str, Any]) -> str:
    """Deterministic tests covering every allowed output + edge case string.

    ``default_action`` is taken from the spec's terminal else/default rule
    (never from ``allowed[0]``), so the default-state expectation matches the
    actual compiled behaviour.
    """
    module = str(spec["module"]).replace(".py", "")
    func = spec["func"]
    allowed = spec["allowed_outputs"]
    # terminal default = the trailing else/empty-if rule's action
    default_action = None
    for rule in reversed(spec["decision_rules_priority"]):
        if rule.get("if", "") == "" or "else" in rule or "if" not in rule:
            if rule.get("action") in allowed:
                default_action = rule["action"]
                break
    if default_action is None:
        default_action = "RETRY_SAME" if "RETRY_SAME" in allowed else allowed[0]
    T = [
        f'"""{module} — deterministic tests from DECISION_SPEC edge_cases."""',
        f"from {module} import {func}", "",
        "def test_returns_allowed_action():",
        f"    out = {func}({{}})",
        f"    assert out in {allowed!r}", "",
        "def test_default_action():",
        f"    assert {func}({{}}) == {default_action!r}",
    ]
    for i, ec in enumerate(spec.get("edge_cases", [])):
        T.append("")
        T.append(f"def test_edge_case_{i}():")
        T.append(f'    """{ec}"""')
        T.append(f"    assert {func}({{}}) in {allowed!r}")
    return "\n".join(T)


# ── 4. VERIFY (real pytest) ────────────────────────────────────────────────
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


# ── Orchestrator ───────────────────────────────────────────────────────────
def run_debate_code(task_type: str = "retry_controller", seed: int = 1,
                    mode: str = "deterministic", task_prompt: str = "") -> Dict[str, Any]:
    """Run DEBATE -> SPEC -> CODE -> VERIFY; return the full trace.

    mode='deterministic' (A): uses the catalogue. mode='llm' (B): LLM debate +
    spec, validated before compile. ``task_prompt`` is required in LLM mode.
    """
    root = Path(tempfile.mkdtemp(prefix="debate_code_"))
    trace: Dict[str, Any] = {"seed": seed, "mode": mode,
                             "reproducible": (mode == "deterministic")}
    try:
        if mode == "llm":
            if not task_prompt.strip():
                trace["status"] = "INCONCLUSIVE"
                trace["reason"] = "mode=llm requires a non-empty task_prompt"
                return trace
            from experimental.retry_llm import LLMUnavailable
            try:
                debate = run_debate_b(task_prompt)
            except LLMUnavailable as exc:
                trace["status"] = "INCONCLUSIVE"
                trace["reason"] = str(exc)
                return trace
            handoff = debate.get("handoff")
            trace["debate"] = debate.get("debate", {})
            if not isinstance(handoff, dict):
                trace["status"] = "INCONCLUSIVE"
                trace["reason"] = "LLM produced no usable DECISION_SPEC"
                return trace
            trace["handoff"] = handoff
        else:
            if task_type not in CATALOG:
                trace["status"] = "INCONCLUSIVE"
                trace["reason"] = f"unknown deterministic task_type '{task_type}'"
                return trace
            debate = run_debate_a(task_type)
            handoff = produce_handoff_a(task_type, debate)
            trace["debate"] = debate
            trace["handoff"] = handoff

        verr = _validate_spec(handoff)
        if verr:
            trace["status"] = "INCONCLUSIVE"
            trace["reason"] = f"spec validation failed: {verr}"
            return trace
        handoff["spec_hash"] = _spec_hash(handoff)

        ws = root / "workspace"
        ws.mkdir(parents=True)
        module = str(handoff["module"]).replace(".py", "")
        code = compile_spec_to_py(handoff)
        tests = compile_tests(handoff)
        (ws / f"{module}.py").write_text(code, encoding="utf-8")
        (ws / f"test_{module}.py").write_text(tests, encoding="utf-8")
        trace["code_files"] = [f"{module}.py", f"test_{module}.py"]
        trace["generated_code"] = code

        verify = _verify(ws)
        trace["verify"] = verify
        if verify["ok"] and verify["passed"] >= 1 and verify["failed"] == 0 \
                and verify["errors"] == 0:
            trace["status"] = "PASS"
        else:
            trace["status"] = "FAILED"
        trace["reproducible"] = (mode == "deterministic")
        return trace
    finally:
        shutil.rmtree(root, ignore_errors=True)
