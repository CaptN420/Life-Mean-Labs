"""Orchestration abstractions — core data model.

Defines the interfaces used by all three orchestration modes (A/B/C) and the
divergence/convergence engine. These are pure Python, no LLM dependency.

Invariants:
  - Agent describes RESPONSIBILITY, not a concrete model instance.
  - Task carries its own context budget; the orchestrator enforces it.
  - Result is immutable once produced (traceable, reproducible).
  - Branch isolates a hypothesis with its own context and evaluation.
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


# ── Enums ────────────────────────────────────────────────────────────────────


class AgentType(str, enum.Enum):
    """Logical role an agent plays in a run. NOT a model identity."""
    PLANNER = "planner"
    DEVELOPER = "developer"
    CRITIC = "critic"
    REVIEWER = "reviewer"
    JUDGE = "judge"
    ARCHITECT = "architect"
    TESTER = "tester"
    INTEGRATOR = "integrator"


class Strategy(str, enum.Enum):
    """Orchestration strategy selected by StrategyRouter."""
    SINGLE_MODEL_MULTI_ROLE = "single_model_multi_role"   # Mode A
    MULTI_MODEL_COLLABORATION = "multi_model_collaboration"  # Mode B
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    DIVERGENT = "divergent"
    CONVERGENT = "convergent"


class BranchStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    EVALUATED = "evaluated"
    SELECTED = "selected"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class ValidationResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


# ── Core dataclasses ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentSpec:
    """Declarative description of an agent's responsibility.

    Does NOT bind to a concrete model — model assignment happens at runtime
    via RoleModelMapping (see role_templates/core.py).
    """
    agent_id: str
    agent_type: AgentType
    instructions_template: str = ""
    objectives: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    # Optional model slot reference (e.g. "GENERAL_REASONING_MODEL").
    model_slot: str = ""

    def content_hash(self) -> str:
        """Deterministic hash of the meaningful payload."""
        payload = {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "instructions_template": self.instructions_template,
            "objectives": sorted(self.objectives),
            "constraints": sorted(self.constraints),
            "allowed_tools": sorted(self.allowed_tools),
            "model_slot": self.model_slot,
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class Task:
    """A unit of work to be orchestrated.

    Carries its own context budget so the orchestrator can enforce limits
    without guessing.
    """
    task_id: str
    description: str
    domain: str = ""
    difficulty: Optional[int] = None  # 1-5
    context_budget_tokens: int = 4096
    max_steps: int = 20
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_complex(self) -> bool:
        """Heuristic: tasks above difficulty 3 or with large budget are complex."""
        return (self.difficulty or 0) >= 3 or self.context_budget_tokens > 8192


@dataclass
class StepResult:
    """Outcome of a single agent step within a run."""
    step_index: int
    agent_type: AgentType
    input_summary: str = ""
    output: str = ""
    tools_used: List[str] = field(default_factory=list)
    tokens_consumed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.error is None and bool(self.output.strip())


@dataclass
class AgentResult:
    """Complete result of an agent's execution within a run."""
    run_id: str
    task_id: str
    strategy: Strategy
    steps: List[StepResult] = field(default_factory=list)
    final_output: str = ""
    validation_result: Optional[ValidationResult] = None
    tokens_total: int = 0
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """True when there is substantive output or all steps succeeded."""
        has_output = bool(self.final_output.strip())
        has_successful_steps = len(self.steps) > 0 and all(s.is_success for s in self.steps)
        return has_output or has_successful_steps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "strategy": self.strategy.value,
            "steps": [
                {
                    "step_index": s.step_index,
                    "agent_type": s.agent_type.value,
                    "input_summary": s.input_summary,
                    "output_len": len(s.output),
                    "tools_used": s.tools_used,
                    "tokens_consumed": s.tokens_consumed,
                    "duration_seconds": s.duration_seconds,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "final_output_len": len(self.final_output),
            "validation_result": self.validation_result.value if self.validation_result else None,
            "tokens_total": self.tokens_total,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


@dataclass
class Branch:
    """A divergent hypothesis with isolated context and evaluation.

    Each branch represents an independent attempt at solving the task.
    Branches are evaluated by deterministic tools (not LLM auto-assessment).
    """
    branch_id: str
    task_id: str
    strategy_label: str = ""
    status: BranchStatus = BranchStatus.PENDING
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    result: Optional[AgentResult] = None
    evaluation: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    selected_at: Optional[float] = None

    @property
    def is_evaluated(self) -> bool:
        return self.status == BranchStatus.EVALUATED

    @property
    def is_selected(self) -> bool:
        return self.status == BranchStatus.SELECTED


@dataclass
class ConvergenceResult:
    """Outcome of merging or selecting among branches."""
    selected_branch_id: str
    integration_method: str = "single_best"  # single_best | merged_compatible | rollback
    merged_outputs: Optional[Dict[str, str]] = None
    validation_passed: bool = False
    notes: str = ""


@dataclass
class OrchestrationTrace:
    """Full observable trace of an orchestration run.

    Records every decision the orchestrator made, enabling post-hoc analysis
    and reproducibility.
    """
    run_id: str
    task_id: str
    strategy_chosen: Strategy
    reason: str = ""
    branches_created: int = 0
    branches_evaluated: int = 0
    branches_selected: int = 0
    tokens_total: int = 0
    duration_seconds: float = 0.0
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def record_decision(self, decision_type: str, details: Dict[str, Any]) -> None:
        self.decisions.append({
            "type": decision_type,
            "timestamp": time.time(),
            "details": details,
        })
