"""Failure bank for storing and analyzing validation failures.

Provides persistent storage of failed validations with query and export capabilities.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import FailureRecord

logger = logging.getLogger("FailureBank")


class FailureBank:
    """Stores and retrieves validation failure records."""

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize the failure bank.

        Args:
            storage_path: Path to JSON file for persistence (optional)
        """
        self._failures: Dict[str, FailureRecord] = {}
        self._storage_path = storage_path
        self._load_if_exists()

    def _load_if_exists(self) -> None:
        """Load failures from disk if file exists."""
        if self._storage_path and self._storage_path.exists():
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for fid, record_data in data.items():
                        self._failures[fid] = FailureRecord.from_dict(record_data)
                logger.info(f"Loaded {len(self._failures)} failure records from {self._storage_path}")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load failures: {e}")

    def store(
        self,
        task_id: str,
        experiment_id: str,
        run_id: str,
        failed_answer: Any,
        ground_truth: Any,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a failure record.

        Args:
            task_id: Original task identifier
            experiment_id: Experiment identifier
            run_id: Run identifier
            failed_answer: The incorrect answer
            ground_truth: The expected answer
            error_message: Optional error description
            metadata: Additional context

        Returns:
            Failure record ID
        """
        record = FailureRecord(
            task_id=task_id,
            experiment_id=experiment_id,
            run_id=run_id,
            failed_answer=failed_answer,
            ground_truth=ground_truth,
            error_message=error_message,
            metadata=metadata or {},
        )

        failure_id = f"fail_{uuid.uuid4().hex[:8]}"
        self._failures[failure_id] = record
        self._save()

        logger.debug(f"Stored failure {failure_id} for task {task_id}")
        return failure_id

    def query(self, task_id: str) -> List[FailureRecord]:
        """Query failures by task ID.

        Args:
            task_id: Task identifier to search for

        Returns:
            List of matching failure records
        """
        return [r for r in self._failures.values() if r.task_id == task_id]

    def query_by_experiment(self, experiment_id: str) -> List[FailureRecord]:
        """Query failures by experiment ID.

        Args:
            experiment_id: Experiment identifier

        Returns:
            List of matching failure records
        """
        return [r for r in self._failures.values() if r.experiment_id == experiment_id]

    def query_by_run(self, run_id: str) -> Optional[FailureRecord]:
        """Query failure by run ID.

        Args:
            run_id: Run identifier

        Returns:
            Matching failure record or None
        """
        for record in self._failures.values():
            if record.run_id == run_id:
                return record
        return None

    def export(self) -> List[Dict[str, Any]]:
        """Export all failures as dictionaries.

        Returns:
            List of failure record dictionaries
        """
        return [r.to_dict() for r in self._failures.values()]

    def get_statistics(self) -> Dict[str, Any]:
        """Get failure statistics.

        Returns:
            Dictionary with failure counts by experiment
        """
        stats = {
            "total_failures": len(self._failures),
            "by_experiment": {},
            "by_task": {},
        }

        for record in self._failures.values():
            stats["by_experiment"][record.experiment_id] = (
                stats["by_experiment"].get(record.experiment_id, 0) + 1
            )
            stats["by_task"][record.task_id] = (
                stats["by_task"].get(record.task_id, 0) + 1
            )

        return stats

    def _save(self) -> None:
        """Save failures to disk."""
        if self._storage_path:
            try:
                data = {fid: r.to_dict() for fid, r in self._failures.items()}
                with open(self._storage_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except OSError as e:
                logger.error(f"Failed to save failures: {e}")

    def clear(self) -> None:
        """Clear all stored failures."""
        self._failures.clear()
        if self._storage_path:
            self._storage_path.unlink(missing_ok=True)
