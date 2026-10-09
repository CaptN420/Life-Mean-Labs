"""Failure record schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FailureRecord:
    """Record of a validation failure."""

    task_id: str
    experiment_id: str
    run_id: str
    failed_answer: Any
    ground_truth: Any
    error_message: Optional[str] = None
    validation_method: str = "deterministic"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "failed_answer": self.failed_answer,
            "ground_truth": self.ground_truth,
            "error_message": self.error_message,
            "validation_method": self.validation_method,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FailureRecord":
        return cls(
            task_id=data["task_id"],
            experiment_id=data["experiment_id"],
            run_id=data["run_id"],
            failed_answer=data.get("failed_answer"),
            ground_truth=data.get("ground_truth"),
            error_message=data.get("error_message"),
            validation_method=data.get("validation_method", "deterministic"),
            metadata=data.get("metadata", {}),
        )
