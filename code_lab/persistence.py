"""Autonomous persistence layer for build→run→repair loop.

Implements an explicit state machine that continues after errors instead of
prematurely stopping. Tracks repair attempts, detects stagnation, and enforces
perseverance policies.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CodeLab.Persistence")


class PipelineState(str, Enum):
    """Explicit pipeline states for the autonomous loop."""
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    WRITING_FILES = "WRITING_FILES"
    BUILDING = "BUILDING"
    EXECUTING = "EXECUTING"
    TESTING = "TESTING"
    ANALYZING_FAILURE = "ANALYZING_FAILURE"
    REPAIRING = "REPAIRING"
    RETESTING = "RETESTING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


@dataclass
class RepairAttempt:
    """Records one repair attempt with hypothesis and outcome."""
    attempt_id: int
    hypothesis: str
    error_type: str
    error_message: str
    files_modified: List[str]
    patch_applied: str
    result_after_patch: str  # "passed", "failed", "error"
    tests_run: int
    tests_passed: int
    strategy_used: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "hypothesis": self.hypothesis,
            "error_type": self.error_type,
            "error_message": self.error_message[:500],
            "files_modified": self.files_modified,
            "patch_applied": self.patch_applied[:200],
            "result_after_patch": self.result_after_patch,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "strategy_used": self.strategy_used,
            "timestamp": self.timestamp,
        }


@dataclass
class Checkpoint:
    """Snapshot of project state before a major repair."""
    checkpoint_id: str
    timestamp: float
    files: Dict[str, str]  # rel_path -> content
    test_results: Optional[Dict[str, Any]] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "files_count": len(self.files),
            "notes": self.notes,
        }


@dataclass
class PerseverancePolicy:
    """Configurable limits for the autonomous loop."""
    max_repair_attempts: int = 30
    max_total_iterations: int = 100
    max_consecutive_identical_failures: int = 3
    max_runtime_minutes: int = 30
    max_stagnation_cycles: int = 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_repair_attempts": self.max_repair_attempts,
            "max_total_iterations": self.max_total_iterations,
            "max_consecutive_identical_failures": self.max_consecutive_identical_failures,
            "max_runtime_minutes": self.max_runtime_minutes,
            "max_stagnation_cycles": self.max_stagnation_cycles,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerseverancePolicy":
        return cls(
            max_repair_attempts=int(data.get("max_repair_attempts", 30)),
            max_total_iterations=int(data.get("max_total_iterations", 100)),
            max_consecutive_identical_failures=int(data.get("max_consecutive_identical_failures", 3)),
            max_runtime_minutes=int(data.get("max_runtime_minutes", 30)),
            max_stagnation_cycles=int(data.get("max_stagnation_cycles", 5)),
        )


class AutonomousPersistence:
    """Manages state, memory, and perseverance for the build→run→repair loop."""

    def __init__(self, run_id: str, workspace_root: Path):
        self.run_id = run_id
        self.workspace_root = workspace_root
        self.state = PipelineState.PLANNING
        self.repair_attempts: List[RepairAttempt] = []
        self.checkpoints: List[Checkpoint] = []
        self.policy = PerseverancePolicy()
        self._start_time = time.time()
        self._consecutive_failures = 0
        self._last_error_signature: Optional[str] = None
        self._stagnation_counter = 0
        self._error_history: Dict[str, List[int]] = {}  # error_type -> [attempt_ids]

        # Ensure directories exist
        (workspace_root / "checkpoints").mkdir(parents=True, exist_ok=True)
        (workspace_root / "repair_logs").mkdir(parents=True, exist_ok=True)

    @property
    def elapsed_minutes(self) -> float:
        return (time.time() - self._start_time) / 60.0

    @property
    def total_repair_attempts(self) -> int:
        return len(self.repair_attempts)

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def can_continue(self) -> bool:
        """Check if the loop should continue based on policy."""
        if self.state == PipelineState.STOPPED:
            return False
        if self.state == PipelineState.COMPLETED:
            return False

        # Check time limit
        if self.elapsed_minutes >= self.policy.max_runtime_minutes:
            logger.info("Max runtime reached (%.1f min)", self.elapsed_minutes)
            return False

        # Check max iterations
        if self.total_repair_attempts >= self.policy.max_total_iterations:
            logger.info("Max iterations reached (%d)", self.policy.max_total_iterations)
            return False

        # Check consecutive identical failures
        if self._consecutive_failures >= self.policy.max_consecutive_identical_failures:
            logger.info("Too many consecutive identical failures (%d)",
                       self._consecutive_failures)
            return False

        # Check stagnation
        if self._stagnation_counter >= self.policy.max_stagnation_cycles:
            logger.info("Stagnation detected, changing strategy")
            return False

        return True

    def should_change_strategy(self) -> bool:
        """Detect if we're stuck and need a different approach."""
        if len(self.repair_attempts) < 3:
            return False

        # Check for repeated identical errors
        recent_errors = [a.error_type for a in self.repair_attempts[-5:]]
        if len(set(recent_errors)) == 1 and recent_errors[0] != "":
            self._stagnation_counter += 1
            return True

        return False

    def record_repair_attempt(self, attempt: RepairAttempt) -> None:
        """Record a repair attempt and update state."""
        self.repair_attempts.append(attempt)

        if attempt.result_after_patch == "failed":
            self._consecutive_failures += 1
            self._last_error_signature = attempt.error_type
            # Track error history
            if attempt.error_type not in self._error_history:
                self._error_history[attempt.error_type] = []
            self._error_history[attempt.error_type].append(attempt.attempt_id)
        else:
            self._consecutive_failures = 0
            self._stagnation_counter = 0

    def record_checkpoint(self, files: Dict[str, str], notes: str = "") -> str:
        """Save a checkpoint before a major repair."""
        cp_id = f"cp_{len(self.checkpoints):03d}_{int(time.time())}"
        cp = Checkpoint(
            checkpoint_id=cp_id,
            timestamp=time.time(),
            files=files,
            notes=notes,
        )
        self.checkpoints.append(cp)

        # Persist checkpoint
        cp_path = self.workspace_root / "checkpoints" / f"{cp_id}.json"
        cp_path.write_text(json.dumps(cp.to_dict(), indent=2), encoding="utf-8")

        logger.info("Checkpoint saved: %s", cp_id)
        return cp_id

    def rollback_to_checkpoint(self, checkpoint_id: Optional[str] = None) -> bool:
        """Rollback to a previous checkpoint."""
        if not self.checkpoints:
            return False

        # Find the checkpoint
        cp = None
        if checkpoint_id:
            cp = next((c for c in self.checkpoints if c.checkpoint_id == checkpoint_id), None)
        else:
            # Use the last checkpoint
            cp = self.checkpoints[-1] if self.checkpoints else None

        if cp is None:
            return False

        # Restore files
        try:
            for rel_path, content in cp.files.items():
                target = self.workspace_root / "workspace" / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            logger.info("Rolled back to checkpoint %s", cp.checkpoint_id)
            return True
        except Exception as e:
            logger.error("Rollback failed: %s", e)
            return False

    def get_error_pattern(self, error_message: str) -> str:
        """Extract a signature from an error for deduplication."""
        # Use first line + exception type as signature
        lines = error_message.split("\n")
        if lines:
            return f"{lines[0][:80]}|{error_message.split(':')[0]}"
        return "unknown_error"

    def has_seen_error(self, error_signature: str) -> bool:
        """Check if we've seen this exact error before."""
        return error_signature in self._error_history

    def get_strategy_recommendation(self) -> str:
        """Get a recommendation for what strategy to try next."""
        if not self.repair_attempts:
            return "initial_development"

        recent = self.repair_attempts[-3:]
        failed_strategies = [a.strategy_used for a in recent if a.result_after_patch == "failed"]

        # Suggest different strategy if same one failed repeatedly
        from collections import Counter
        strategy_counts = Counter(failed_strategies)
        most_common = strategy_counts.most_common(1)
        if most_common and most_common[0][1] >= 2:
            alternatives = ["structural_fix", "dependency_resolution", "test_rewrite",
                          "architecture_change"]
            for alt in alternatives:
                if alt not in failed_strategies:
                    return alt

        return "incremental_fix"

    def persist_state(self) -> None:
        """Save current state to disk."""
        state_path = self.workspace_root / "persistence_state.json"
        state = {
            "run_id": self.run_id,
            "state": self.state.value,
            "elapsed_minutes": self.elapsed_minutes,
            "total_repair_attempts": self.total_repair_attempts,
            "consecutive_failures": self._consecutive_failures,
            "stagnation_counter": self._stagnation_counter,
            "policy": self.policy.to_dict(),
            "error_history": {k: len(v) for k, v in self._error_history.items()},
        }
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load previous state if available."""
        state_path = self.workspace_root / "persistence_state.json"
        if not state_path.exists():
            return None
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return data
        except Exception as e:
            logger.warning("Failed to load state: %s", e)
            return None
