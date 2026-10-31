"""Factories for generating skills and tools from detected needs."""

from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registries import CapabilityNeed, ResourceStatus, SkillDef, ToolDef, Version

logger = logging.getLogger("life_mean_extensions.factories")

# Ids derived from caller-supplied `need_id` MUST be constrained to a safe
# character set before use as a registry key or filesystem component — an
# unbounded need_id ("../../pwn") escapes the sandbox and turns
# propose_from_need into an arbitrary file write (confirmed during the
# dashboard security audit). Whitelist, never blacklist.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_FALLBACK_ID = "generated-tool"


def _sanitize_id(raw: str, prefix: str) -> str:
    """Return a filesystem/registry-safe id derived from caller input.

    The raw id is only ever a hint; an invalid character set silently falls
    back to a safe canonical id instead of propagating attacker input. This
    also neutralizes the stored-XSS vector where an id containing quotes/spaces
    was echoed into inline handlers on the dashboard.
    """
    s = str(raw or "").strip()
    if not s or not _SAFE_ID_RE.match(s):
        return f"{prefix}-{_FALLBACK_ID}"
    return s


# --------------------------------------------------------------------------
# Skill factory
# --------------------------------------------------------------------------

@dataclass
class SkillSpec:
    need_id: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    test_cases: List[str] = field(default_factory=list)


class SkillFactory:
    """Proposes and generates skills from capability needs."""

    def __init__(self, registry) -> None:  # SkillRegistry
        self.registry = registry

    def propose_from_need(self, need: CapabilityNeed, spec: Optional[SkillSpec] = None) -> SkillDef:
        if spec is None:
            spec = SkillSpec(need_id=need.id, description=f"Auto-generated skill for: {need.evidence[:100]}")
        skill = SkillDef(
            id=_sanitize_id(spec.need_id.replace("need-", "skill-"), "skill"),
            description=spec.description,
            input_schema=spec.input_schema,
            output_schema=spec.output_schema,
            dependencies=list(spec.dependencies),
            tests=list(spec.test_cases),
            instructions=self._generate_instructions(need, spec),
        )
        self.registry.propose(skill)
        return skill

    def _generate_instructions(self, need: CapabilityNeed, spec: SkillSpec) -> str:
        return textwrap.dedent(f"""\
            # Skill: {spec.description}
            Generated from capability need: {need.id}
            Priority: {need.priority}
            Evidence: {need.evidence[:200]}

            ## Purpose
            Address the missing capability detected during debate/tool execution.

            ## Inputs
            {spec.input_schema or '(see schema)'}

            ## Outputs
            {spec.output_schema or '(see schema)'}

            ## Dependencies
            {', '.join(spec.dependencies) or 'None'}

            ## Validation
            Run tests: {', '.join(spec.test_cases) or '(none defined)'}
            """)


# --------------------------------------------------------------------------
# Tool factory
# --------------------------------------------------------------------------

@dataclass
class ToolSpec:
    need_id: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    source_template: str = ""  # user-provided or template code
    dependencies: List[str] = field(default_factory=list)
    test_cases: List[str] = field(default_factory=list)


class ToolFactory:
    """Proposes and generates tools from capability needs.

    IMPORTANT: Generated code is NEVER executed in the main environment.
    It stays in a sandbox until human approval + activation.
    """

    def __init__(self, registry, sandbox_root: Optional[Path] = None) -> None:
        self.registry = registry
        self.sandbox_root = sandbox_root or Path(__file__).parent.parent / "sandbox" / "tools"
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def propose_from_need(self, need: CapabilityNeed, spec: Optional[ToolSpec] = None) -> ToolDef:
        if spec is None:
            spec = ToolSpec(need_id=need.id, description=f"Auto-generated tool for: {need.evidence[:100]}")
        tool_id = _sanitize_id(spec.need_id.replace("need-", "tool-"), "tool")
        sandbox_path = self.sandbox_root / tool_id
        sandbox_path.mkdir(parents=True, exist_ok=True)

        # Write generated code to sandbox (isolated from main env)
        source_code = spec.source_template or self._generate_stub(need, spec)
        (sandbox_path / "tool.py").write_text(source_code, encoding="utf-8")
        import json
        (sandbox_path / "spec.json").write_text(
            json.dumps(
                ToolDef(
                    id=tool_id, description=spec.description,
                    input_schema=spec.input_schema, output_schema=spec.output_schema,
                    source_code=source_code, dependencies=list(spec.dependencies),
                    tests=list(spec.test_cases),
                ).to_dict(),
                indent=2,
            ),
            encoding="utf-8",
        )

        tool = ToolDef(
            id=tool_id,
            description=spec.description,
            input_schema=spec.input_schema,
            output_schema=spec.output_schema,
            source_code=source_code,
            dependencies=list(spec.dependencies),
            tests=list(spec.test_cases),
            sandbox_path=sandbox_path,
        )
        self.registry.propose(tool)
        return tool

    def _generate_stub(self, need: CapabilityNeed, spec: ToolSpec) -> str:
        return textwrap.dedent(f"""\
            # Auto-generated tool from capability need: {need.id}
            # Description: {spec.description}
            # WARNING: This code has NOT been approved for production use.

            def execute(**kwargs):
                \"\"\"Stub implementation — replace with real logic.\"\"\"
                return {{
                    "valid": False,
                    "error": "Tool not yet implemented (needs approval)",
                    "raw_input": kwargs,
                }}
            """)

    def get_sandbox_path(self, tool_id: str) -> Optional[Path]:
        t = self.registry.get(tool_id)
        return t.sandbox_path if t else None
