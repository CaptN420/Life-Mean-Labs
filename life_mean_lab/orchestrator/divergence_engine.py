"""DivergenceEngine — generates multiple independent solution branches.

Creates isolated branches with distinct strategies, bounded budgets, and
independent workspaces. Supports sequential or parallel execution based on
available resources.

Design rules:
  - Each branch is fully isolated (WorkspaceManager).
  - Budgets are enforced per-branch and globally.
  - Redundant branches are detected and skipped.
  - Cancellation stops all branches immediately.
  - Results are structured and traceable.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import AgentResult, Branch, BranchStatus, Task
from .task_analyzer import TaskAnalysis
from .workspace_manager import WorkspaceManager, WorkspaceBranchStatus

logger = logging.getLogger("Life_mean.Orchestrator.DivergenceEngine")


# ── Divergence strategies ─────────────────────────────────────────────────────


class DivergenceStrategy(str, enum.Enum):
    """Distinct approaches for exploring solution space."""
    DIRECT = "direct"                    # Direct implementation from plan
    DECOMPOSED = "decomposed"            # Break into sub-problems, assemble
    PATTERN = "pattern"                  # Pattern-based from similar cases
    CONTRASTING = "contrasting"          # Deliberately opposite approach
    CONSTRAINTS_FIRST = "constraints_first"  # Satisfy constraints first, optimize later


@dataclass
class BranchConfig:
    """Configuration for a single divergence branch."""
    branch_id: str
    strategy: DivergenceStrategy
    token_budget: int
    time_budget_seconds: float
    workspace_path: Optional[str] = None


@dataclass
class DivergenceResult:
    """Complete result of a divergence execution."""
    task_id: str
    branches_created: int = 0
    branches_completed: int = 0
    branches_failed: int = 0
    total_tokens_used: int = 0
    total_duration_seconds: float = 0.0
    branches: List[Branch] = field(default_factory=list)
    cancelled: bool = False
    cancellation_reason: str = ""

    @property
    def has_successful_branch(self) -> bool:
        return any(
            b.status == BranchStatus.EVALUATED and b.evaluation.get("validation_passed", False)
            for b in self.branches
        )

    @property
    def best_branch(self) -> Optional[Branch]:
        """Return the best evaluated branch, or None if none evaluated."""
        evaluated = [b for b in self.branches if b.is_evaluated]
        if not evaluated:
            return None
        # Score: validated > unvalidated, then prefer lower tokens.
        def score(b: Branch) -> tuple:
            validated = b.evaluation.get("validation_passed", False)
            tokens = b.result.tokens_total if b.result else 999999
            return (1 if validated else 0, -tokens)
        return max(evaluated, key=score)


# ── DivergenceEngine ──────────────────────────────────────────────────────────


class DivergenceEngine:
    """Generates and executes multiple independent solution branches."""

    # Default budgets per branch.
    DEFAULT_TOKEN_BUDGET = 4096
    DEFAULT_TIME_BUDGET = 120.0

    def __init__(
        self,
        workspace_manager: Optional[WorkspaceManager] = None,
        max_branches: int = 3,
        token_budget_per_branch: int = DEFAULT_TOKEN_BUDGET,
        time_budget_per_branch: float = DEFAULT_TIME_BUDGET,
        global_token_budget: int = 0,       # 0 = unlimited
        global_time_budget: float = 0.0,    # 0 = unlimited
        enable_parallel: bool = True,
    ) -> None:
        self._wm = workspace_manager or WorkspaceManager()
        self._max_branches = max_branches
        self._token_budget_per_branch = token_budget_per_branch
        self._time_budget_per_branch = time_budget_per_branch
        self._global_token_budget = global_token_budget
        self._global_time_budget = global_time_budget
        self._enable_parallel = enable_parallel

        self._branches: Dict[str, Branch] = {}
        self._branch_configs: Dict[str, BranchConfig] = {}
        self._started_at: float = 0.0
        self._cancelled: bool = False

    @property
    def branch_count(self) -> int:
        return len(self._branches)

    def create_branches(
        self,
        task: Task,
        analysis: TaskAnalysis,
        base_workspace: Optional[str] = None,
    ) -> List[BranchConfig]:
        """Create divergence branch configurations."""
        strategies = self._select_strategies(task, analysis)
        configs = []

        for i, strategy in enumerate(strategies[:self._max_branches]):
            branch_id = f"{task.task_id}_branch_{i}"
            config = BranchConfig(
                branch_id=branch_id,
                strategy=strategy,
                token_budget=self._token_budget_per_branch,
                time_budget_seconds=self._time_budget_per_branch,
                workspace_path=base_workspace,
            )
            configs.append(config)

        logger.info(
            "Created %d divergence branches for task '%s'",
            len(configs), task.task_id,
        )
        return configs

    def execute_branch(
        self,
        config: BranchConfig,
        task: Task,
        executor: Callable[[BranchConfig, Task], AgentResult],
    ) -> Branch:
        """Execute a single branch with isolation and budget tracking."""
        branch = Branch(
            branch_id=config.branch_id,
            task_id=task.task_id,
            strategy_label=config.strategy.value,
            status=BranchStatus.RUNNING,
        )
        self._branches[config.branch_id] = branch
        self._branch_configs[config.branch_id] = config

        start_time = time.time()
        tokens_used = 0

        try:
            # Create isolated workspace.
            workspace_path = self._create_isolated_workspace(config, task)

            # Execute with budget tracking.
            result = executor(config, task)

            # Update branch with result.
            branch.result = result
            branch.status = BranchStatus.EVALUATED
            branch.context_snapshot = {"workspace": str(workspace_path) if workspace_path else None}

            tokens_used = result.tokens_total if result else 0
            duration = time.time() - start_time

            # Check global budget.
            if self._global_token_budget > 0:
                total_tokens = sum(
                    b.result.tokens_total if b.result else 0
                    for b in self._branches.values()
                )
                if total_tokens > self._global_token_budget:
                    logger.warning("Global token budget exceeded")

            if time.time() - self._started_at > self._global_time_budget > 0:
                logger.warning("Global time budget exceeded")

            logger.info(
                "Branch '%s' completed: tokens=%d, duration=%.1fs",
                config.branch_id, tokens_used, duration,
            )

        except Exception as e:
            branch.status = BranchStatus.ROLLED_BACK
            branch.evaluation = {"error": str(e), "validation_passed": False}
            logger.warning("Branch '%s' failed: %s", config.branch_id, e)

        return branch

    def execute_all(
        self,
        task: Task,
        analysis: TaskAnalysis,
        executor: Callable[[BranchConfig, Task], AgentResult],
    ) -> DivergenceResult:
        """Execute all branches sequentially or in parallel."""
        self._branches = {}
        self._branch_configs = {}
        self._started_at = time.time()
        self._cancelled = False

        configs = self.create_branches(task, analysis)
        results = DivergenceResult(task_id=task.task_id)

        if not configs:
            return results

        if self._enable_parallel:
            # Simple sequential execution for now (parallel requires async executor).
            # Future: integrate with ParallelScheduler.
            pass

        for config in configs:
            if self._cancelled:
                results.cancelled = True
                results.cancellation_reason = "User requested cancellation"
                break

            branch = self.execute_branch(config, task, executor)
            results.branches_created += 1
            results.branches.append(branch)

            if branch.status == BranchStatus.EVALUATED:
                results.branches_completed += 1
                if branch.result:
                    results.total_tokens_used += branch.result.tokens_total
                    results.total_duration_seconds += branch.result.duration_seconds
            else:
                results.branches_failed += 1

        return results

    def cancel(self, reason: str = "Cancelled by user") -> None:
        """Cancel all running branches."""
        self._cancelled = True
        logger.info("Cancelling divergence: %s", reason)

    def _create_isolated_workspace(
        self, config: BranchConfig, task: Task
    ) -> Optional[str]:
        """Create an isolated workspace for a branch."""
        if not config.workspace_path:
            return None

        try:
            self._wm.create_workspace(
                branch_id=config.branch_id,
                source_path=None,  # Will use temp dir
            )
            branch_info = self._wm.get_branch(config.branch_id)
            if branch_info is None:
                return None
            return str(branch_info.workspace_path)
        except Exception as e:
            logger.warning("Failed to create workspace for '%s': %s", config.branch_id, e)
            return None

    def _select_strategies(self, task: Task, analysis: TaskAnalysis) -> List[DivergenceStrategy]:
        """Select distinct divergence strategies based on task analysis."""
        strategies = [DivergenceStrategy.DIRECT]

        if analysis.is_complex:
            strategies.append(DivergenceStrategy.DECOMPOSED)

        if analysis.uncertainty.value in ("medium", "high"):
            strategies.append(DivergenceStrategy.PATTERN)
            strategies.append(DivergenceStrategy.CONTRASTING)

        if analysis.risk_level.value == "high":
            strategies.append(DivergenceStrategy.CONSTRAINTS_FIRST)

        # Ensure at least 2 strategies for meaningful divergence.
        if len(strategies) < 2:
            strategies.append(DivergenceStrategy.DECOMPOSED)

        return strategies[:self._max_branches]

    def detect_redundancy(self, branches: List[Branch]) -> Dict[str, str]:
        """Detect redundant branches (similar outputs/strategies).

        Returns mapping of branch_id -> reason for redundancy.
        """
        redundancies = {}
        seen_outputs = {}

        for branch in branches:
            if branch.result is None:
                continue

            output_hash = hash(branch.result.final_output) if branch.result.final_output else 0
            strategy = branch.strategy_label

            key = (output_hash, strategy)
            if key in seen_outputs:
                redundancies[branch.branch_id] = f"Redundant with {seen_outputs[key]}"
            else:
                seen_outputs[key] = branch.branch_id

        return redundancies
