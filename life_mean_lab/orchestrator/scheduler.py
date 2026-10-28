"""ParallelScheduler — executes independent tasks concurrently.

Respects task dependencies, resource constraints, timeouts, cancellation, and
global token budgets. Does NOT parallelize two models if their combined memory
needs exceed available resources.

Design rules:
  - Dependency graph is resolved before execution (topological sort).
  - Concurrency is bounded by available VRAM/RAM, not just CPU cores.
  - Timeouts are per-task; cancelled tasks release their resources immediately.
  - Global token budget is enforced across all concurrent tasks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("Life_mean.Orchestrator.Scheduler")


@dataclass
class TaskDependency:
    """A task with its dependencies and execution metadata."""
    task_id: str
    description: str
    # IDs of tasks that must complete before this one.
    depends_on: List[str] = field(default_factory=list)
    # Resource requirements (estimated).
    estimated_vram_mb: int = 0
    estimated_ram_mb: int = 0
    estimated_tokens: int = 4096
    timeout_seconds: float = 120.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Outcome of executing a scheduled task."""
    task_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    tokens_consumed: int = 0
    duration_seconds: float = 0.0
    model_used: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ParallelScheduler:
    """Executes independent tasks concurrently within resource limits."""

    def __init__(
        self,
        max_concurrency: int = 4,
        global_vram_mb: int = 0,       # 0 = unlimited
        global_ram_mb: int = 0,         # 0 = unlimited
        global_token_budget: int = 0,   # 0 = unlimited
        default_timeout: float = 120.0,
    ) -> None:
        self.max_concurrency = max_concurrency
        self.global_vram_mb = global_vram_mb
        self.global_ram_mb = global_ram_mb
        self.global_token_budget = global_token_budget
        self.default_timeout = default_timeout

        self._running_tokens: int = 0
        self._running_vram: int = 0
        self._running_ram: int = 0
        self._completed: Set[str] = set()
        self._results: Dict[str, TaskResult] = {}
        self._cancelled: Set[str] = set()
        self._active_task_ids: Set[str] = set()

    @property
    def available_vram(self) -> float:
        if self.global_vram_mb <= 0:
            return float("inf")
        return self.global_vram_mb - self._running_vram

    @property
    def available_ram(self) -> float:
        if self.global_ram_mb <= 0:
            return float("inf")
        return self.global_ram_mb - self._running_ram

    @property
    def available_tokens(self) -> float:
        if self.global_token_budget <= 0:
            return float("inf")
        return self.global_token_budget - self._running_tokens

    @property
    def active_count(self) -> int:
        return len(self._results) + sum(1 for _ in asyncio.all_tasks() if not _.done())

    async def execute(
        self,
        tasks: List[TaskDependency],
        executor: Callable[[TaskDependency], Any],
    ) -> Dict[str, TaskResult]:
        """Execute tasks respecting dependencies and resource constraints.

        Args:
            tasks: List of tasks to execute.
            executor: Async callable(task) -> result.

        Returns:
            Mapping of task_id -> TaskResult.
        """
        # Build dependency graph.
        task_map = {t.task_id: t for t in tasks}
        pending = set(task_map.keys())
        self._completed = set()
        self._results = {}
        self._cancelled = set()
        self._running_tokens = 0
        self._running_vram = 0
        self._running_ram = 0
        self._active_task_ids = set()

        # Topological sort to establish execution order for ready tasks.
        ready = self._find_ready(task_map, pending)

        while pending or self._active_tasks():
            # Launch ready tasks that fit within resources.
            launched = 0
            for task_id in list(ready):
                if task_id not in pending:
                    continue
                task = task_map[task_id]
                if self._can_run(task):
                    asyncio.create_task(self._run_task(task, executor))
                    self._active_task_ids.add(task_id)
                    launched += 1
                    pending.discard(task_id)
                    ready.discard(task_id)
                    if launched >= self.max_concurrency:
                        break

            # Wait for at least one task to complete or timeout.
            if not self._active_tasks() and pending:
                # No active tasks but pending remain — check for unresolvable deps.
                stuck = [t for t in pending if not self._is_resolvable(t, task_map)]
                if stuck:
                    logger.warning("Stuck tasks (unresolvable dependencies): %s", stuck)
                    for sid in stuck:
                        self._results[sid] = TaskResult(
                            task_id=sid, success=False,
                            error="Unresolvable dependencies",
                        )
                        pending.discard(sid)
                # Check if any ready tasks are stuck due to resources.
                still_ready = [t for t in ready if t in pending]
                if still_ready and not self._active_tasks():
                    # Force-complete stuck tasks as failed.
                    logger.warning("Tasks stuck due to resource constraints: %s", still_ready)
                    for sid in still_ready:
                        self._results[sid] = TaskResult(
                            task_id=sid, success=False,
                            error="Resource constraint",
                        )
                        pending.discard(sid)
                ready = self._find_ready(task_map, pending)
            else:
                await asyncio.sleep(0.01)

        return dict(self._results)

    async def _run_task(self, task: TaskDependency, executor: Callable) -> None:
        """Run a single task with timeout and resource tracking."""
        start = time.time()
        try:
            # Reserve resources.
            self._running_tokens += task.estimated_tokens
            self._running_vram += task.estimated_vram_mb
            self._running_ram += task.estimated_ram_mb

            result = await asyncio.wait_for(
                executor(task),
                timeout=min(task.timeout_seconds, self.default_timeout) if self.default_timeout > 0 else task.timeout_seconds,
            )
            duration = time.time() - start
            self._completed.add(task.task_id)
            self._active_task_ids.discard(task.task_id)
            self._results[task.task_id] = TaskResult(
                task_id=task.task_id,
                success=True,
                output=result,
                duration_seconds=duration,
                metadata=task.metadata,
            )
        except asyncio.TimeoutError:
            duration = time.time() - start
            self._completed.add(task.task_id)
            self._active_task_ids.discard(task.task_id)
            self._results[task.task_id] = TaskResult(
                task_id=task.task_id, success=False,
                error="Timeout", duration_seconds=duration,
            )
        except Exception as e:
            duration = time.time() - start
            self._completed.add(task.task_id)
            self._active_task_ids.discard(task.task_id)
            self._results[task.task_id] = TaskResult(
                task_id=task.task_id, success=False,
                error=str(e), duration_seconds=duration,
            )
        finally:
            # Release resources.
            self._running_tokens -= task.estimated_tokens
            self._running_vram -= task.estimated_vram_mb
            self._running_ram -= task.estimated_ram_mb

    def _can_run(self, task: TaskDependency) -> bool:
        """Check if a task can run given current resource constraints."""
        if self.available_vram != float("inf") and task.estimated_vram_mb > self.available_vram:
            return False
        if self.available_ram != float("inf") and task.estimated_ram_mb > self.available_ram:
            return False
        if self.available_tokens != float("inf") and task.estimated_tokens > self.available_tokens:
            return False
        return True

    def _find_ready(self, task_map: Dict[str, TaskDependency],
                    pending: Set[str]) -> Set[str]:
        """Find tasks whose dependencies are all satisfied."""
        ready = set()
        for tid in pending:
            task = task_map[tid]
            if all(dep in self._completed for dep in task.depends_on):
                ready.add(tid)
        return ready

    def _is_resolvable(self, task_id: str, task_map: Dict[str, TaskDependency]) -> bool:
        """Check if a pending task can ever become ready."""
        # If it has no dependencies, it's resolvable.
        task = task_map[task_id]
        if not task.depends_on:
            return True
        # Check if any dependency is stuck (not completed and not in pending).
        for dep in task.depends_on:
            if dep not in self._completed and dep not in task_map:
                return False  # Dependency was cancelled or never existed.
        return True

    def _active_tasks(self) -> int:
        """Count currently running tasks tracked by this scheduler."""
        return len(self._active_task_ids)

    def cancel(self, task_id: str) -> None:
        """Mark a task as cancelled (best-effort; actual cancellation depends on executor)."""
        self._cancelled.add(task_id)
        logger.info("Cancelled task '%s'", task_id)
