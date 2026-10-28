"""API handlers for the modular self-extension layer.

Provides endpoints to inspect and manage skills, tools, capability needs,
and the approval pipeline — all human-gated (approval required before any
generated code is activated).

Endpoints:
  GET    /api/extensions/skills          -> list all skills with stats
  GET    /api/extensions/skills/{id}     -> one skill detail
  POST   /api/extensions/skills          -> propose a new skill
  PUT    /api/extensions/skills/{id}/approve  -> approve (by human)
  PUT    /api/extensions/skills/{id}/activate  -> activate approved skill
  PUT    /api/extensions/skills/{id}/disable  -> disable active skill
  DELETE /api/extensions/skills/{id}     -> rollback/remove

  GET    /api/extensions/tools           -> list all tools with stats
  GET    /api/extensions/tools/{id}      -> one tool detail (+ sandbox)
  POST   /api/extensions/tools           -> propose a new tool
  PUT    /api/extensions/tools/{id}/approve  -> approve (by human)
  PUT    /api/extensions/tools/{id}/activate  -> activate approved tool
  PUT    /api/extensions/tools/{id}/disable  -> disable active tool
  DELETE /api/extensions/tools/{id}     -> rollback/remove

  GET    /api/extensions/capabilities   -> list detected capability needs + stats
  POST   /api/extensions/capabilities/analyze  -> re-analyze a debate run
  PUT    /api/extensions/capabilities/{id}/resolve  -> mark resolved

  GET    /api/extensions/pipeline        -> list pipeline items + stats
  PUT    /api/extensions/pipeline/{id}/approve  -> human approval gate
  PUT    /api/extensions/pipeline/{id}/activate  -> activate approved item
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_ID_RE = re.compile(r"^/api/extensions/(skills|tools)/([^/]+)$")
_PIPELINE_RE = re.compile(r"^/api/extensions/pipeline/([^/]+)$")


class ExtensionsApiMixin:
    """Mixin providing /api/extensions/* handlers for the self-extension layer."""

    # Set by server (injected at startup)
    extension_layer: Dict[str, Any] = None  # type: ignore[assignment]

    # ── collaborators ──────────────────────────────────────────────────────
    def _ext_layer(self) -> Dict[str, Any]:
        if self.extension_layer is None:
            from .pipeline import create_extension_layer
            layer = create_extension_layer()
            self.extension_layer = layer
        return self.extension_layer

    @property
    def _skills(self):
        return self._ext_layer()["skill_registry"]

    @property
    def _tools(self):
        return self._ext_layer()["tool_registry"]

    @property
    def _detector(self):
        return self._ext_layer()["detector"]

    @property
    def _factories(self):
        return self._ext_layer()["factories"]

    @property
    def _pipeline(self):
        return self._ext_layer()["pipeline"]

    # ── GET handlers ───────────────────────────────────────────────────────
    def _extensions_skills_list(self) -> None:
        skills = list(self._skills.list_active())
        all_skills = list(self._skills._skills.values())
        stats = self._skills.stats()
        self._send_json({
            "active": [s.to_dict() for s in skills],
            "all": [s.to_dict() for s in all_skills],
            "stats": stats,
        })

    def _extensions_skill_get(self, skill_id: str) -> None:
        s = self._skills.get(skill_id)
        if s is None:
            self._send_error(404, f"Skill {skill_id} not found", code="not_found")
            return
        self._send_json({"skill": s.to_dict()})

    def _extensions_tools_list(self) -> None:
        tools = list(self._tools.list_active())
        all_tools = list(self._tools._tools.values())
        stats = self._tools.stats()
        self._send_json({
            "active": [t.to_dict() for t in tools],
            "all": [t.to_dict() for t in all_tools],
            "stats": stats,
        })

    def _extensions_tool_get(self, tool_id: str) -> None:
        t = self._tools.get(tool_id)
        if t is None:
            self._send_error(404, f"Tool {tool_id} not found", code="not_found")
            return
        self._send_json({"tool": t.to_dict()})

    def _extensions_capabilities_list(self) -> None:
        needs = self._detector.list_needs(active_only=True)
        stats = self._detector.stats()
        self._send_json({
            "needs": [n.to_dict() for n in needs],
            "stats": stats,
        })

    def _extensions_pipeline_list(self) -> None:
        items = self._pipeline.list_items()
        stats = self._pipeline.stats()
        self._send_json({
            "items": [i.to_dict() for i in items],
            "stats": stats,
        })

    # ── POST handlers ──────────────────────────────────────────────────────
    def _extensions_skill_create(self, data: Dict[str, Any]) -> None:
        from .registries import SkillDef, ResourceStatus
        from .factories import SkillSpec
        need_id = (data or {}).get("need_id", "")
        description = (data or {}).get("description", "")
        if not description:
            self._send_error(400, "description is required", code="invalid")
            return
        spec = SkillSpec(
            need_id=need_id,
            description=description,
            input_schema=(data or {}).get("input_schema", {}),
            output_schema=(data or {}).get("output_schema", {}),
            dependencies=list((data or {}).get("dependencies", []) or []),
            test_cases=list((data or {}).get("test_cases", []) or []),
        )
        skill = self._factories["skill"].propose_from_need(
            self._detector._needs.get(need_id) if need_id else None, spec
        )
        # Also create a pipeline item
        pipe_item = self._pipeline.create_item(need_id or skill.id, "skill")
        self._send_json({
            "skill_id": skill.id, "status": skill.status.value,
            "pipeline_item_id": pipe_item.id,
        })

    def _extensions_tool_create(self, data: Dict[str, Any]) -> None:
        from .registries import ToolDef, ResourceStatus
        from .factories import ToolSpec
        need_id = (data or {}).get("need_id", "")
        description = (data or {}).get("description", "")
        source_template = (data or {}).get("source_code", "")
        if not description:
            self._send_error(400, "description is required", code="invalid")
            return
        spec = ToolSpec(
            need_id=need_id,
            description=description,
            input_schema=(data or {}).get("input_schema", {}),
            output_schema=(data or {}).get("output_schema", {}),
            source_template=source_template,
            dependencies=list((data or {}).get("dependencies", []) or []),
            test_cases=list((data or {}).get("test_cases", []) or []),
        )
        tool = self._factories["tool"].propose_from_need(
            self._detector._needs.get(need_id) if need_id else None, spec
        )
        pipe_item = self._pipeline.create_item(need_id or tool.id, "tool")
        self._send_json({
            "tool_id": tool.id, "status": tool.status.value,
            "sandbox_path": str(tool.sandbox_path) if tool.sandbox_path else None,
            "pipeline_item_id": pipe_item.id,
        })

    def _extensions_capabilities_analyze(self, data: Dict[str, Any]) -> None:
        """Re-analyze a debate run to detect new capability needs."""
        debate_id = (data or {}).get("debate_id", "")
        run_id = (data or {}).get("run_id", "")
        topic = (data or {}).get("topic", "")
        turn_count = int((data or {}).get("turn_count", 0))
        final_response = (data or {}).get("final_response", "")
        is_valid = bool((data or {}).get("is_valid", False))
        validation_reasons = list((data or {}).get("validation_reasons", []) or [])
        tools_used = list((data or {}).get("tools_used", []) or [])
        need = self._detector.analyze_debate_result(
            debate_id, run_id, topic, turn_count, final_response,
            is_valid, validation_reasons, tools_used,
        )
        if need:
            self._send_json({"need_id": need.id, "priority": need.priority})
        else:
            self._send_json({"need_id": None, "message": "No new capability needs detected"})

    # ── PUT handlers ───────────────────────────────────────────────────────
    def _extensions_skill_approve(self, skill_id: str, data: Dict[str, Any]) -> None:
        by = (data or {}).get("by", "human")
        note = (data or {}).get("note", "")
        s = self._skills.approve(skill_id, by=by, note=note)
        if s is None:
            self._send_error(404, f"Skill {skill_id} not found", code="not_found")
            return
        # Also approve pipeline item if exists
        pipe_item = self._pipeline.get_item(f"pipe-skill-{skill_id}")
        if pipe_item:
            self._pipeline.approve(pipe_item.id, by=by, resource_id=skill_id)
        self._send_json({"skill_id": skill_id, "status": s.status.value})

    def _extensions_skill_activate(self, skill_id: str) -> None:
        s = self._skills.activate(skill_id)
        if s is None:
            self._send_error(400, f"Skill {skill_id} not approved", code="not_approved")
            return
        pipe_item = self._pipeline.get_item(f"pipe-skill-{skill_id}")
        if pipe_item:
            self._pipeline.activate(pipe_item.id)
        self._send_json({"skill_id": skill_id, "status": s.status.value})

    def _extensions_skill_disable(self, skill_id: str) -> None:
        s = self._skills.disable(skill_id)
        if s is None:
            self._send_error(404, f"Skill {skill_id} not found", code="not_found")
            return
        self._send_json({"skill_id": skill_id, "status": s.status.value})

    def _extensions_tool_approve(self, tool_id: str, data: Dict[str, Any]) -> None:
        by = (data or {}).get("by", "human")
        note = (data or {}).get("note", "")
        t = self._tools.approve(tool_id, by=by, note=note)
        if t is None:
            self._send_error(404, f"Tool {tool_id} not found", code="not_found")
            return
        pipe_item = self._pipeline.get_item(f"pipe-tool-{tool_id}")
        if pipe_item:
            self._pipeline.approve(pipe_item.id, by=by, resource_id=tool_id)
        self._send_json({"tool_id": tool_id, "status": t.status.value})

    def _extensions_tool_activate(self, tool_id: str) -> None:
        t = self._tools.activate(tool_id)
        if t is None:
            self._send_error(400, f"Tool {tool_id} not approved", code="not_approved")
            return
        pipe_item = self._pipeline.get_item(f"pipe-tool-{tool_id}")
        if pipe_item:
            self._pipeline.activate(pipe_item.id)
        self._send_json({"tool_id": tool_id, "status": t.status.value})

    def _extensions_tool_disable(self, tool_id: str) -> None:
        t = self._tools.disable(tool_id)
        if t is None:
            self._send_error(404, f"Tool {tool_id} not found", code="not_found")
            return
        self._send_json({"tool_id": tool_id, "status": t.status.value})

    def _extensions_capabilities_resolve(self, need_id: str, data: Dict[str, Any]) -> None:
        approved = bool((data or {}).get("approved", False))
        n = self._detector.resolve(need_id, approved=approved)
        if n is None:
            self._send_error(404, f"Need {need_id} not found", code="not_found")
            return
        self._send_json({"need_id": need_id, "resolved": approved})

    def _extensions_pipeline_approve(self, item_id: str, data: Dict[str, Any]) -> None:
        by = (data or {}).get("by", "human")
        resource_id = (data or {}).get("resource_id", "")
        item = self._pipeline.approve(item_id, by=by, resource_id=resource_id or None)
        if item is None:
            self._send_error(404, f"Pipeline item {item_id} not found", code="not_found")
            return
        self._send_json({"item_id": item_id, "stage": item.stage.value})

    def _extensions_pipeline_activate(self, item_id: str) -> None:
        item = self._pipeline.activate(item_id)
        if item is None:
            self._send_error(400, f"Pipeline item {item_id} not approved", code="not_approved")
            return
        self._send_json({"item_id": item_id, "stage": item.stage.value})

    # ── DELETE handlers ────────────────────────────────────────────────────
    def _extensions_skill_delete(self, skill_id: str) -> None:
        s = self._skills.rollback(skill_id)
        if s is None:
            self._send_error(404, f"Skill {skill_id} not found", code="not_found")
            return
        pipe_item = self._pipeline.get_item(f"pipe-skill-{skill_id}")
        if pipe_item:
            self._pipeline._items.pop(pipe_item.id, None)
        self._send_json({"skill_id": skill_id, "status": "rolled_back"})

    def _extensions_tool_delete(self, tool_id: str) -> None:
        t = self._tools.rollback(tool_id)
        if t is None:
            self._send_error(404, f"Tool {tool_id} not found", code="not_found")
            return
        pipe_item = self._pipeline.get_item(f"pipe-tool-{tool_id}")
        if pipe_item:
            self._pipeline._items.pop(pipe_item.id, None)
        self._send_json({"tool_id": tool_id, "status": "rolled_back"})

    # ── routing helpers ────────────────────────────────────────────────────
    @classmethod
    def match_extension_id(cls, path: str) -> Optional[tuple]:
        m = _ID_RE.match(path)
        return (m.group(1), m.group(2)) if m else None

    @classmethod
    def match_pipeline_id(cls, path: str) -> Optional[str]:
        m = _PIPELINE_RE.match(path)
        return m.group(1) if m else None
