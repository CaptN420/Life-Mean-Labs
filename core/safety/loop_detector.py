"""Loop detection for LIFE_MEAN.

Detects circular fallbacks, excessive retries, and recursive patterns.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LoopSeverity(str, Enum):
    """Severity of a detected loop."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LoopEvent:
    """Event emitted when a loop is detected."""
    event: str = "LOOP_DETECTED"
    severity: LoopSeverity = LoopSeverity.WARNING
    component: str = ""
    worker: str = ""
    task_id: str = ""
    attempts: int = 0
    progress_detected: bool = False
    action: str = "EXECUTION_PAUSED"
    fallback: str = "REVIEW_REQUIRED"
    trace_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "severity": self.severity.value,
            "component": self.component,
            "worker": self.worker,
            "task_id": self.task_id,
            "attempts": self.attempts,
            "progress_detected": self.progress_detected,
            "action": self.action,
            "fallback": self.fallback,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class LoopDetector:
    """Detects loops in execution patterns."""

    def __init__(self, max_attempts: int = 5, progress_threshold: float = 0.01):
        self._max_attempts = max_attempts
        self._progress_threshold = progress_threshold

        # Track per task
        self._task_calls: Dict[str, List[Dict[str, Any]]] = {}
        self._task_results: Dict[str, List[Any]] = {}
        self._task_timestamps: Dict[str, List[float]] = {}

        # Global deduplication
        self._recent_events: List[LoopEvent] = []
        self._dedup_window: float = 60.0  # seconds

    def record_call(
        self,
        task_id: str,
        worker: str,
        result: Any,
        execution_ms: float = 0.0,
    ) -> Optional[LoopEvent]:
        """Record a call and check for loops."""
        now = time.time()

        if task_id not in self._task_calls:
            self._task_calls[task_id] = []
            self._task_results[task_id] = []
            self._task_timestamps[task_id] = []

        self._task_calls[task_id].append({
            "worker": worker,
            "timestamp": now,
            "execution_ms": execution_ms,
        })
        self._task_results[task_id].append(result)
        self._task_timestamps[task_id].append(now)

        # Check for loop
        return self._detect_loop(task_id)

    def _detect_loop(self, task_id: str) -> Optional[LoopEvent]:
        """Detect if a loop exists for the given task."""
        calls = self._task_calls.get(task_id, [])
        results = self._task_results.get(task_id, [])
        timestamps = self._task_timestamps.get(task_id, [])

        if len(calls) < 2:
            return None

        # Check attempt count
        if len(calls) >= self._max_attempts:
            return LoopEvent(
                severity=LoopSeverity.WARNING,
                component="loop_detector",
                worker=calls[-1]["worker"],
                task_id=task_id,
                attempts=len(calls),
                progress_detected=False,
                trace_id=str(uuid.uuid4())[:8],
            )

        # Check for identical results (stuck pattern)
        if len(results) >= 3:
            last_result = results[-1]
            prev_results = results[-3:-1]
            if all(r == last_result for r in prev_results) and last_result is not None:
                return LoopEvent(
                    severity=LoopSeverity.WARNING,
                    component="loop_detector",
                    worker=calls[-1]["worker"],
                    task_id=task_id,
                    attempts=len(calls),
                    progress_detected=False,
                    trace_id=str(uuid.uuid4())[:8],
                )

        # Check for rapid repeated calls (timeout loop)
        if len(timestamps) >= 3:
            recent = timestamps[-3:]
            if recent[-1] - recent[0] < 0.1:  # Less than 100ms for 3 calls
                return LoopEvent(
                    severity=LoopSeverity.ERROR,
                    component="loop_detector",
                    worker=calls[-1]["worker"],
                    task_id=task_id,
                    attempts=len(calls),
                    progress_detected=False,
                    trace_id=str(uuid.uuid4())[:8],
                )

        return None

    def check_progress(
        self,
        task_id: str,
        current_value: Any,
        previous_values: List[Any],
    ) -> bool:
        """Check if progress is being made."""
        if not previous_values:
            return True

        # Try to compare values
        try:
            if isinstance(current_value, (int, float)):
                changes = [abs(current_value - v) for v in previous_values]
                return any(c > self._progress_threshold for c in changes)
        except TypeError:
            pass

        # Fallback: check for any difference
        return current_value not in previous_values

    def reset_task(self, task_id: str) -> None:
        """Reset tracking for a task."""
        self._task_calls.pop(task_id, None)
        self._task_results.pop(task_id, None)
        self._task_timestamps.pop(task_id, None)

    def get_stats(self) -> Dict[str, Any]:
        """Get loop detection statistics."""
        return {
            "tracked_tasks": len(self._task_calls),
            "max_attempts_threshold": self._max_attempts,
        }
