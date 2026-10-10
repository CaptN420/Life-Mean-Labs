"""Template → executor dispatch.

A Role Template declares an ``executor_type``; this module is the SINGLE place
that maps that declaration onto the compatible EXISTING executor (it does not
create or replace any engine/orchestrator). Selection must dispatch by executor
type instead of sending every template into CodeLabEngine — CodeLab Engine stays
100% coding-specific and only ever receives ``executor_type == "code_lab"``
templates. A template whose executor is not connected is refused here, at the
dispatch layer, with a message naming the intended executor — never by being
misrouted into a mismatched engine.

Consumed by the dashboard when a template is selected, so the wrong-executor
case fails BEFORE any CodeLabConfig/CodeLabEngine is constructed.
"""

from __future__ import annotations

from typing import Any, Dict

# Executor capability catalog — THE single authoritative source of what CAN run
# right now (spec §30: one truth for settings / dispatch / dashboard; no
# contradictory `_EXECUTABLE_EXECUTORS` / `_DEBATE_CONNECTED` flags elsewhere).
# `connected` = a live executor is actually wired for this executor_type.
EXECUTOR_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "code_lab": {
        "executor_kind": "code_lab",
        "engine": "CodeLabEngine",
        "connected": True,
        "configurable": True,
        "description": "Code Lab: coding tasks via the deterministic + multi-agent code engine.",
    },
    "debate": {
        "executor_kind": "debate",
        "engine": "DebateEngine (via DebateSessionFactory)",
        "connected": True,
        "configurable": True,
        "description": "Debate Lab: template-driven multi-agent debates via the stable DebateEngine.",
    },
    "philosophical_debate": {
        "executor_kind": "philosophical_debate",
        # Compatibility alias — same DebateEngine integration as `debate`
        # (spec §4). historical template ids/versions/hashes are untouched.
        "engine": "DebateEngine (via DebateSessionFactory)",
        "connected": True,
        "configurable": True,
        "description": "Philosophical debate: the historical philosophical-debate template via the Debate Lab integration.",
    },
    "general_reasoning": {
        "executor_kind": "general_reasoning",
        "engine": None,
        "connected": False,
        "configurable": False,
        "description": "General reasoning: no executor wired yet.",
    },
}


def _executor_connected(executor_type: str) -> bool:
    """Single source of truth for executor availability (spec §30).

    Settings, dispatch and the dashboard ALL read this one function — there is
    no separate connection flag that can drift out of sync.
    """
    cap = EXECUTOR_CAPABILITIES.get(executor_type or "")
    return bool(cap and cap.get("connected"))


def dispatch_template(template_id: str) -> Dict[str, Any]:
    """Resolve and dispatch a template by its ``executor_type``.

    Returns a descriptor naming the executor that MUST run this template.
    Raises ``ValueError`` (controlled, never a silent fallback) when the
    template is unknown or declares an executor_type with no entry in the
    capability catalog.
    """
    from .registry import get_registry

    tpl = get_registry().get_template(template_id)
    if tpl is None:
        raise ValueError(f"unknown role template '{template_id}' — cannot dispatch.")
    executor_type = tpl.executor_type or ""
    cap = EXECUTOR_CAPABILITIES.get(executor_type)
    if cap is None:
        raise ValueError(
            f"role template '{template_id}' declares executor_type "
            f"'{executor_type or 'unspecified'}', which has no compatible executor. "
            "No fallback execution was attempted.")
    return {
        "template_id": tpl.template_id,
        "executor_type": executor_type,
        "executor_kind": cap["executor_kind"],
        "engine": cap["engine"],
        "connected": cap["connected"],
        "configurable": cap["configurable"],
        "description": cap["description"],
    }


def require_code_lab(template_id: str) -> Dict[str, Any]:
    """Dispatch guard for Code Lab: return the code-lab executor descriptor, or
    raise ValueError naming the executor that SHOULD handle this template.

    Code Lab must never construct an engine for a non-code_lab template.
    """
    d = dispatch_template(template_id)
    if d["executor_type"] != "code_lab":
        target = d["executor_kind"]
        connected = d["connected"]
        raise ValueError(
            f"role template '{template_id}' is of executor type '{d['executor_type']}' "
            f"→ it dispatches to the {target} executor"
            + (" (connected). Code Lab cannot run it." if connected
               else " (not connected). Code Lab cannot run it; no fallback prompts were used."))
    return d


DEBATE_EXECUTOR_TYPES = ("debate", "philosophical_debate")


def require_debate(template_id: str) -> Dict[str, Any]:
    """Dispatch guard for Debate Lab: return the debate executor descriptor, or
    raise ValueError naming the executor that SHOULD handle this template.

    Accepts ONLY Debate-compatible executor types (``debate`` and the historical
    ``philosophical_debate`` alias — both dispatch to the SAME DebateEngine
    integration, spec §4/§31). Debate Lab must never construct an engine for a
    non-debate template; no cross-engine prompt fallback is ever attempted.
    """
    d = dispatch_template(template_id)
    if d["executor_type"] not in DEBATE_EXECUTOR_TYPES:
        target = d["executor_kind"]
        connected = d["connected"]
        raise ValueError(
            f"role template '{template_id}' is of executor type '{d['executor_type']}' "
            f"→ it dispatches to the {target} executor"
            + (" (connected). Debate Lab cannot run it." if connected
               else " (not connected). Debate Lab cannot run it; no fallback prompts were used."))
    return d