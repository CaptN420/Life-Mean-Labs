"""AdaptiveStrategyController — configurable strategy selection with explainability.

Uses TaskAnalyzer to estimate task properties, then selects an appropriate
orchration strategy with full decision trace. Supports:
  - Simple tasks → direct execution
  - Medium tasks → Mode A (Single Model Multi-Role)
  - Complex + parallelizable → Mode B (Multi-Model Collaboration)
  - Uncertain tasks → Divergence with multiple hypotheses
  - Verifiable failures → Targeted repair
  - Budget exhausted → Early stop with partial report

Every decision is recorded and explainable.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import (
    AgentResult,
    Branch,
    BranchStatus,
    ConvergenceResult,
    OrchestrationTrace,
    Strategy,
    Task,
)
from .task_analyzer import TaskAnalysis, TaskAnalyzer, UncertaintyLevel
from .divergence_engine import DivergenceEngine, DivergenceResult
from .convergence_engine import ConvergenceEngine, ConvergenceAnalysis, ConvergenceOutcome

logger = logging.getLogger("Life_mean.Orchestrator.AdaptiveController")


# ── Controller decisions ──────────────────────────────────────────────────────


class ControllerDecision(str, enum.Enum):
    DIRECT_EXECUTION = "direct_execution"
    MODE_A_MULTI_ROLE = "mode_a_multi_role"
    MODE_B_COLLABORATION = "mode_b_collaboration"
    DIVERGENCE = "divergence"
    TARGETED_REPAIR = "targeted_repair"
    EARLY_STOP = "early_stop"


@dataclass
class StrategyDecision:
    """Complete decision record for a strategy selection."""
    decision_type: ControllerDecision
    strategy: Strategy
    reason: str
    analysis: Optional[TaskAnalysis] = None
    alternatives_considered: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_type": self.decision_type.value,
            "strategy": self.strategy.value,
            "reason": self.reason,
            "analysis_summary": {
                "complexity": self.analysis.complexity if self.analysis else None,
                "subtasks": self.analysis.independent_subtasks if self.analysis else None,
                "uncertainty": self.analysis.uncertainty.value if self.analysis else None,
                "risk": self.analysis.risk_level.value if self.analysis else None,
            } if self.analysis else None,
            "alternatives": self.alternatives_considered,
            "metadata": self.metadata,
        }


# ── AdaptiveStrategyController ────────────────────────────────────────────────


class AdaptiveStrategyController:
    """Configurable strategy controller for adaptive orchestration.

    Uses TaskAnalyzer to estimate task properties and selects strategies
    based on deterministic rules with full explainability.
    """

    # Configuration defaults.
    DEFAULT_MAX_BRANCHES = 3
    DEFAULT_ENABLE_DIVERGENCE = True
    DEFAULT_TOKEN_BUDGET = 16384
    DEFAULT_TIME_BUDGET_SECONDS = 300.0

    def __init__(
        self,
        analyzer: Optional[TaskAnalyzer] = None,
        max_branches: int = DEFAULT_MAX_BRANCHES,
        enable_divergence: bool = DEFAULT_ENABLE_DIVERGENCE,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    ) -> None:
        self._analyzer = analyzer or TaskAnalyzer()
        self._max_branches = max_branches
        self._enable_divergence = enable_divergence
        self._token_budget = token_budget
        self._time_budget_seconds = time_budget_seconds

        # Decision history for learning.
        self._decision_history: List[StrategyDecision] = []

        # Sub-engines for divergence and convergence.
        self._divergence_engine: Optional[DivergenceEngine] = None
        self._convergence_engine: Optional[ConvergenceEngine] = None

    @property
    def analyzer(self) -> TaskAnalyzer:
        return self._analyzer

    def analyze(self, task: Task, resources: Optional[Dict[str, Any]] = None
                ) -> TaskAnalysis:
        """Analyze a task using the embedded analyzer."""
        return self._analyzer.analyze(task, resources)

    def select_strategy(self, task: Task, resources: Optional[Dict[str, Any]] = None
                        ) -> StrategyDecision:
        """Select the optimal strategy for a task with full explanation."""
        analysis = self.analyze(task, resources)

        # Rule 1: Simple tasks → direct execution.
        if analysis.is_simple:
            decision = StrategyDecision(
                decision_type=ControllerDecision.DIRECT_EXECUTION,
                strategy=Strategy.SEQUENTIAL,
                reason=f"Simple task (complexity={analysis.complexity}, subtasks={analysis.independent_subtasks})",
                analysis=analysis,
                alternatives_considered=["mode_a_multi_role"],
            )
            self._record_decision(decision)
            return decision

        # Rule 2: Complex + uncertain → divergence.
        if analysis.is_uncertain and self._enable_divergence:
            decision = StrategyDecision(
                decision_type=ControllerDecision.DIVERGENCE,
                strategy=Strategy.DIVERGENT,
                reason=(
                    f"Complex ({analysis.complexity}) + uncertain "
                    f"({analysis.uncertainty.value}) → explore multiple hypotheses"
                ),
                analysis=analysis,
                alternatives_considered=["mode_a_multi_role", "mode_b_collaboration"],
                metadata={"max_branches": self._max_branches},
            )
            self._record_decision(decision)
            return decision

        # Rule 3: Complex + parallelizable → Mode B.
        if analysis.is_complex and analysis.independent_subtasks >= 2:
            decision = StrategyDecision(
                decision_type=ControllerDecision.MODE_B_COLLABORATION,
                strategy=Strategy.MULTI_MODEL_COLLABORATION,
                reason=(
                    f"Complex ({analysis.complexity}) with "
                    f"{analysis.independent_subtasks} independent subtasks → parallel collaboration"
                ),
                analysis=analysis,
                alternatives_considered=["mode_a_multi_role", "divergence"],
            )
            self._record_decision(decision)
            return decision

        # Rule 4: Default → Mode A (Single Model Multi-Role).
        decision = StrategyDecision(
            decision_type=ControllerDecision.MODE_A_MULTI_ROLE,
            strategy=Strategy.SINGLE_MODEL_MULTI_ROLE,
            reason=(
                f"Medium complexity ({analysis.complexity}) → "
                "single model multi-role (most resource-efficient)"
            ),
            analysis=analysis,
            alternatives_considered=["direct_execution", "divergence"],
        )
        self._record_decision(decision)
        return decision

    def suggest_branches(self, task: Task, analysis: TaskAnalysis) -> List[Dict[str, str]]:
        """Suggest independent branch strategies for divergence."""
        if analysis.uncertainty != UncertaintyLevel.HIGH:
            return []

        return [
            {"label": "direct", "description": "Direct implementation from plan"},
            {"label": "decomposed", "description": "Decompose sub-problems then assemble"},
            {"label": "pattern", "description": "Pattern-based solution from similar cases"},
        ][:self._max_branches]

    def check_budget(self, tokens_used: int, time_elapsed: float) -> ControllerDecision:
        """Check if budget is exhausted and return early-stop decision if so."""
        token_ratio = tokens_used / self._token_budget if self._token_budget > 0 else 0
        time_ratio = time_elapsed / self._time_budget_seconds if self._time_budget_seconds > 0 else 0

        if token_ratio >= 0.9 or time_ratio >= 0.9:
            return ControllerDecision.EARLY_STOP

        return ControllerDecision.DIRECT_EXECUTION  # Continue

    def record_observation(self, task_id: str, analysis: TaskAnalysis,
                           passed: bool, steps_taken: int = 0,
                           tokens_used: int = 0) -> None:
        """Record an observation to refine future estimates."""
        self._analyzer.record_observation(
            task_id=task_id,
            estimated=analysis,
            actual_passed=passed,
            actual_steps=steps_taken,
            actual_tokens=tokens_used,
        )

    def get_learning_summary(self) -> Dict[str, Any]:
        """Return summary of learning from past decisions and observations."""
        return self._analyzer.get_learning_summary()

    def _record_decision(self, decision: StrategyDecision) -> None:
        """Record a decision for traceability and learning."""
        self._decision_history.append(decision)
        logger.debug(
            "Recorded decision: %s → %s (reason: %s)",
            decision.decision_type.value,
            decision.strategy.value,
            decision.reason[:80],
        )

    def get_decision_history(self) -> List[Dict[str, Any]]:
        """Return the history of strategy decisions."""
        return [d.to_dict() for d in self._decision_history]

    def build_trace(self, run_id: str, task: Task,
                    decision: StrategyDecision) -> OrchestrationTrace:
        """Build an orchestration trace from a strategy decision."""
        trace = OrchestrationTrace(
            run_id=run_id,
            task_id=task.task_id,
            strategy_chosen=decision.strategy,
            reason=decision.reason,
        )
        trace.record_decision("strategy_selection", decision.to_dict())
        return trace

    def converge(self, branches: List[Branch],
                 trace: OrchestrationTrace) -> ConvergenceResult:
        """Select the best branch based on deterministic evaluation.

        Prefers branches with:
          1. Validation pass
          2. Lower token consumption
          3. Shorter duration
        """
        evaluated = [b for b in branches if b.is_evaluated]
        if not evaluated:
            return ConvergenceResult(
                selected_branch_id=branches[0].branch_id if branches else "",
                integration_method="rollback",
                notes="No branches evaluated; rolling back to first.",
            )

        def branch_score(b: Branch) -> tuple:
            validated = b.evaluation.get("validation_passed", False)
            tokens = b.result.tokens_total if b.result else 999999
            duration = b.result.duration_seconds if b.result else 999999
            return (1 if validated else 0, -tokens, -duration)

        best = max(evaluated, key=branch_score)
        trace.branches_evaluated = len(evaluated)
        trace.branches_selected = 1

        return ConvergenceResult(
            selected_branch_id=best.branch_id,
            integration_method="single_best",
            validation_passed=bool(best.evaluation.get("validation_passed")),
            notes=f"Selected branch '{best.strategy_label}' (tokens={best.result.tokens_total if best.result else 'N/A'}).",
        )

    def run_divergence(
        self,
        task: Task,
        executor: Optional[Any] = None,
        workspace_path: Optional[str] = None,
    ) -> tuple[DivergenceResult, ConvergenceAnalysis]:
        """Run divergence and convergence for a task.

        Args:
            task: The task to solve.
            executor: Callable(config, task) -> AgentResult. If None, uses dummy executor.
            workspace_path: Base workspace path for isolation.

        Returns:
            Tuple of (divergence_result, convergence_analysis).
        """
        # Initialize engines if needed.
        if self._divergence_engine is None:
            self._divergence_engine = DivergenceEngine(
                max_branches=self._max_branches,
                global_token_budget=self._token_budget,
                global_time_budget=self._time_budget_seconds,
            )
        if self._convergence_engine is None:
            self._convergence_engine = ConvergenceEngine()

        # Analyze task.
        analysis = self.analyze(task)

        # Run divergence.
        div_result = self._divergence_engine.execute_all(
            task=task,
            analysis=analysis,
            executor=executor or self._dummy_executor,
        )

        # Run convergence.
        conv_analysis = self._convergence_engine.analyze(
            task_id=task.task_id,
            branches=div_result.branches,
        )

        return div_result, conv_analysis

    def _dummy_executor(
        self, config, task: Task
    ) -> AgentResult:
        """Dummy executor for testing without real LLM."""
        from .models import AgentResult, Strategy
        return AgentResult(
            run_id="test",
            task_id=task.task_id,
            strategy=Strategy.DIVERGENT,
            final_output=f"Result for {config.strategy.value}",
            tokens_total=100,
            duration_seconds=0.1,
        )
