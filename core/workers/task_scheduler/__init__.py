"""Task Scheduler — Deterministic event-driven task execution engine.

Executes tasks respecting dependencies, priorities, and failure handling.
Uses a virtual clock (no time.sleep) and supports parallel execution
(up to max_workers simultaneous tasks).
"""
from __future__ import annotations

import json
import heapq
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    """A task with dependencies, priority, and duration."""

    id: str
    duration: int
    priority: int
    depends_on: List[str] = field(default_factory=list)
    max_retries: int = 0  # bonus: extra attempts after first failure
    retry_delays: List[int] = field(default_factory=list)  # virtual delays between retries

    def __post_init__(self):
        for dep in self.depends_on:
            if not isinstance(dep, str):
                raise TypeError(f"Task {self.id}: dependency must be a string, got {type(dep)}")


@dataclass
class TaskEvent:
    """An event in the task execution timeline."""

    time: int
    event_type: str  # "started", "completed", "failed", "retry"
    task_id: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of a single task execution."""

    task_id: str
    status: str
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    duration: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1


class TaskSchedulerError(Exception):
    """Base exception for scheduler errors."""


class CircularDependencyError(TaskSchedulerError):
    """Raised when circular dependencies are detected."""


class ValidationError(TaskSchedulerError):
    """Raised when task validation fails."""


class TaskScheduler:
    """Event-driven task scheduler with virtual clock.

    Executes up to max_workers tasks in parallel, selecting by priority
    (descending) then alphabetically. Handles failures by blocking
    dependents while allowing independent tasks to proceed.
    """

    def __init__(self, max_workers: int = 2):
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self.max_workers = max_workers
        self._tasks: Dict[str, Task] = {}
        self._results: Dict[str, TaskResult] = {}
        self._events: List[TaskEvent] = []
        self._failed_tasks: Set[str] = set()  # permanently failed tasks

    def add_task(self, task: Task) -> None:
        """Register a task. Raises ValidationError on duplicate id."""
        if task.id in self._tasks:
            raise ValidationError(f"Duplicate task id: {task.id}")
        self._tasks[task.id] = task

    def validate(self) -> None:
        """Validate tasks: unique ids, existing dependencies, positive durations.

        Also detects circular dependencies via DFS.
        """
        # Check unique IDs (already enforced by add_task, but be safe)
        ids = set(self._tasks.keys())
        if len(ids) != len(self._tasks):
            raise ValidationError("Duplicate task ids detected")

        # Check dependencies exist
        for task in self._tasks.values():
            for dep in task.depends_on:
                if dep not in ids:
                    raise ValidationError(
                        f"Task {task.id}: dependency '{dep}' does not exist"
                    )
            if task.duration < 0:
                raise ValidationError(f"Task {task.id}: duration must be non-negative")

        # Detect circular dependencies via DFS
        self._detect_cycles()

    def _detect_cycles(self) -> None:
        """Detect cycles using DFS. Raises CircularDependencyError if found."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in self._tasks}

        def dfs(tid: str) -> bool:
            color[tid] = GRAY
            for dep in self._tasks[tid].depends_on:
                if color[dep] == GRAY:
                    return True  # cycle detected
                if color[dep] == WHITE and dfs(dep):
                    return True
            color[tid] = BLACK
            return False

        for tid in self._tasks:
            if color[tid] == WHITE:
                if dfs(tid):
                    raise CircularDependencyError(
                        f"Circular dependency detected involving task '{tid}'"
                    )

    def run(self, failures: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Execute all tasks using a virtual clock.

        Args:
            failures: Dict mapping task_id -> attempt number at which to fail.
                      e.g. {"load": 1} fails on first attempt.

        Returns:
            Report dict with statuses, timings, and total duration.
        """
        self._results = {}
        self._events = []
        self._failed_tasks = set()

        total_tasks = len(self._tasks)
        running: Dict[str, int] = {}      # task_id -> end_time
        start_times: Dict[str, int] = {}  # task_id -> start_time
        attempts: Dict[str, int] = {}     # task_id -> attempt count
        retry_at: Dict[str, int] = {}     # task_id -> virtual time retry becomes available
        finished: Set[str] = set()         # terminal states (completed/failed/blocked)

        clock = 0

        while len(finished) < total_tasks:
            # ── 1. Resolve completions at current clock ──────────────────────
            for tid in [t for t, end in running.items() if end <= clock]:
                task = self._tasks[tid]
                self._results[tid] = TaskResult(
                    task_id=tid, status=TaskStatus.COMPLETED,
                    start_time=start_times.pop(tid, None), end_time=clock,
                    duration=task.duration, attempts=attempts.get(tid, 1),
                )
                finished.add(tid)
                self._events.append(TaskEvent(
                    time=clock, event_type="completed", task_id=tid,
                    detail={"duration": task.duration}
                ))
                del running[tid]

            # ── 2. Block dependents of failed/blocked tasks, collect available ──
            available = []
            for tid, task in self._tasks.items():
                if tid in finished or tid in running:
                    continue
                if tid in retry_at and retry_at[tid] > clock:
                    continue  # retry not yet available
                # A dependency is only satisfied if it COMPLETED. Any failed or
                # blocked dependency blocks this task (transitively).
                if any(self._results.get(dep) and self._results[dep].status
                       in (TaskStatus.FAILED, TaskStatus.BLOCKED)
                       for dep in task.depends_on):
                    self._results[tid] = TaskResult(
                        task_id=tid, status=TaskStatus.BLOCKED,
                        error="dependency failed",
                    )
                    finished.add(tid)
                    self._events.append(TaskEvent(
                        time=clock, event_type="blocked", task_id=tid,
                        detail={"reason": "dependency failed"}
                    ))
                    continue
                if all(self._results.get(dep)
                       and self._results[dep].status == TaskStatus.COMPLETED
                       for dep in task.depends_on):
                    available.append(tid)

            # Sort by priority desc, then id asc
            available.sort(key=lambda tid: (-self._tasks[tid].priority, tid))

            # ── 3. Start tasks up to max_workers, handling failures ──────────
            while len(running) < self.max_workers and available:
                tid = available.pop(0)
                task = self._tasks[tid]
                attempts[tid] = attempts.get(tid, 0) + 1
                a = attempts[tid]
                start_times[tid] = clock
                running[tid] = clock + task.duration
                self._events.append(TaskEvent(
                    time=clock, event_type="started", task_id=tid,
                    detail={"attempt": a, "priority": task.priority}
                ))

                should_fail = failures and tid in failures and a <= failures[tid]
                if should_fail:
                    if a < 1 + task.max_retries:
                        # Retry allowed: remove from running, schedule retry
                        delay = (task.retry_delays[a - 1]
                                 if a <= len(task.retry_delays) else 0)
                        del running[tid]
                        start_times.pop(tid, None)
                        retry_at[tid] = clock + delay
                        self._events.append(TaskEvent(
                            time=clock, event_type="retry", task_id=tid,
                            detail={"attempt": a, "next_attempt": a + 1, "delay": delay}
                        ))
                    else:
                        # Permanent failure
                        self._failed_tasks.add(tid)
                        self._results[tid] = TaskResult(
                            task_id=tid, status=TaskStatus.FAILED,
                            start_time=start_times.pop(tid, None), end_time=clock,
                            duration=0,
                            error=f"Simulated failure on attempt {a}", attempts=a,
                        )
                        finished.add(tid)
                        self._events.append(TaskEvent(
                            time=clock, event_type="failed", task_id=tid,
                            detail={"attempts": a, "error": "Simulated failure"}
                        ))
                        del running[tid]

            # ── 4. Advance clock to the next scheduled event ─────────────────
            # Drop stale retry entries for tasks already dispatched.
            retry_at = {t: s for t, s in retry_at.items()
                        if t not in finished and t not in running}
            running_times = [t for t in running.values()]
            future_retries = [s for s in retry_at.values() if s > clock]
            if running_times or future_retries:
                clock = min(running_times + future_retries)
            elif retry_at:
                # Retries scheduled at or before current clock: loop again to
                # pick them up (no clock advance).
                pass
            else:
                # No running tasks and no retries pending, but not all finished:
                # mark remaining as blocked (deadlock/impossible state) and stop.
                for tid in self._tasks:
                    if tid not in finished:
                        self._results[tid] = TaskResult(
                            task_id=tid, status=TaskStatus.BLOCKED,
                            error="deadlock detected",
                        )
                        finished.add(tid)
                break

        # ── Build report ─────────────────────────────────────────────────────
        report = {
            "tasks": {tid: {
                "status": res.status,
                "start_time": res.start_time,
                "end_time": res.end_time,
                "duration": res.duration,
                "attempts": res.attempts,
                "error": res.error,
            } for tid, res in self._results.items()},
            "events": [e.__dict__ for e in self._events],
            "total_duration": max((e.time for e in self._events), default=0),
        }
        return report

    def export_json(self, path: str) -> None:
        """Export the execution report as JSON."""
        report = self.run() if not self._results else {
            "tasks": {tid: {
                "status": res.status,
                "start_time": res.start_time,
                "end_time": res.end_time,
                "duration": res.duration,
                "attempts": res.attempts,
                "error": res.error,
            } for tid, res in self._results.items()},
            "events": [e.__dict__ for e in self._events],
            "total_duration": max((e.time for e in self._events), default=0),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
