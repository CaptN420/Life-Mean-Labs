"""MetacognitiveBudgetController — adaptive resource allocation and monitoring.

Manages global and per-component budgets for tokens, time, and memory.
Supports dynamic reallocation, progress monitoring, early stopping, and
redundant call reduction.

Design rules:
  - Never exceed global budget limits.
  - Track real vs estimated consumption separately.
  - Preserve verification reserves.
  - Log all transfers for auditability.
  - Do not confuse LLM semantic scores with verified progress.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import OrchestrationTrace, Task
from .task_analyzer import TaskAnalysis

logger = logging.getLogger("Life_mean.Orchestrator.BudgetController")


# ── Budget types ──────────────────────────────────────────────────────────────


class BudgetType(str, enum.Enum):
    TOKENS = "tokens"
    TIME = "time"
    RAM = "ram"
    VRAM = "vram"


class AllocationStage(str, enum.Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    RESERVE = "reserve"


# ── Budget dataclasses ────────────────────────────────────────────────────────


@dataclass
class BudgetAllocation:
    """Budget allocation for a specific stage or component."""
    stage: AllocationStage
    allocated: float  # tokens, seconds, or MB
    used: float = 0.0
    estimated: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.allocated - self.used)

    @property
    def utilization(self) -> float:
        if self.allocated == 0:
            return 0.0
        return self.used / self.allocated


@dataclass
class BudgetSnapshot:
    """Point-in-time snapshot of budget state."""
    timestamp: float = field(default_factory=time.time)
    global_tokens_allocated: int = 0
    global_tokens_used: int = 0
    global_time_allocated: float = 0.0
    global_time_used: float = 0.0
    stage_allocations: Dict[str, BudgetAllocation] = field(default_factory=dict)
    branch_budgets: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class TransferRecord:
    """Records a budget transfer between stages."""
    from_stage: str
    to_stage: str
    amount: float
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProgressSignal:
    """Verified progress indicator."""
    signal_type: str  # "tests_passed", "constraints_satisfied", etc.
    value: float
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # branch_id or component


@dataclass
class StagnationRecord:
    """Tracks lack of progress for early stopping."""
    last_progress_timestamp: float = 0.0
    consecutive_no_progress: int = 0
    best_result_so_far: Optional[str] = None


# ── MetacognitiveBudgetController ─────────────────────────────────────────────


class MetacognitiveBudgetController:
    """Central budget controller for adaptive orchestration.

    Manages global and per-component budgets with dynamic reallocation,
    progress monitoring, and early stopping capabilities.
    """

    # Default allocation percentages (sum must <= 1.0).
    DEFAULT_SIMPLE_ALLOCATION = {
        AllocationStage.EXECUTION: 0.80,
        AllocationStage.VERIFICATION: 0.20,
    }
    DEFAULT_COMPLEX_ALLOCATION = {
        AllocationStage.PLANNING: 0.20,
        AllocationStage.EXECUTION: 0.45,
        AllocationStage.VERIFICATION: 0.25,
        AllocationStage.RESERVE: 0.10,
    }

    # Early stopping thresholds.
    DEFAULT_NO_PROGRESS_STALLS = 3
    DEFAULT_MIN_VERIFICATION_THRESHOLD = 0.5

    def __init__(
        self,
        global_token_budget: int = 16384,
        global_time_budget_seconds: float = 300.0,
        global_ram_mb: int = 0,       # 0 = unlimited
        global_vram_mb: int = 0,      # 0 = unlimited
        no_progress_stalls: int = DEFAULT_NO_PROGRESS_STALLS,
        min_verification_threshold: float = DEFAULT_MIN_VERIFICATION_THRESHOLD,
        enable_early_stopping: bool = True,
    ) -> None:
        self._global_token_budget = global_token_budget
        self._global_time_budget_seconds = global_time_budget_seconds
        self._global_ram_mb = global_ram_mb
        self._global_vram_mb = global_vram_mb

        self._no_progress_stalls = no_progress_stalls
        self._min_verification_threshold = min_verification_threshold
        self._enable_early_stopping = enable_early_stopping

        # Current consumption.
        self._tokens_used: int = 0
        self._time_used_seconds: float = 0.0
        self._ram_used_mb: int = 0
        self._vram_used_mb: int = 0

        # Stage allocations.
        self._allocations: Dict[AllocationStage, BudgetAllocation] = {
            stage: BudgetAllocation(stage=stage, allocated=0.0)
            for stage in AllocationStage
        }

        # Per-branch budgets.
        self._branch_budgets: Dict[str, Dict[str, float]] = {}

        # Transfer history.
        self._transfers: List[TransferRecord] = []

        # Progress tracking.
        self._progress_signals: List[ProgressSignal] = []
        self._stagnation = StagnationRecord()

        # Cache for redundant call reduction.
        self._result_cache: Dict[str, Any] = {}
        self._cache_invalidations: int = 0

        # Start time.
        self._started_at: float = time.time()

    # ── Budget properties ────────────────────────────────────────────────────

    @property
    def tokens_remaining(self) -> int:
        return max(0, self._global_token_budget - self._tokens_used)

    @property
    def time_remaining_seconds(self) -> float:
        return max(0.0, self._global_time_budget_seconds - self._time_used_seconds)

    @property
    def tokens_utilization(self) -> float:
        if self._global_token_budget == 0:
            return 0.0
        return self._tokens_used / self._global_token_budget

    @property
    def time_utilization(self) -> float:
        if self._global_time_budget_seconds == 0:
            return 0.0
        return self._time_used_seconds / self._global_time_budget_seconds

    # ── Allocation ───────────────────────────────────────────────────────────

    def allocate_stage(
        self,
        stage: AllocationStage,
        task_analysis: TaskAnalysis,
        num_branches: int = 1,
    ) -> None:
        """Allocate budget to a stage based on task analysis."""
        percentages = self._get_allocation_percentages(task_analysis)

        # Allocate tokens.
        if self._global_token_budget > 0:
            allocated_tokens = int(self._global_token_budget * percentages.get(stage, 0.2))
            self._allocations[stage].allocated = allocated_tokens

        # Allocate time (separate from tokens).
        if self._global_time_budget_seconds > 0:
            allocated_time = self._global_time_budget_seconds * percentages.get(stage, 0.2)
            # Store time allocation in a separate dict to avoid confusion.
            if not hasattr(self, '_time_allocations'):
                self._time_allocations = {}
            self._time_allocations[stage] = allocated_time

        # Distribute branch budgets.
        if num_branches > 1 and self._global_token_budget > 0:
            per_branch = (
                self._allocations[AllocationStage.EXECUTION].allocated // max(1, num_branches)
            )
            for i in range(num_branches):
                self._branch_budgets[f"branch_{i}"] = {"tokens": per_branch}

        logger.info("Allocated stage '%s': tokens=%d", stage.value, self._allocations[stage].allocated)

    def _get_allocation_percentages(self, analysis: TaskAnalysis) -> Dict[AllocationStage, float]:
        """Get allocation percentages based on task complexity."""
        if analysis.complexity >= 4:
            return self.DEFAULT_COMPLEX_ALLOCATION
        return self.DEFAULT_SIMPLE_ALLOCATION

    # ── Consumption tracking ─────────────────────────────────────────────────

    def record_token_consumption(self, tokens: int, stage: Optional[AllocationStage] = None) -> bool:
        """Record token consumption. Returns False if budget exceeded."""
        if self._global_token_budget > 0 and self._tokens_used + tokens > self._global_token_budget:
            logger.warning("Token budget exceeded: %d used vs %d budget", self._tokens_used, self._global_token_budget)
            return False

        self._tokens_used += tokens
        if stage and stage in self._allocations:
            self._allocations[stage].used += tokens
        return True

    def record_time_consumption(self, seconds: float, stage: Optional[AllocationStage] = None) -> None:
        """Record time consumption."""
        self._time_used_seconds += seconds
        if stage and stage in self._allocations:
            self._allocations[stage].used += seconds

    def record_ram_consumption(self, mb: int) -> bool:
        """Record RAM consumption. Returns False if limit exceeded."""
        if self._global_ram_mb > 0 and self._ram_used_mb + mb > self._global_ram_mb:
            return False
        self._ram_used_mb += mb
        return True

    def record_vram_consumption(self, mb: int) -> bool:
        """Record VRAM consumption. Returns False if limit exceeded."""
        if self._global_vram_mb > 0 and self._vram_used_mb + mb > self._global_vram_mb:
            return False
        self._vram_used_mb += mb
        return True

    # ── Reallocation ─────────────────────────────────────────────────────────

    def reallocate(
        self,
        from_stage: AllocationStage,
        to_stage: AllocationStage,
        amount: float,
        reason: str,
    ) -> bool:
        """Reallocate budget between stages."""
        if from_stage not in self._allocations or to_stage not in self._allocations:
            logger.warning("Invalid stage for reallocation: %s -> %s", from_stage, to_stage)
            return False

        from_alloc = self._allocations[from_stage]
        to_alloc = self._allocations[to_stage]

        if from_alloc.remaining < amount:
            logger.warning("Insufficient budget in %s for reallocation", from_stage)
            return False

        # Perform transfer.
        from_alloc.used -= amount
        to_alloc.allocated += amount
        to_alloc.used += amount  # Assume immediately used.

        self._transfers.append(TransferRecord(
            from_stage=from_stage.value,
            to_stage=to_stage.value,
            amount=amount,
            reason=reason,
        ))

        logger.info("Reallocated %.1f from %s to %s: %s", amount, from_stage.value, to_stage.value, reason)
        return True

    def release_branch_budget(self, branch_id: str) -> float:
        """Release unused budget from a completed/failed branch."""
        released = 0.0
        if branch_id in self._branch_budgets:
            budget = self._branch_budgets.pop(branch_id)
            released = budget.get("tokens", 0)
            logger.info("Released %.0f tokens from branch '%s'", released, branch_id)
        return released

    # ── Progress monitoring ──────────────────────────────────────────────────

    def record_progress(self, signal_type: str, value: float, source: str = "") -> None:
        """Record a verified progress signal."""
        self._progress_signals.append(ProgressSignal(
            signal_type=signal_type,
            value=value,
            source=source,
        ))
        self._stagnation.last_progress_timestamp = time.time()
        self._stagnation.consecutive_no_progress = 0

    def check_stagnation(self) -> bool:
        """Check if execution is stagnant (no progress for N attempts)."""
        if not self._enable_early_stopping:
            return False

        # Check consecutive no-progress.
        if self._stagnation.consecutive_no_progress >= self._no_progress_stalls:
            logger.info("Stagnation detected: %d consecutive stalls", self._stagnation.consecutive_no_progress)
            return True

        # Check time stagnation (no progress in last 30s).
        if time.time() - self._stagnation.last_progress_timestamp > 30.0:
            self._stagnation.consecutive_no_progress += 1

        return False

    def increment_no_progress(self) -> None:
        """Increment the no-progress counter."""
        self._stagnation.consecutive_no_progress += 1

    # ── Early stopping ───────────────────────────────────────────────────────

    def should_stop(self, reason: str = "") -> tuple[bool, str]:
        """Check if execution should stop based on budget or progress."""
        if not self._enable_early_stopping:
            return False, ""

        # Check budget exhaustion.
        if self._global_token_budget > 0 and self._tokens_used >= self._global_token_budget:
            return True, "Token budget exhausted"

        if self._global_time_budget_seconds > 0 and self._time_used_seconds >= self._global_time_budget_seconds:
            return True, "Time budget exhausted"

        # Check stagnation.
        if self.check_stagnation():
            return True, "No progress detected"

        return False, reason

    # ── Redundant call reduction ─────────────────────────────────────────────

    def compute_fingerprint(self, task: Task, config: Dict[str, Any]) -> str:
        """Compute a fingerprint for context/configuration deduplication."""
        payload = {
            "task_id": task.task_id,
            "description": task.description,
            "config": json.dumps(config, sort_keys=True, ensure_ascii=False),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def get_cached_result(self, fingerprint: str) -> Optional[Any]:
        """Get a cached result if available and valid."""
        return self._result_cache.get(fingerprint)

    def store_cached_result(self, fingerprint: str, result: Any) -> None:
        """Store a result in the cache."""
        self._result_cache[fingerprint] = result

    def invalidate_cache(self, pattern: Optional[str] = None) -> int:
        """Invalidate cached results matching a pattern."""
        if pattern is None:
            count = len(self._result_cache)
            self._result_cache.clear()
            self._cache_invalidations += count
            return count

        keys_to_remove = [k for k in self._result_cache if pattern in k]
        for k in keys_to_remove:
            del self._result_cache[k]
        self._cache_invalidations += len(keys_to_remove)
        return len(keys_to_remove)

    # ── Snapshot and trace ───────────────────────────────────────────────────

    def take_snapshot(self) -> BudgetSnapshot:
        """Take a point-in-time snapshot of budget state."""
        return BudgetSnapshot(
            timestamp=time.time(),
            global_tokens_allocated=self._global_token_budget,
            global_tokens_used=self._tokens_used,
            global_time_allocated=self._global_time_budget_seconds,
            global_time_used=self._time_used_seconds,
            stage_allocations={
                stage.value: {
                    "allocated": alloc.allocated,
                    "used": alloc.used,
                    "utilization": alloc.utilization,
                }
                for stage, alloc in self._allocations.items()
            },
            branch_budgets=dict(self._branch_budgets),
        )

    def extend_trace(self, trace: OrchestrationTrace) -> None:
        """Extend an orchestration trace with budget information."""
        snapshot = self.take_snapshot()
        trace.metadata["budget"] = {
            "global_tokens_allocated": snapshot.global_tokens_allocated,
            "global_tokens_used": snapshot.global_tokens_used,
            "global_time_allocated_seconds": snapshot.global_time_allocated,
            "global_time_used_seconds": snapshot.global_time_used,
            "stages": {
                stage: {
                    "allocated": alloc.allocated,
                    "used": alloc.used,
                    "utilization": round(alloc.utilization, 3),
                }
                for stage, alloc in self._allocations.items()
            },
            "transfers": [
                {
                    "from": t.from_stage,
                    "to": t.to_stage,
                    "amount": t.amount,
                    "reason": t.reason,
                }
                for t in self._transfers[-10:]
            ],
        }

    # ── Utilities ────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all budget state."""
        self._tokens_used = 0
        self._time_used_seconds = 0.0
        self._ram_used_mb = 0
        self._vram_used_mb = 0
        self._transfers.clear()
        self._progress_signals.clear()
        self._stagnation = StagnationRecord()
        self._started_at = time.time()
        for stage in self._allocations:
            self._allocations[stage].used = 0.0

    def get_summary(self) -> Dict[str, Any]:
        """Return a compact summary of budget state."""
        return {
            "tokens": {
                "allocated": self._global_token_budget,
                "used": self._tokens_used,
                "remaining": self.tokens_remaining,
                "utilization": round(self.tokens_utilization, 3),
            },
            "time": {
                "allocated_seconds": self._global_time_budget_seconds,
                "used_seconds": round(self._time_used_seconds, 2),
                "remaining_seconds": round(self.time_remaining_seconds, 2),
                "utilization": round(self.time_utilization, 3),
            },
            "transfers_count": len(self._transfers),
            "progress_signals_count": len(self._progress_signals),
            "stagnation_stalls": self._stagnation.consecutive_no_progress,
        }
