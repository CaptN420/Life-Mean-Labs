"""Real executor adapters that the ExperimentalEngine dispatches to.

Each adapter converts a design stage into a call against an EXISTING engine via
the existing stable core — CodeLabEngine for code stages, the synchronous tool
host for deterministic stages. Adapters are injected as ``executors={kind: fn}``
into :class:`experimental.engine.ExperimentalEngine`; the engine never calls an
engine directly. LLM-only stages (debate, research, synthesis, review) stay
NOT-connected here and are refused at dispatch before any adapter runs.
"""

from __future__ import annotations

from typing import Any, Dict

from experimental.engine import ExperimentalEngine
from experimental.schema import DesignStage, ExperimentDesign


def _stage_text(stage: DesignStage, design: ExperimentDesign) -> str:
    """Tell the executor WHAT this stage must produce (the stage request wins)."""
    return (stage.request or "").strip() or (design.research_question or "").strip() or design.description


def code_lab_adapter(stage: DesignStage, design: ExperimentDesign) -> Dict[str, Any]:
    """Run a code stage through the EXISTING CodeLabEngine (deterministic-first:
    ``multi_agent`` defaults to False unless the stage explicitly requests it)."""
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine

    cfg = CodeLabConfig(
        prompt=_stage_text(stage, design) or "Create a small Python program with unit tests.",
        template_id=str(stage.config.get("template_id", "coding-standard")),
        multi_agent=bool(stage.config.get("multi_agent", False)),
        run_tests=bool(stage.config.get("run_tests", True)),
        deterministic_validation=bool(stage.config.get("deterministic_validation", True)),
        role_models=dict(stage.config.get("role_models", {})),
        max_iterations=min(int(stage.config.get("max_iterations", 3)), design.budgets.max_iterations),
    )
    result = CodeLabEngine(config=cfg).run()
    return {"dispatched_to": "CodeLabEngine", "outcome": result.get("status"),
            "result": result}


def _tool_stage(tool_name: str, stage: DesignStage, design: ExperimentDesign) -> Dict[str, Any]:
    """Run a single deterministic tool through the existing stable tool host."""
    from core.workers.tool import _execute_tool

    args = dict(stage.config.get("args", {}))
    return {"dispatched_to": "ToolWorker", "tool": tool_name,
            "result": _execute_tool(tool_name, **args)}


def tool_adapter(stage: DesignStage, design: ExperimentDesign) -> Dict[str, Any]:
    """Deterministic / tool_execution stage: executes the tool named in
    ``stage.config['tool']`` (or auto-detects from the request when absent)."""
    from core.workers.tool import _execute_tool, detect_tool

    tool_name = str(stage.config.get("tool", ""))
    if not tool_name:
        det = detect_tool(_stage_text(stage, design) or "")
        if det:
            tool_name = det["tool_name"]
    if not tool_name:
        raise ValueError("a deterministic stage must declare stage.config['tool'] "
                         "(this stage did not, and no tool could be auto-detected)")
    args = dict(stage.config.get("args", {}))
    return {"dispatched_to": "ToolWorker", "tool": tool_name,
            "result": _execute_tool(tool_name, **args)}


def build_engine() -> ExperimentalEngine:
    """ExperimentalEngine pre-wired with the REAL Code Lab + ToolWorker adapters.

    For a deterministic validation stage the adapter runs a real tool; for a
    code stage a real CodeLabEngine run. Debate / research / synthesis / review
    stages are NOT registered: the dispatcher refuses them (EXECUTOR_NOT_AVAILABLE)
    before they could reach an adapter."""
    return ExperimentalEngine(executors={
        "code": code_lab_adapter,          # kind of code_lab / code / benchmark
        "deterministic": tool_adapter,     # kind of deterministic / tool_execution / validation
    })