"""Metacognitive memory storage.

Provides persistent, isolated storage for experiment memories
and enables cross-run comparison and pattern detection.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import ErrorPattern, RunMemory, StrategyComparison

logger = logging.getLogger("MetacognitiveMemory")


class MetacognitiveMemory:
    """Persistent storage for metacognitive experiment data."""

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage_path = storage_path or (
            Path("data") / "metacognition" / "memory.json"
        )
        self._lock = threading.RLock()
        self._runs: Dict[str, RunMemory] = {}
        self._error_patterns: Dict[str, ErrorPattern] = {}
        self._strategy_comparisons: Dict[str, StrategyComparison] = {}
        self._project_index: Dict[str, List[str]] = {}

        self._load_if_exists()

    def _load_if_exists(self) -> None:
        """Load memory from disk if file exists."""
        if not self._storage_path.exists():
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                for run_data in data.get("runs", []):
                    run_id = run_data.get("run_id", "")
                    if run_id:
                        self._runs[run_id] = RunMemory.from_dict(run_data)
                        project = run_data.get("project", "unknown")
                        if project not in self._project_index:
                            self._project_index[project] = []
                        self._project_index[project].append(run_id)

                for pattern_data in data.get("error_patterns", []):
                    pattern_id = pattern_data.get("error_type", "")
                    if pattern_id:
                        self._error_patterns[pattern_id] = ErrorPattern.from_dict(
                            pattern_data
                        )

                for comp_data in data.get("strategy_comparisons", []):
                    key = f"{comp_data.get('strategy_a', '')}_vs_{comp_data.get('strategy_b', '')}"
                    self._strategy_comparisons[key] = StrategyComparison.from_dict(
                        comp_data
                    )

            logger.info(
                f"Loaded {len(self._runs)} runs, "
                f"{len(self._error_patterns)} error patterns, "
                f"{len(self._strategy_comparisons)} comparisons"
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load metacognitive memory: {e}")

    def save_run_memory(self, memory: RunMemory) -> None:
        """Persist a run's metacognitive memory."""
        with self._lock:
            self._runs[memory.run_id] = memory
            project = memory.project
            if project not in self._project_index:
                self._project_index[project] = []
            if memory.run_id not in self._project_index[project]:
                self._project_index[project].append(memory.run_id)
            self._save()

    def get_run_memory(self, run_id: str) -> Optional[RunMemory]:
        """Retrieve memory for a specific run."""
        with self._lock:
            return self._runs.get(run_id)

    def list_runs_by_project(self, project: str) -> List[RunMemory]:
        """List all memories for a project."""
        with self._lock:
            run_ids = self._project_index.get(project, [])
            return [self._runs[rid] for rid in run_ids if rid in self._runs]

    def list_all_runs(self) -> List[RunMemory]:
        """List all stored memories."""
        with self._lock:
            return list(self._runs.values())

    def detect_error_patterns(self, runs: List[RunMemory]) -> Dict[str, ErrorPattern]:
        """Analyze runs to detect recurring error patterns."""
        patterns: Dict[str, ErrorPattern] = {}

        for run in runs:
            for error in run.errors_detected:
                error_type = error.get("type", "unknown")
                if error_type not in patterns:
                    patterns[error_type] = ErrorPattern(
                        error_type=error_type,
                        description=error.get("description", ""),
                        occurrence_count=0,
                        affected_runs=[],
                        first_seen=run.created_at,
                        last_seen=run.created_at,
                    )

                pattern = patterns[error_type]
                pattern.occurrence_count += 1
                if run.run_id not in pattern.affected_runs:
                    pattern.affected_runs.append(run.run_id)
                pattern.last_seen = run.created_at

        with self._lock:
            self._error_patterns.update(patterns)
            self._save()

        return patterns

    def add_strategy_comparison(
        self, comparison: StrategyComparison
    ) -> str:
        """Store a strategy comparison result."""
        key = f"{comparison.strategy_a}_vs_{comparison.strategy_b}"
        with self._lock:
            self._strategy_comparisons[key] = comparison
            self._save()
        return key

    def get_strategy_comparison(
        self, strategy_a: str, strategy_b: str
    ) -> Optional[StrategyComparison]:
        """Retrieve a strategy comparison."""
        key = f"{strategy_a}_vs_{strategy_b}"
        with self._lock:
            return self._strategy_comparisons.get(key)

    def _save(self) -> None:
        """Persist memory to disk."""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "runs": [r.to_dict() for r in self._runs.values()],
                "error_patterns": [p.to_dict() for p in self._error_patterns.values()],
                "strategy_comparisons": [
                    c.to_dict() for c in self._strategy_comparisons.values()
                ],
                "project_index": self._project_index,
            }

            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved metacognitive memory to {self._storage_path}")
        except OSError as e:
            logger.error(f"Failed to save metacognitive memory: {e}")

    def clear_project(self, project: str) -> int:
        """Remove all memories for a project. Returns count removed."""
        with self._lock:
            run_ids = self._project_index.get(project, [])
            count = len(run_ids)
            for rid in run_ids:
                self._runs.pop(rid, None)
            self._project_index.pop(project, None)
            self._save()
            return count

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics."""
        with self._lock:
            total_runs = len(self._runs)
            passed = sum(1 for r in self._runs.values() if r.status == "passed")
            failed = sum(1 for r in self._runs.values() if r.status == "failed")

            return {
                "total_runs": total_runs,
                "passed": passed,
                "failed": failed,
                "success_rate": passed / total_runs if total_runs > 0 else 0.0,
                "projects": len(self._project_index),
                "error_patterns_detected": len(self._error_patterns),
                "strategy_comparisons": len(self._strategy_comparisons),
            }
