"""Deterministic design validation — runs BEFORE any execution, no LLM.

Validation is DETERMINISTIC FIRST: it checks structure, references and
executor compatibility with the existing capability catalog, and reports
explicit categories (spec §21). A design that fails here is DESIGN_INVALID;
execution must never be attempted on an unfrozen or invalid design.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from experimental.schema import ExperimentDesign
from experimental.dispatch import EXECUTOR_NOT_AVAILABLE, STAGE_EXECUTORS


class DesignInvalid(ValueError):
    """A design failed deterministic validation. ``category`` follows §21."""

    def __init__(self, message: str, category: str = "DESIGN_INVALID") -> None:
        super().__init__(message)
        self.category = category


def validate_design(design: ExperimentDesign) -> Tuple[bool, List[str]]:
    """Validate a design structurally. Returns (ok, errors). No LLM, no I/O."""
    errors: List[str] = []

    if not (design.title or design.description or design.research_question):
        errors.append("design must carry a title, description or research_question")

    # agents must be well formed and uniquely keyed
    ids = [a.agent_id for a in design.agents]
    if not ids:
        errors.append("design has no agents")
    if len(set(ids)) != len(ids):
        errors.append("duplicate agent_id in agents")
    for a in design.agents:
        if not a.agent_id:
            errors.append("agent with empty agent_id")
        if not a.role:
            errors.append(f"agent {a.agent_id!r} has no role")

    # stages must reference known agents and a known executor
    if not design.stages:
        errors.append("design has no stages")
    stage_ids = [s.stage_id for s in design.stages]
    if len(set(stage_ids)) != len(stage_ids):
        errors.append("duplicate stage_id in stages")
    agent_set = set(ids)
    for s in design.stages:
        if not s.executor_type:
            errors.append(f"stage {s.stage_id!r} has no executor_type")
            continue
        if s.executor_type not in STAGE_EXECUTORS:
            errors.append(f"stage {s.stage_id!r} executor_type '{s.executor_type}' is unknown")
        missing = [p for p in s.participants if p not in agent_set]
        if missing:
            errors.append(f"stage {s.stage_id!r} references unknown agents {missing}")

    # budgets sane
    b = design.budgets
    if b.max_agent_calls <= 0 or b.max_iterations <= 0 or b.max_tool_calls <= 0:
        errors.append("budgets must be strictly positive")
    if b.max_runtime_seconds <= 0:
        errors.append("max_runtime_seconds must be positive")

    return (len(errors) == 0, errors)


def require_executable(design: ExperimentDesign) -> None:
    """Gate before running: the design must be FROZEN and valid. Raises an
    explicit category — never a silent fallback to a different design."""
    if not design.can_run:
        raise DesignInvalid("cannot run an experiment that is not FROZEN", "DESIGN_INVALID")
    ok, errors = validate_design(design)
    if not ok:
        raise DesignInvalid("; ".join(errors), "DESIGN_INVALID")


def check_stage_executor(executor_type: str) -> Optional[Dict[str, Any]]:
    """Return the executor descriptor for a stage's executor_type, or raise
    EXECUTOR_NOT_AVAILABLE when no compatible/connected executor exists.

    This is where a selected stage is matched to an EXISTING engine — the
    dispatcher never invents a fallback executor."""
    cap = STAGE_EXECUTORS.get(executor_type)
    if cap is None:
        raise EXECUTOR_NOT_AVAILABLE(
            f"executor_type '{executor_type}' has no registered executor", executor_type)
    if not cap.get("connected"):
        raise EXECUTOR_NOT_AVAILABLE(
            f"executor_type '{executor_type}' targets {cap.get('engine')} which is "
            "not connected now", executor_type,
            engine=cap.get("engine"))
    return cap