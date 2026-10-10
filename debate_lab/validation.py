"""Debate template contract validation.

A RoleTemplate is Debate-compatible when it describes a moderator + at least two
participants (spec §5):

- exactly one moderator role, with role_id convention ``"moderator"``
- at least 2 participant roles
- every role has a unique role_id
- model mapping is NEVER embedded in the template (run-level only)

Validation runs BEFORE any engine construction: an incompatible template raises
a controlled ``TemplateInvalidForDebate`` — never a silent fallback to the
philosophical agents (spec §5, §31).
"""

from __future__ import annotations

from typing import Any, Dict, List

# Controlled error codes (spec §40-style, machine-readable).
TEMPLATE_INVALID_FOR_DEBATE = "DEBATE_TEMPLATE_INCOMPATIBLE"
DEBATE_TEMPLATE_MISSING_MODERATOR = "DEBATE_TEMPLATE_MISSING_MODERATOR"
DEBATE_TEMPLATE_TOO_FEW_PARTICIPANTS = "DEBATE_TEMPLATE_TOO_FEW_PARTICIPANTS"
DEBATE_TEMPLATE_DUPLICATE_ROLE = "DEBATE_TEMPLATE_DUPLICATE_ROLE"


class TemplateInvalidForDebate(ValueError):
    """A template cannot drive a DebateEngine session (controlled error)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "error": str(self)}


def validate_debate_template(template: Any) -> None:
    """Raise :class:`TemplateInvalidForDebate` when the template is not
    Debate-compatible. Returns None on success."""
    if template is None:
        raise TemplateInvalidForDebate(
            TEMPLATE_INVALID_FOR_DEBATE,
            "DEBATE_TEMPLATE_INCOMPATIBLE: unknown role template.",
        )

    roles = list(getattr(template, "roles", []) or [])
    role_ids = [getattr(r, "role_id", "") for r in roles]

    moderators = [rid for rid in role_ids if rid == "moderator"]
    if len(moderators) != 1:
        raise TemplateInvalidForDebate(
            DEBATE_TEMPLATE_MISSING_MODERATOR,
            "DEBATE_TEMPLATE_MISSING_MODERATOR: a Debate template must declare "
            "exactly one role with role_id 'moderator'.",
        )

    participants = [rid for rid in role_ids if rid != "moderator"]
    if len(participants) < 2:
        raise TemplateInvalidForDebate(
            DEBATE_TEMPLATE_TOO_FEW_PARTICIPANTS,
            "DEBATE_TEMPLATE_TOO_FEW_PARTICIPANTS: a Debate template requires "
            "at least 2 participant roles.",
        )

    if len(set(role_ids)) != len(role_ids):
        raise TemplateInvalidForDebate(
            DEBATE_TEMPLATE_DUPLICATE_ROLE,
            "DEBATE_TEMPLATE_DUPLICATE_ROLE: every role must have a unique role_id.",
        )

    for r in roles:
        if not getattr(r, "role_id", ""):
            raise TemplateInvalidForDebate(
                TEMPLATE_INVALID_FOR_DEBATE,
                "DEBATE_TEMPLATE_INCOMPATIBLE: a role has an empty role_id.",
            )


def template_summary(template: Any) -> Dict[str, Any]:
    """Compact read-only summary of a Debate template for the UI (spec §25)."""
    return {
        "template_id": template.template_id,
        "name": template.name,
        "version": template.version,
        "hash": template.content_hash(),
        "executor_type": template.executor_type,
        "description": template.description,
        "response_contract": list(getattr(template, "response_contract", []) or []),
        "has_shared_context": bool((getattr(template, "shared_context", "") or "").strip()),
        "roles": [
            {
                "role_id": r.role_id,
                "name": r.name,
                "default_persona": r.default_persona or "",
                "model_slot": r.model_slot or "",
                "objectives": list(r.objectives or []),
                "constraints": list(r.constraints or []),
                "expected_output": r.expected_output or "",
            }
            for r in template.roles
        ],
    }


def debate_template_ids() -> List[str]:
    """The registered template ids whose executor_type is Debate-compatible.

    Both ``philosophical_debate`` (historical) and ``debate`` (generic) dispatch
    to the SAME DebateEngine integration (spec §4).
    """
    from role_templates.registry import get_registry

    out = []
    for tpl in get_registry()._latest.values():
        et = tpl.executor_type or ""
        if et in ("debate", "philosophical_debate"):
            out.append(tpl.template_id)
    return sorted(out)
