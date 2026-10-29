"""Comparable Run Finder — identifies similar successful runs for comparison.

Compares runs on:
- Task type and prompt
- Template and roles
- Models and versions
- Parameters and environment
- Dependencies and validators
- Test coverage

Produces an explainable comparability score with distinct metrics.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.comparable_run_finder")


# ── Enums ────────────────────────────────────────────────────────────────────


class RunStatus(str, Enum):
    """Execution status of a run."""
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class MetricAvailability(str, Enum):
    """Availability status of a metric."""
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class RunConfiguration:
    """Configuration of a run."""
    run_id: str
    task_type: str = ""
    prompt: str = ""
    template: str = ""
    roles: List[str] = field(default_factory=list)
    models: List[str] = field(default_factory=list)
    versions: Dict[str, str] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    environment: str = ""
    dependencies: List[str] = field(default_factory=list)
    validators: List[str] = field(default_factory=list)
    test_suite: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_type": self.task_type,
            "prompt": self.prompt[:200],
            "template": self.template,
            "roles": self.roles,
            "models": self.models,
            "versions": self.versions,
            "parameters": {k: str(v)[:50] for k, v in self.parameters.items()},
            "environment": self.environment,
            "dependencies": self.dependencies,
            "validators": self.validators,
            "test_suite": self.test_suite,
        }


@dataclass
class RunMetrics:
    """Performance metrics of a run."""
    run_id: str
    completion_rate: float = 0.0
    validator_pass_rate: float = 0.0
    executed_test_pass_rate: float = 0.0
    artifact_correctness: float = 0.0
    reproducibility: float = 0.0
    configuration_comparability: float = 0.0
    status: RunStatus = RunStatus.UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "completion_rate": self.completion_rate,
            "validator_pass_rate": self.validator_pass_rate,
            "executed_test_pass_rate": self.executed_test_pass_rate,
            "artifact_correctness": self.artifact_correctness,
            "reproducibility": self.reproducibility,
            "configuration_comparability": self.configuration_comparability,
            "status": self.status.value,
            "metadata": self.metadata,
        }


@dataclass
class ComparableRun:
    """A run comparable to a target run."""
    run_id: str
    comparability_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    differences: List[Dict[str, Any]] = field(default_factory=list)
    config: Optional[RunConfiguration] = None
    metrics: Optional[RunMetrics] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "comparability_score": self.comparability_score,
            "score_breakdown": self.score_breakdown,
            "differences": self.differences,
            "config": self.config.to_dict() if self.config else None,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


# ── Comparable Run Finder ────────────────────────────────────────────────────


class ComparableRunFinder:
    """Finds runs comparable to a target run for failure analysis.

    Compares runs on multiple dimensions and produces an explainable score.
    Does not assume high completion rate implies correctness.
    """

    # Weight for each comparison dimension
    _WEIGHTS = {
        "task_type": 0.15,
        "prompt_similarity": 0.20,
        "template_match": 0.10,
        "roles_match": 0.10,
        "model_match": 0.10,
        "version_match": 0.10,
        "parameter_similarity": 0.10,
        "environment_match": 0.10,
        "validator_match": 0.05,
    }

    def __init__(self):
        self._runs: Dict[str, RunConfiguration] = {}
        self._metrics: Dict[str, RunMetrics] = {}

    def register_run(
        self,
        run_id: str,
        config: RunConfiguration,
        metrics: Optional[RunMetrics] = None,
    ) -> None:
        """Register a run for comparison."""
        self._runs[run_id] = config
        if metrics:
            self._metrics[run_id] = metrics

    def find_comparable_runs(
        self,
        target_run_id: str,
        max_results: int = 5,
        min_score: float = 0.3,
    ) -> List[ComparableRun]:
        """Find runs comparable to the target run."""
        target = self._runs.get(target_run_id)
        if not target:
            return []

        candidates = []
        for run_id, config in self._runs.items():
            if run_id == target_run_id:
                continue

            score, breakdown, differences = self._compute_comparability(
                target, config
            )

            if score >= min_score:
                metrics = self._metrics.get(run_id)
                candidates.append(ComparableRun(
                    run_id=run_id,
                    comparability_score=score,
                    score_breakdown=breakdown,
                    differences=differences,
                    config=config,
                    metrics=metrics,
                ))

        # Sort by score descending
        candidates.sort(key=lambda c: c.comparability_score, reverse=True)
        return candidates[:max_results]

    def _compute_comparability(
        self,
        target: RunConfiguration,
        other: RunConfiguration,
    ) -> tuple[float, Dict[str, float], List[Dict[str, Any]]]:
        """Compute comparability score between two runs."""
        breakdown = {}
        differences = []

        # Task type
        task_score = 1.0 if target.task_type == other.task_type else 0.0
        breakdown["task_type"] = task_score
        if target.task_type != other.task_type:
            differences.append({"dimension": "task_type", "target": target.task_type, "other": other.task_type})

        # Prompt similarity (simple word overlap)
        prompt_score = self._compute_text_similarity(target.prompt, other.prompt)
        breakdown["prompt_similarity"] = prompt_score
        if prompt_score < 0.5:
            differences.append({"dimension": "prompt", "target": target.prompt[:50], "other": other.prompt[:50]})

        # Template match
        template_score = 1.0 if target.template == other.template else 0.0
        breakdown["template_match"] = template_score

        # Roles match
        roles_target = set(target.roles)
        roles_other = set(other.roles)
        roles_score = len(roles_target & roles_other) / max(len(roles_target), len(roles_other), 1)
        breakdown["roles_match"] = roles_score

        # Model match
        models_target = set(target.models)
        models_other = set(other.models)
        models_score = len(models_target & models_other) / max(len(models_target), len(models_other), 1)
        breakdown["model_match"] = models_score

        # Version match
        versions_match = sum(
            1 for k, v in target.versions.items() if other.versions.get(k) == v
        ) / max(len(target.versions), 1)
        breakdown["version_match"] = versions_match

        # Parameter similarity
        params_target = set(target.parameters.keys())
        params_other = set(other.parameters.keys())
        param_score = len(params_target & params_other) / max(len(params_target), len(params_other), 1)
        breakdown["parameter_similarity"] = param_score

        # Environment match
        env_score = 1.0 if target.environment == other.environment else 0.0
        breakdown["environment_match"] = env_score

        # Validator match
        val_target = set(target.validators)
        val_other = set(other.validators)
        val_score = len(val_target & val_other) / max(len(val_target), len(val_other), 1)
        breakdown["validator_match"] = val_score

        # Weighted total
        total = sum(self._WEIGHTS.get(dim, 0) * score for dim, score in breakdown.items())

        return round(total, 3), breakdown, differences

    def _compute_text_similarity(self, text1: str, text2: str) -> float:
        """Compute simple word-overlap similarity between two texts."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def get_run_metrics(self, run_id: str) -> Optional[RunMetrics]:
        """Get metrics for a run."""
        return self._metrics.get(run_id)

    def get_run_config(self, run_id: str) -> Optional[RunConfiguration]:
        """Get configuration for a run."""
        return self._runs.get(run_id)
