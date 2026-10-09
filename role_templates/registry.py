"""RoleTemplateRegistry — simple registry of built-in (and future) templates.

Responsibilities:
    list_templates()                    -> metadata summaries
    get_template(id, version=None)      -> RoleTemplate or None
    validate_template(template)         -> error string or ""
    register_builtin_template()         -> (re)register all built-ins

This is deliberately NOT an extension marketplace infra — it only holds
versioned, hashable protocol definitions.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .core import RoleTemplate
from .builtins import builtin_templates


def _version_key(version: str):
    """Deterministic sort key for versions (semver-ish, tolerant).

    '1.10.0' > '1.9.9'; non-numeric segments fall back to string compare.
    """
    key = []
    for part in re.split(r"[._-]+", str(version)):
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return key


class RoleTemplateRegistry:
    """Holds RoleTemplate instances keyed by template_id, with versions.

    Registration is VALIDATED and IMMUTABLE: the same (template_id, version)
    can only be registered once with the same content hash. Re-registering an
    identical protocol is idempotent; re-registering a DIFFERENT content under
    an existing id/version is REJECTED (a registered scientific identity is
    never silently replaced). ``_latest`` is the deterministically-highest
    version, not merely the last one registered.
    """

    def __init__(self) -> None:
        self._latest: Dict[str, RoleTemplate] = {}
        self._versions: Dict[str, Dict[str, RoleTemplate]] = {}

    # ── registration ──────────────────────────────────────────────────────
    def register(self, template: RoleTemplate) -> bool:
        """Validate + register. Returns True on a NEW registration, False on
        an idempotent re-register of an identical protocol. Raises ValueError
        on invalid templates or immutable-identity collisions."""
        tid = template.template_id
        err = self.validate_template(template)
        if err:
            raise ValueError(f"invalid role template: {err}")
        existing = self._versions.get(tid, {}).get(template.version)
        if existing is not None:
            if existing.content_hash() != template.content_hash():
                raise ValueError(
                    f"template '{tid}' version '{template.version}' is already "
                    f"registered with a DIFFERENT content hash — refusing to "
                    f"silently replace a registered protocol "
                    f"({existing.content_hash()[:8]} != {template.content_hash()[:8]})")
            return False  # identical id+version+hash → idempotent no-op
        self._versions.setdefault(tid, {})[template.version] = template
        cur = self._latest.get(tid)
        if cur is None or _version_key(template.version) > _version_key(cur.version):
            self._latest[tid] = template
        return True

    def register_builtin(self) -> int:
        """(Re)register all built-in templates. Returns the count NEWLY
        registered (idempotent on re-register of identical built-ins)."""
        count = 0
        for tpl in builtin_templates():
            if self.register(tpl):
                count += 1
        return count

    # ── lookup ────────────────────────────────────────────────────────────
    def get_template(self, template_id: str,
                     version: Optional[str] = None) -> Optional[RoleTemplate]:
        if version:
            return self._versions.get(template_id, {}).get(version)
        return self._latest.get(template_id)

    def list_templates(self) -> List[dict]:
        """Safe metadata summaries for API/UI (never full instruction bodies)."""
        out = []
        for tid in sorted(self._latest):
            tpl = self._latest[tid]
            out.append(tpl.summary())
        return out

    def versions(self, template_id: str) -> List[str]:
        return sorted(self._versions.get(template_id, {}))

    # ── validation ────────────────────────────────────────────────────────
    @staticmethod
    def validate_template(template: RoleTemplate) -> str:
        """Return an error message, or '' if the template is valid."""
        if not template.template_id:
            return "template_id is required"
        if not template.version:
            return "version is required"
        if not template.roles:
            return "template must declare at least one role"
        seen = set()
        for r in template.roles:
            if not r.role_id:
                return "each role requires a role_id"
            if r.role_id in seen:
                return f"duplicate role_id '{r.role_id}'"
            seen.add(r.role_id)
            if not r.instructions_template and not r.objectives:
                return f"role '{r.role_id}' needs instructions or objectives"
        return ""


# Module-level default registry, preloaded with built-ins.
_default_registry = RoleTemplateRegistry()
_default_registry.register_builtin()


def get_registry() -> RoleTemplateRegistry:
    """Return the module-level default registry."""
    return _default_registry
