"""Life_mean modular self-extension layer.

Adds a capability-detection / skill-and-tool registry / factory / approval
pipeline on top of the EXISTING debate engine WITHOUT replacing it. The
engine continues debating normally; capability requests are processed in a
separate queue and gated by human approval before any activation.

Design principles (hard constraints):
* Never execute unverified generated code in the main environment.
* Models propose, permission system authorizes.
* Isolation: new skills/tools live in a sandbox until approved + activated.
* Preserve existing DebateEngine / AutoPilot / ExperimentRunner behavior.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("life_mean_extensions")


# --------------------------------------------------------------------------
# Statuses & versioning
# --------------------------------------------------------------------------

class ResourceStatus(str, Enum):
    PROPOSED = "proposed"
    TESTED = "tested"
    APPROVED = "approved"
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass
class Version:
    major: int = 0
    minor: int = 0
    patch: int = 0
    tag: str = ""

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.tag}" if self.tag else base

    def bump(self, part: str = "patch") -> "Version":
        m, n, p, t = self.major, self.minor, self.patch, self.tag
        if part == "major":
            m, n, p = m + 1, 0, 0
        elif part == "minor":
            n, p = n + 1, 0
        else:
            p += 1
        return Version(m, n, p, t)


# --------------------------------------------------------------------------
# Skill registry
# --------------------------------------------------------------------------

@dataclass
class SkillDef:
    id: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    dependencies: List[str] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)  # paths or test ids
    status: ResourceStatus = ResourceStatus.PROPOSED
    version: Version = field(default_factory=Version)
    created_at: float = field(default_factory=time.time)
    approved_by: Optional[str] = None
    approval_note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "input_schema": self.input_schema, "output_schema": self.output_schema,
            "instructions": self.instructions, "dependencies": list(self.dependencies),
            "tests": list(self.tests), "status": self.status.value,
            "version": str(self.version), "created_at": self.created_at,
            "approved_by": self.approved_by, "approval_note": self.approval_note,
        }


class SkillRegistry:
    """Central registry of reusable skills (procedures)."""

    def __init__(self) -> None:
        self._skills: Dict[str, SkillDef] = {}

    def propose(self, skill: SkillDef) -> SkillDef:
        if skill.id in self._skills:
            existing = self._skills[skill.id]
            if existing.status == ResourceStatus.ACTIVE:
                raise ValueError(f"Skill {skill.id} already active")
            # bump version for updates
            skill.version = existing.version.bump("minor")
        self._skills[skill.id] = skill
        logger.info("Skill registered: %s v%s [%s]", skill.id, skill.version, skill.status)
        return skill

    def get(self, skill_id: str) -> Optional[SkillDef]:
        return self._skills.get(skill_id)

    def list_active(self) -> List[SkillDef]:
        return [s for s in self._skills.values() if s.status == ResourceStatus.ACTIVE]

    def approve(self, skill_id: str, by: str, note: str = "") -> Optional[SkillDef]:
        s = self._skills.get(skill_id)
        if not s:
            return None
        s.status = ResourceStatus.APPROVED
        s.approved_by = by
        s.approval_note = note[:500]
        logger.info("Skill approved: %s by %s", skill_id, by)
        return s

    def activate(self, skill_id: str) -> Optional[SkillDef]:
        s = self._skills.get(skill_id)
        if not s or s.status != ResourceStatus.APPROVED:
            return None
        s.status = ResourceStatus.ACTIVE
        s.version = s.version.bump("minor")
        logger.info("Skill activated: %s v%s", skill_id, s.version)
        return s

    def disable(self, skill_id: str) -> Optional[SkillDef]:
        s = self._skills.get(skill_id)
        if not s:
            return None
        s.status = ResourceStatus.DISABLED
        logger.info("Skill disabled: %s", skill_id)
        return s

    def rollback(self, skill_id: str) -> Optional[SkillDef]:
        """Deactivate and remove (full rollback)."""
        s = self._skills.pop(skill_id, None)
        if s:
            logger.info("Skill rolled back: %s", skill_id)
        return s

    def stats(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in ResourceStatus}
        for s in self._skills.values():
            counts[s.status.value] += 1
        return {"total": len(self._skills), **counts}


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------

@dataclass
class ToolDef:
    id: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    source_code: str = ""  # generated code (sandboxed until approved)
    dependencies: List[str] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)
    status: ResourceStatus = ResourceStatus.PROPOSED
    version: Version = field(default_factory=Version)
    created_at: float = field(default_factory=time.time)
    approved_by: Optional[str] = None
    approval_note: str = ""
    sandbox_path: Optional[Path] = None  # isolated location for generated code

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "input_schema": self.input_schema, "output_schema": self.output_schema,
            "source_code": (self.source_code or "")[:500],
            "dependencies": list(self.dependencies), "tests": list(self.tests),
            "status": self.status.value, "version": str(self.version),
            "created_at": self.created_at, "approved_by": self.approved_by,
            "approval_note": self.approval_note,
            "sandbox_path": str(self.sandbox_path) if self.sandbox_path else None,
        }


class ToolRegistry:
    """Central registry of available tools (with permissions)."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDef] = {}

    def propose(self, tool: ToolDef) -> ToolDef:
        if tool.id in self._tools:
            existing = self._tools[tool.id]
            if existing.status == ResourceStatus.ACTIVE:
                raise ValueError(f"Tool {tool.id} already active")
            tool.version = existing.version.bump("minor")
        self._tools[tool.id] = tool
        logger.info("Tool registered: %s v%s [%s]", tool.id, tool.version, tool.status)
        return tool

    def get(self, tool_id: str) -> Optional[ToolDef]:
        return self._tools.get(tool_id)

    def list_active(self) -> List[ToolDef]:
        return [t for t in self._tools.values() if t.status == ResourceStatus.ACTIVE]

    def approve(self, tool_id: str, by: str, note: str = "") -> Optional[ToolDef]:
        t = self._tools.get(tool_id)
        if not t:
            return None
        t.status = ResourceStatus.APPROVED
        t.approved_by = by
        t.approval_note = note[:500]
        logger.info("Tool approved: %s by %s", tool_id, by)
        return t

    def activate(self, tool_id: str) -> Optional[ToolDef]:
        t = self._tools.get(tool_id)
        if not t or t.status != ResourceStatus.APPROVED:
            return None
        t.status = ResourceStatus.ACTIVE
        t.version = t.version.bump("minor")
        logger.info("Tool activated: %s v%s", tool_id, t.version)
        return t

    def disable(self, tool_id: str) -> Optional[ToolDef]:
        t = self._tools.get(tool_id)
        if not t:
            return None
        t.status = ResourceStatus.DISABLED
        logger.info("Tool disabled: %s", tool_id)
        return t

    def rollback(self, tool_id: str) -> Optional[ToolDef]:
        t = self._tools.pop(tool_id, None)
        if t:
            logger.info("Tool rolled back: %s", tool_id)
        return t

    def stats(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in ResourceStatus}
        for t in self._tools.values():
            counts[t.status.value] += 1
        return {"total": len(self._tools), **counts}


# --------------------------------------------------------------------------
# Capability detector (hooks into debate results)
# --------------------------------------------------------------------------

@dataclass
class CapabilityNeed:
    id: str
    detected_at: float = field(default_factory=time.time)
    source_debate_id: Optional[str] = None
    source_run_id: Optional[str] = None
    evidence: str = ""
    suggested_skill_id: Optional[str] = None
    suggested_tool_id: Optional[str] = None
    priority: int = 5  # 1=critical, 10=low

    def to_dict(self) -> dict:
        return {
            "id": self.id, "detected_at": self.detected_at,
            "source_debate_id": self.source_debate_id,
            "source_run_id": self.source_run_id,
            "evidence": (self.evidence or "")[:500],
            "suggested_skill_id": self.suggested_skill_id,
            "suggested_tool_id": self.suggested_tool_id,
            "priority": self.priority,
        }


class CapabilityDetector:
    """Analyzes debate outcomes and tool usage to detect missing capabilities."""

    def __init__(self, skill_registry: SkillRegistry, tool_registry: ToolRegistry) -> None:
        self.skills = skill_registry
        self.tools = tool_registry
        self._needs: Dict[str, CapabilityNeed] = {}

    def analyze_debate_result(
        self,
        debate_id: str,
        run_id: str,
        topic: str,
        turn_count: int,
        final_response: str,
        is_valid: bool,
        validation_reasons: List[str],
        tools_used: List[str] = None,
    ) -> Optional[CapabilityNeed]:
        """Detect capability gaps from a single debate run."""
        needs: List[CapabilityNeed] = []

        # 1) Validation failure → missing tool or skill
        if not is_valid and validation_reasons:
            for reason in validation_reasons:
                need_id = f"need-{uuid.uuid4().hex[:8]}"
                need = CapabilityNeed(
                    id=need_id,
                    source_debate_id=debate_id,
                    source_run_id=run_id,
                    evidence=f"Validation failed: {reason} | topic={topic[:100]}",
                    priority=3,
                )
                # Suggest a skill if no tools were used
                if not tools_used:
                    need.suggested_skill_id = f"skill-{need_id}"
                else:
                    need.suggested_tool_id = f"tool-{need_id}"
                needs.append(need)

        # 2) Low turn count with no response → engine stalled (missing capability)
        if turn_count == 0 and not final_response:
            need_id = f"need-{uuid.uuid4().hex[:8]}"
            needs.append(CapabilityNeed(
                id=need_id, source_debate_id=debate_id, source_run_id=run_id,
                evidence=f"No turns executed for topic: {topic[:100]}", priority=2,
            ))

        # 3) Stagnation detection (repeated validation reasons)
        if len(validation_reasons) > 2:
            need_id = f"need-{uuid.uuid4().hex[:8]}"
            needs.append(CapabilityNeed(
                id=need_id, source_debate_id=debate_id, source_run_id=run_id,
                evidence=f"Stagnation detected ({len(validation_reasons)} reasons): {validation_reasons[:3]}",
                priority=4,
            ))

        # Persist and return first (highest priority) need
        for need in needs:
            self._needs[need.id] = need
            logger.info("Capability need detected: %s (priority %d)", need.id, need.priority)

        return min(needs, key=lambda n: n.priority) if needs else None

    def detect_from_tool_failure(
        self, tool_id: str, error: str, task_description: str = ""
    ) -> Optional[CapabilityNeed]:
        """Detect missing capability when a tool fails."""
        need_id = f"need-{uuid.uuid4().hex[:8]}"
        need = CapabilityNeed(
            id=need_id,
            evidence=f"Tool failure [{tool_id}]: {error} | task={task_description[:100]}",
            priority=3,
            suggested_tool_id=f"tool-fix-{need_id}",
        )
        self._needs[need_id] = need
        logger.info("Capability need from tool failure: %s", need_id)
        return need

    def list_needs(self, *, active_only: bool = False) -> List[CapabilityNeed]:
        if active_only:
            return [n for n in self._needs.values()
                    if n.suggested_skill_id or n.suggested_tool_id]
        return list(self._needs.values())

    def resolve(self, need_id: str, *, approved: bool = False) -> Optional[CapabilityNeed]:
        need = self._needs.get(need_id)
        if not need:
            return None
        need.evidence += f" | resolved={'approved' if approved else 'rejected'}"
        return need

    def stats(self) -> Dict[str, Any]:
        needs = list(self._needs.values())
        by_priority = {}
        for n in needs:
            by_priority[n.priority] = by_priority.get(n.priority, 0) + 1
        return {
            "total": len(needs),
            "by_priority": dict(sorted(by_priority.items())),
            "with_suggestions": sum(1 for n in needs if n.suggested_skill_id or n.suggested_tool_id),
        }
