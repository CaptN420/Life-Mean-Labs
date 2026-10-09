"""Experiment layer — Study, Experiment, Condition, Run.

Provides high-level abstractions for designing, configuring, and
tracking synthetic data generation experiments.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from experiments.config import ExperimentConfig


@dataclass
class Condition:
    """An experimental condition with specific parameters.

    Represents one configuration of an experiment that can be run
    and compared against other conditions.
    """

    name: str
    config: ExperimentConfig
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "config": self.config.to_dict(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        config = ExperimentConfig.from_dict(data["config"])
        return cls(
            name=data["name"],
            config=config,
            description=data.get("description", ""),
        )


@dataclass
class Study:
    """An experimental study with multiple conditions.

    A study defines the overall experimental design, including
    all conditions to be tested and comparison criteria.
    """

    title: str
    conditions: List[Condition] = field(default_factory=list)
    hypothesis: str = ""
    study_id: str = field(default_factory=lambda: f"study_{uuid.uuid4().hex[:8]}")
    created_at: float = field(default_factory=time.time)

    def add_condition(self, condition: Condition) -> None:
        """Add a condition to the study."""
        self.conditions.append(condition)

    def get_condition(self, name: str) -> Optional[Condition]:
        """Get a condition by name."""
        for cond in self.conditions:
            if cond.name == name:
                return cond
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "study_id": self.study_id,
            "title": self.title,
            "hypothesis": self.hypothesis,
            "conditions": [c.to_dict() for c in self.conditions],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Study":
        study = cls(
            title=data["title"],
            hypothesis=data.get("hypothesis", ""),
            study_id=data.get("study_id", f"study_{uuid.uuid4().hex[:8]}"),
            created_at=data.get("created_at", time.time()),
        )
        for cond_data in data.get("conditions", []):
            study.add_condition(Condition.from_dict(cond_data))
        return study


@dataclass
class RunResult:
    """Result of a single task execution within a run."""

    task_id: str
    experiment_id: str
    run_id: str
    condition_name: str
    success: bool
    answer: Optional[str] = None
    ground_truth: Optional[str] = None
    score: float = 0.0
    validation_result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "condition_name": self.condition_name,
            "success": self.success,
            "answer": self.answer,
            "ground_truth": self.ground_truth,
            "score": self.score,
            "validation_result": self.validation_result,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class Run:
    """An execution of an experiment condition."""

    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")
    study_id: str = ""
    condition_name: str = ""
    config: ExperimentConfig = field(default_factory=ExperimentConfig)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    results: List[RunResult] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed

    def start(self) -> None:
        """Start the run."""
        self.start_time = time.time()
        self.status = "running"

    def complete(self) -> None:
        """Mark the run as complete."""
        self.end_time = time.time()
        self.status = "completed"

    def fail(self, error: str = "") -> None:
        """Mark the run as failed."""
        self.end_time = time.time()
        self.status = "failed"
        if error:
            self._last_error = error

    def add_result(self, result: RunResult) -> None:
        """Add a result to the run."""
        self.results.append(result)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        end = self.end_time or time.time()
        return end - (self.start_time or end)

    @property
    def success_rate(self) -> float:
        """Get the success rate."""
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.success) / len(self.results)

    @property
    def avg_score(self) -> float:
        """Get the average score."""
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "study_id": self.study_id,
            "condition_name": self.condition_name,
            "config": self.config.to_dict(),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "elapsed_seconds": self.elapsed_seconds,
            "status": self.status,
            "num_results": len(self.results),
            "success_rate": self.success_rate,
            "avg_score": self.avg_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Run":
        run = cls(
            run_id=data.get("run_id", f"run_{uuid.uuid4().hex[:8]}"),
            study_id=data.get("study_id", ""),
            condition_name=data.get("condition_name", ""),
            config=ExperimentConfig.from_dict(data.get("config", {})),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            status=data.get("status", "pending"),
        )
        for result_data in data.get("results", []):
            run.add_result(RunResult(**result_data))
        return run


class ExperimentManager:
    """Manages studies, runs, and results."""

    def __init__(self) -> None:
        self._studies: Dict[str, Study] = {}
        self._runs: Dict[str, Run] = {}
        self._results_by_run: Dict[str, List[RunResult]] = {}

    def create_study(self, study: Study) -> Study:
        """Create and register a study."""
        self._studies[study.study_id] = study
        return study

    def get_study(self, study_id: str) -> Optional[Study]:
        """Get a study by ID."""
        return self._studies.get(study_id)

    def create_run(
        self,
        study_id: str,
        condition_name: str,
        config: Optional[ExperimentConfig] = None,
    ) -> Run:
        """Create a new run for a study condition."""
        run = Run(
            study_id=study_id,
            condition_name=condition_name,
            config=config or ExperimentConfig(),
        )
        self._runs[run.run_id] = run
        self._results_by_run[run.run_id] = []
        return run

    def start_run(self, run_id: str) -> bool:
        """Start a run."""
        if run_id not in self._runs:
            return False
        self._runs[run_id].start()
        return True

    def complete_run(self, run_id: str) -> bool:
        """Complete a run."""
        if run_id not in self._runs:
            return False
        self._runs[run_id].complete()
        return True

    def add_result(self, result: RunResult) -> None:
        """Add a result to a run."""
        if result.run_id in self._results_by_run:
            self._results_by_run[result.run_id].append(result)

    def get_run(self, run_id: str) -> Optional[Run]:
        """Get a run by ID."""
        return self._runs.get(run_id)

    def get_run_results(self, run_id: str) -> List[RunResult]:
        """Get all results for a run."""
        return self._results_by_run.get(run_id, [])

    def get_study_runs(self, study_id: str) -> List[Run]:
        """Get all runs for a study."""
        return [r for r in self._runs.values() if r.study_id == study_id]

    def get_statistics(self, run_id: str) -> Dict[str, Any]:
        """Get statistics for a run."""
        run = self._runs.get(run_id)
        if not run:
            return {}

        results = self._results_by_run.get(run_id, [])
        if not results:
            return {
                "num_tasks": 0,
                "success_rate": 0.0,
                "avg_score": 0.0,
                "elapsed_seconds": 0.0,
            }

        return {
            "num_tasks": len(results),
            "success_rate": sum(1 for r in results if r.success) / len(results),
            "avg_score": sum(r.score for r in results) / len(results),
            "elapsed_seconds": run.elapsed_seconds,
        }
