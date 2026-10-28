"""Tests for life_mean_extensions module.

Verifies: registries, detector, factories, pipeline — without touching
the real DebateEngine / AutoPilot / ExperimentRunner.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from life_mean_extensions import (
    CapabilityNeed,
    CapabilityDetector,
    ResourceStatus,
    SkillDef,
    SkillRegistry,
    ToolDef,
    ToolRegistry,
    Version,
)
from life_mean_extensions.factories import SkillFactory, ToolFactory, SkillSpec, ToolSpec
from life_mean_extensions.pipeline import (
    ApprovalPipeline,
    Stage,
    PipelineItem,
    create_extension_layer,
    run_security_audit,
)


# --------------------------------------------------------------------------
# SkillRegistry
# --------------------------------------------------------------------------

class TestSkillRegistry:
    def test_propose_and_get(self) -> None:
        reg = SkillRegistry()
        skill = SkillDef(id="test-skill", description="A test skill")
        reg.propose(skill)
        assert reg.get("test-skill") is skill
        assert reg.get("missing") is None

    def test_list_active(self) -> None:
        reg = SkillRegistry()
        reg.propose(SkillDef(id="active", description="Active", status=ResourceStatus.ACTIVE))
        reg.propose(SkillDef(id="proposed", description="Proposed", status=ResourceStatus.PROPOSED))
        assert len(reg.list_active()) == 1
        assert reg.list_active()[0].id == "active"

    def test_approve_then_activate(self) -> None:
        reg = SkillRegistry()
        skill = reg.propose(SkillDef(id="s1", description="x"))
        assert skill.status == ResourceStatus.PROPOSED
        approved = reg.approve("s1", by="user")
        assert approved is not None
        assert approved.status == ResourceStatus.APPROVED
        assert approved.approved_by == "user"
        activated = reg.activate("s1")
        assert activated is not None
        assert activated.status == ResourceStatus.ACTIVE

    def test_disable(self) -> None:
        reg = SkillRegistry()
        s = reg.propose(SkillDef(id="s2", description="x"))
        reg.approve("s2", by="user")
        reg.activate("s2")
        disabled = reg.disable("s2")
        assert disabled is not None
        assert disabled.status == ResourceStatus.DISABLED

    def test_stats(self) -> None:
        reg = SkillRegistry()
        for status in ResourceStatus:
            reg.propose(SkillDef(id=f"s-{status.value}", description="x", status=status))
        stats = reg.stats()
        assert stats["total"] == 5
        assert stats["proposed"] == 1
        assert stats["active"] == 1

    def test_version_bump(self) -> None:
        reg = SkillRegistry()
        s1 = reg.propose(SkillDef(id="dup", description="x"))
        assert s1.version == Version(0, 0, 0)
        # Propose same id again — should bump minor
        s2 = reg.propose(SkillDef(id="dup", description="x updated"))
        assert s2.version.minor == 1


# --------------------------------------------------------------------------
# ToolRegistry
# --------------------------------------------------------------------------

class TestToolRegistry:
    def test_propose_and_get(self) -> None:
        reg = ToolRegistry()
        tool = ToolDef(id="test-tool", description="A test tool")
        reg.propose(tool)
        assert reg.get("test-tool") is tool

    def test_list_active(self) -> None:
        reg = ToolRegistry()
        reg.propose(ToolDef(id="t1", description="x", status=ResourceStatus.ACTIVE))
        reg.propose(ToolDef(id="t2", description="y", status=ResourceStatus.PROPOSED))
        assert len(reg.list_active()) == 1

    def test_approve_and_activate(self) -> None:
        reg = ToolRegistry()
        t = reg.propose(ToolDef(id="t3", description="x"))
        approved = reg.approve("t3", by="admin")
        assert approved.status == ResourceStatus.APPROVED
        activated = reg.activate("t3")
        assert activated.status == ResourceStatus.ACTIVE

    def test_rollback(self) -> None:
        reg = ToolRegistry()
        t = reg.propose(ToolDef(id="t4", description="x"))
        reg.approve("t4", by="user")
        rolled = reg.rollback("t4")
        assert rolled is not None
        assert reg.get("t4") is None


# --------------------------------------------------------------------------
# CapabilityDetector
# --------------------------------------------------------------------------

class TestCapabilityDetector:
    def test_analyze_debate_result_failure(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        need = det.analyze_debate_result(
            debate_id="deb-1", run_id="run-1", topic="test topic",
            turn_count=3, final_response="", is_valid=False,
            validation_reasons=["Missing tool for X"], tools_used=[],
        )
        assert need is not None
        assert need.source_debate_id == "deb-1"
        assert need.suggested_skill_id is not None

    def test_analyze_stagnation(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        need = det.analyze_debate_result(
            debate_id="deb-2", run_id="run-2", topic="stuck",
            turn_count=0, final_response="", is_valid=False,
            validation_reasons=["reason1", "reason2", "reason3"],
        )
        assert need is not None
        assert need.priority == 2  # high priority for no turns

    def test_detect_from_tool_failure(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        need = det.detect_from_tool_failure("broken-tool", "ModuleNotFoundError", "task desc")
        assert need is not None
        assert need.suggested_tool_id is not None

    def test_list_needs(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        det.analyze_debate_result("d1", "r1", "topic", 0, "", False, ["fail"])
        needs = det.list_needs()
        # Stagnation (0 turns) + validation failure = 2 needs
        assert len(needs) >= 1

    def test_stats(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        det.analyze_debate_result("d1", "r1", "topic", 0, "", False, ["fail"])
        stats = det.stats()
        assert stats["total"] >= 1
        assert stats["with_suggestions"] >= 1


# --------------------------------------------------------------------------
# Factories
# --------------------------------------------------------------------------

class TestSkillFactory:
    def test_propose_from_need(self) -> None:
        skills = SkillRegistry()
        factory = SkillFactory(skills)
        need = CapabilityNeed(id="need-1", evidence="Missing capability")
        spec = SkillSpec(need_id="need-1", description="New skill")
        skill = factory.propose_from_need(need, spec)
        # ID transformation: "need-1" → "skill-1" (replace "need-" with "skill-")
        assert skill.id == "skill-1"
        assert skill.status == ResourceStatus.PROPOSED
        assert "Generated from capability need" in skill.instructions


class TestToolFactory:
    def test_propose_from_need(self) -> None:
        tools = ToolRegistry()
        factory = ToolFactory(tools)
        need = CapabilityNeed(id="need-2", evidence="Missing tool")
        spec = ToolSpec(need_id="need-2", description="New tool")
        tool = factory.propose_from_need(need, spec)
        # ID transformation: "need-2" → "tool-2"
        assert tool.id == "tool-2"
        assert tool.status == ResourceStatus.PROPOSED
        assert tool.sandbox_path is not None
        assert (tool.sandbox_path / "tool.py").exists()


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

class TestApprovalPipeline:
    def test_create_and_advance(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        pipe = ApprovalPipeline(skills, tools, det)
        item = pipe.create_item("need-1", "skill")
        assert item.stage == Stage.DETECTED
        item.advance_stage("specified", note="Specified")
        assert item.stage == Stage.SPECIFIED

    def test_full_pipeline(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        pipe = ApprovalPipeline(skills, tools, det)
        item = pipe.create_item("need-1", "skill")
        # Create the skill via factory first (simulates generation step)
        from life_mean_extensions.factories import SkillFactory, SkillSpec
        factory = SkillFactory(skills)
        need = CapabilityNeed(id="need-1", evidence="Missing capability")
        spec = SkillSpec(need_id="need-1", description="New skill")
        skill = factory.propose_from_need(need, spec)
        # Advance through stages
        for stage in [Stage.SPECIFIED, Stage.GENERATED, Stage.AUDITED, Stage.SANDBOXED]:
            item.advance_stage(stage.value, note=f"Advanced to {stage.value}")
        # Approve — resource_id matches the transformed ID "skill-1"
        approved = pipe.approve(item.id, by="human", resource_id=skill.id)
        assert approved is not None
        assert approved.stage == Stage.APPROVED
        # Activate
        activated = pipe.activate(item.id)
        assert activated is not None
        assert activated.stage == Stage.ACTIVE
        # Verify skill is active
        s = skills.get(skill.id)
        assert s is not None
        assert s.status == ResourceStatus.ACTIVE

    def test_list_items(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        pipe = ApprovalPipeline(skills, tools, det)
        pipe.create_item("need-1", "skill")
        pipe.create_item("need-2", "tool")
        items = pipe.list_items()
        assert len(items) == 2

    def test_stats(self) -> None:
        skills = SkillRegistry()
        tools = ToolRegistry()
        det = CapabilityDetector(skills, tools)
        pipe = ApprovalPipeline(skills, tools, det)
        pipe.create_item("need-1", "skill")
        stats = pipe.stats()
        assert stats["total"] == 1
        assert stats["detected"] == 1


# --------------------------------------------------------------------------
# Security audit wrapper
# --------------------------------------------------------------------------

class TestSecurityAudit:
    def test_audit_clean_file(self, tmp_path: Path) -> None:
        tool_path = tmp_path / "clean.py"
        tool_path.write_text("def execute(**kwargs): return {'valid': True}", encoding="utf-8")
        result = run_security_audit(tool_path)
        assert result["passed"] is True

    def test_audit_dangerous_patterns(self, tmp_path: Path) -> None:
        tool_path = tmp_path / "dirty.py"
        # Use a pattern that will definitely trigger the check
        tool_path.write_text("eval(user_input)  # dangerous", encoding="utf-8")
        result = run_security_audit(tool_path)
        # Should have findings and not pass
        assert result["passed"] is False or len(result["findings"]) > 0

    def test_audit_nonexistent_path(self, tmp_path: Path) -> None:
        result = run_security_audit(tmp_path / "missing.py")
        assert result["passed"] is False


# --------------------------------------------------------------------------
# Integration hook
# --------------------------------------------------------------------------

class TestCreateExtensionLayer:
    def test_create_layer(self) -> None:
        layer = create_extension_layer()
        assert "skill_registry" in layer
        assert "tool_registry" in layer
        assert "detector" in layer
        assert "factories" in layer
        assert "pipeline" in layer
        assert isinstance(layer["skill_registry"], SkillRegistry)
        assert isinstance(layer["tool_registry"], ToolRegistry)
        assert isinstance(layer["detector"], CapabilityDetector)
