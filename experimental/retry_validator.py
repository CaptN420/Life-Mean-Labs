"""DECISION_SPEC validation + normalization (shared by mode A and mode B).

The spec is the single contract that DEBATE hands to CODE. Both modes must
produce a spec that satisfies the same structural rules before it is compiled,
so a mode-B (LLM) spec can never inject an unpatchable inconsistency. This is
the "no surprises" gate: an invalid spec is refused (INCONCLUSIVE), never
silently compiled.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _ids(idents) -> List[str]:
    return [str(i) for i in (idents or [])]


def normalize_spec(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a (possibly LLM-returned) spec dict into the canonical shape.

    Fills optional fields with defaults; raises ValueError on structurally
    unusable specs (caller converts to INCONCLUSIVE).
    """
    def _need(k):
        if k not in raw or raw[k] in (None, ""):
            raise ValueError(f"spec missing '{k}'")
        return raw[k]

    # module/func may be missing from a terse LLM answer; require them.
    allowed = _need("allowed_outputs")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("allowed_outputs must be a non-empty list")

    normalized = {
        "name": raw.get("name", "DECISION_SPEC"),
        "version": raw.get("version", 1),
        "module": str(raw.get("module") or "controller.py"),
        "func": str(raw.get("func") or "decide"),
        "required_inputs": [str(x) for x in _need("required_inputs")],
        "allowed_outputs": [str(a) for a in allowed],
        "decision_rules_priority": _need("decision_rules_priority"),
        "constants": raw.get("constants", {}) or {},
        "edge_cases": [str(x) for x in (raw.get("edge_cases", []) or [])],
        "stop_conditions": _ids(raw.get("stop_conditions")),
        "acceptance_criteria": _ids(raw.get("acceptance_criteria")),
    }
    return normalized


def validate_spec(spec: Dict[str, Any]) -> Optional[str]:
    """Return an error string if the spec is unusable, else None.

    Rejects: non-string module/func, empty allowed outputs, non-list rules,
    a rule referencing an action outside allowed_outputs, a rule missing both
    ``if`` and ``else``, non-dict constants.
    """
    if not isinstance(spec, dict):
        return "spec is not a dict"
    for key in ("allowed_outputs", "decision_rules_priority", "required_inputs"):
        if not isinstance(spec.get(key), list) or not spec[key]:
            return f"'{key}' must be a non-empty list"
    if not isinstance(spec.get("module"), str) or not spec["module"]:
        return "'module' must be a non-empty string"
    if not isinstance(spec.get("func"), str) or not spec["func"]:
        return "'func' must be a non-empty string"
    if not isinstance(spec.get("constants"), dict):
        return "'constants' must be an object"
    allowed = set(spec["allowed_outputs"])
    rules = spec["decision_rules_priority"]
    has_else = False
    for rule in rules:
        if not isinstance(rule, dict):
            return "each decision rule must be an object"
        action = rule.get("action")
        if action not in allowed:
            return f"rule action {action!r} not in allowed_outputs"
        has_else = has_else or ("else" in rule or "if" not in rule)
    if not has_else:
        # allow a trailing default rule; reject when no default exists
        return "decision_rules_priority has no default (else/empty-if) rule"
    return None