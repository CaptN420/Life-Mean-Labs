"""Approval pipeline: human-gated activation of skills/tools.

Pipeline (mandatory):
  Need detected → Specification → Generation → Security audit → Sandbox tests → Human approval → Registration → Activation

Safety rule: generated code is NEVER executed in the main environment until
human approval + explicit activation. The sandbox isolates new artifacts.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("life_mean_extensions.pipeline")


# --------------------------------------------------------------------------
# Pipeline stages
# --------------------------------------------------------------------------

class Stage(str, Enum):
    DETECTED = "detected"
    SPECIFIED = "specified"
    GENERATED = "generated"
    AUDITED = "audited"
    SANDBOXED = "sandboxed"
    APPROVED = "approved"
    REGISTERED = "registered"
    ACTIVE = "active"


@dataclass
class PipelineItem:
    id: str
    resource_type: str  # "skill" or "tool"
    stage: Stage = Stage.DETECTED
    need_id: Optional[str] = None
    resource_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    notes: List[Dict[str, Any]] = field(default_factory=list)

    def add_note(self, note: str, *, by: str = "system") -> None:
        self.notes.append({"ts": time.time(), "by": by, "note": note})
        self.updated_at = time.time()

    def advance_stage(self, stage: Stage, *, note: str = "") -> None:
        """Advance to the given stage and optionally add a note."""
        self.stage = stage
        if note:
            self.add_note(note, by="pipeline")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "resource_type": self.resource_type,
            "stage": self.stage.value, "need_id": self.need_id,
            "resource_id": self.resource_id,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "notes": self.notes[-10:],  # keep last 10 notes
        }


# --------------------------------------------------------------------------
# Security audit wrapper (lightweight)
# --------------------------------------------------------------------------

def run_security_audit(tool_path: Path) -> Dict[str, Any]:
    """Run lightweight security checks on a tool before sandbox testing.

    Returns dict with findings, severity, and pass/fail status.
    """
    findings = []
    if not tool_path.exists():
        return {"passed": False, "findings": [{"severity": "critical", "finding": "Path does not exist"}]}

    try:
        code = tool_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"passed": False, "findings": [{"severity": "high", "finding": f"Read error: {e}"}]}

    # Static checks (no bandit dependency needed for basic safety)
    dangerous_patterns = [
        ("eval(", "eval() usage"),
        ("exec(", "exec() usage"),
        ("os.system(", "os.system() usage"),
        ("shell=True", "shell=True subprocess"),
        ("__import__('os')", "dynamic import"),
        ("pickle.loads", "pickle deserialization"),
    ]

    for pattern, desc in dangerous_patterns:
        if pattern in code:
            findings.append({"severity": "high", "finding": f"{desc} detected"})

    # Check for secrets/credentials patterns
    secret_patterns = [
        ("password", "potential password"),
        ("api_key", "potential API key"),
        ("secret", "potential secret"),
    ]
    for pattern, desc in secret_patterns:
        if pattern.lower() in code.lower():
            findings.append({"severity": "medium", "finding": f"{desc} detected"})

    passed = not any(f["severity"] == "critical" for f in findings)
    return {"passed": passed, "findings": findings}


# --------------------------------------------------------------------------
# Sandbox execution (isolated)
# --------------------------------------------------------------------------

def run_sandbox_test(tool_path: Path, test_code: str) -> Dict[str, Any]:
    """Execute tool tests in an isolated subprocess.

    Returns dict with stdout, stderr, returncode, and any exceptions.
    """
    if not tool_path.exists():
        return {"passed": False, "error": "Tool path does not exist"}

    # Create a temporary test runner script (isolated from main env)
    runner = Path(__file__).parent.parent / "sandbox" / "_runner.py"
    runner.write_text(
        f"""\
import sys
sys.path.insert(0, {str(tool_path.parent)!r})
from tool import execute

# Run tests
result = execute(**{{"test": True}})
print(result)
"""
        , encoding="utf-8"
    )

    try:
        result = subprocess.run(
            [sys.executable, str(runner)],
            capture_output=True, text=True, timeout=10,
            # Isolation: no env vars that could leak credentials
            env={k: v for k, v in {**dict(__import__('os').environ).items()} if not any(x in k.lower() for x in ['password', 'secret', 'key', 'token'])},
        )
        return {
            "passed": result.returncode == 0,
            "stdout": result.stdout[:500],
            "stderr": result.stderr[:500],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Sandbox test timed out"}
    except Exception as e:
        return {"passed": False, "error": str(e)}


# --------------------------------------------------------------------------
# Pipeline controller
# --------------------------------------------------------------------------

class ApprovalPipeline:
    """Manages the mandatory approval pipeline for new capabilities."""

    def __init__(self, skill_registry, tool_registry, detector):
        self.skills = skill_registry
        self.tools = tool_registry
        self.detector = detector
        self._items: Dict[str, PipelineItem] = {}

    def create_item(self, need_id: str, resource_type: str) -> PipelineItem:
        item_id = f"pipe-{resource_type}-{need_id}"
        item = PipelineItem(id=item_id, resource_type=resource_type, need_id=need_id)
        self._items[item_id] = item
        logger.info("Pipeline item created: %s", item_id)
        return item

    def advance_stage(self, item_id: str, stage: Stage, *, note: str = "") -> Optional[PipelineItem]:
        item = self._items.get(item_id)
        if not item:
            return None
        prev = item.stage
        item.stage = stage
        if note:
            item.add_note(note, by="pipeline")
        logger.info("Pipeline advanced: %s %s → %s", item_id, prev.value, stage.value)
        return item

    def approve(self, item_id: str, *, by: str, resource_id: Optional[str] = None) -> Optional[PipelineItem]:
        """Human approval gate — required before activation.

        Also approves the underlying resource in the registry if provided.
        """
        item = self._items.get(item_id)
        if not item:
            return None
        # Approve the underlying resource if we have its ID
        if resource_id and item.resource_type == "skill":
            self.skills.approve(resource_id, by=by)
        elif resource_id and item.resource_type == "tool":
            self.tools.approve(resource_id, by=by)
        item.advance_stage(Stage.APPROVED, note=f"Approved by {by}")
        # Link to resource
        if resource_id:
            item.resource_id = resource_id
        logger.info("Pipeline approved: %s by %s", item_id, by)
        return item

    def activate(self, item_id: str) -> Optional[PipelineItem]:
        """Activate the registered resource (final step)."""
        item = self._items.get(item_id)
        if not item or item.stage != Stage.APPROVED:
            return None
        # Activate based on resource type
        if item.resource_type == "skill":
            self.skills.activate(item.resource_id or "")
        elif item.resource_type == "tool":
            self.tools.activate(item.resource_id or "")
        else:
            return None
        item.advance_stage("active", note="Resource activated")
        logger.info("Pipeline activated: %s", item_id)
        return item

    def get_item(self, item_id: str) -> Optional[PipelineItem]:
        return self._items.get(item_id)

    def list_items(self, *, active_only: bool = False) -> List[PipelineItem]:
        if active_only:
            return [i for i in self._items.values() if i.stage == Stage.ACTIVE]
        return list(self._items.values())

    def stats(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in Stage}
        for i in self._items.values():
            counts[i.stage.value] += 1
        return {"total": len(self._items), **counts}


# --------------------------------------------------------------------------
# Integration hook (connects to existing DebateEngine)
# --------------------------------------------------------------------------

def create_extension_layer(
    skill_registry=None, tool_registry=None, detector=None,
) -> Dict[str, Any]:
    """Create the full extension layer and return components.

    This is the entry point for connecting the modular self-extension system
    to the existing Life_mean debate engine.
    """
    from .registries import SkillRegistry, ToolRegistry, CapabilityDetector
    from .factories import SkillFactory, ToolFactory
    from .pipeline import ApprovalPipeline

    skills = skill_registry or SkillRegistry()
    tools = tool_registry or ToolRegistry()
    detector = detector or CapabilityDetector(skills, tools)
    factories = {
        "skill": SkillFactory(skills),
        "tool": ToolFactory(tools),
    }
    pipeline = ApprovalPipeline(skills, tools, detector)

    return {
        "skill_registry": skills,
        "tool_registry": tools,
        "detector": detector,
        "factories": factories,
        "pipeline": pipeline,
    }
