"""TaskAnalyzer — deterministic cognitive task analysis.

Estimates task properties without conflating difficulty with model capability:
  - complexity (1-5)
  - independent sub-tasks count
  - uncertainty (low/medium/high)
  - modification risk
  - verification need
  - available resources
  - token/time budget

Analysis is correction-aware: observed results can refine future estimates.
"""

from __future__ import annotations

import enum
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import Task

logger = logging.getLogger("Life_mean.Orchestrator.TaskAnalyzer")


# ── Analysis enums ────────────────────────────────────────────────────────────


class UncertaintyLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Analysis result ───────────────────────────────────────────────────────────


@dataclass
class TaskAnalysis:
    """Structured analysis of a task's cognitive properties."""
    task_id: str
    complexity: int  # 1-5
    independent_subtasks: int
    uncertainty: UncertaintyLevel
    risk_level: RiskLevel
    needs_verification: bool
    available_resources: Dict[str, Any] = field(default_factory=dict)
    token_budget_estimate: int = 0
    time_budget_estimate_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_simple(self) -> bool:
        return self.complexity <= 2 and self.independent_subtasks <= 1

    @property
    def is_complex(self) -> bool:
        return self.complexity >= 4 or self.independent_subtasks >= 3

    @property
    def is_uncertain(self) -> bool:
        return self.uncertainty in (UncertaintyLevel.MEDIUM, UncertaintyLevel.HIGH)

    @property
    def needs_divergence(self) -> bool:
        return self.is_complex and self.is_uncertain


@dataclass
class CorrectionRecord:
    """Stores observed vs estimated for learning."""
    task_id: str
    estimated_complexity: int
    actual_complexity: int  # derived from test outcomes
    estimated_subtasks: int
    actual_subtasks: int
    correction_factor: float = 1.0
    recorded_at: float = field(default_factory=time.time)


# ── TaskAnalyzer ──────────────────────────────────────────────────────────────


class TaskAnalyzer:
    """Deterministic task analyzer for adaptive orchestration.

    Analysis rules:
      - Never conflate difficulty with model capability.
      - Use heuristics based on task description and metadata.
      - Allow correction from observed results.
      - Return structured analysis, not just a score.
    """

    # Keywords indicating complexity.
    _COMPLEXITY_KEYWORDS = {
        "build": 2, "implement": 2, "create": 1, "design": 2,
        "architect": 3, "optimize": 2, "refactor": 2, "debug": 2,
        "full": 3, "system": 3, "complete": 2, "end-to-end": 3,
        "multi": 2, "distributed": 3, "scalable": 3, "production": 2,
    }

    # Keywords indicating uncertainty.
    _UNCERTAINTY_KEYWORDS = {
        "explore": 1, "research": 2, "investigate": 2, "experiment": 2,
        "unknown": 2, "novel": 2, "untested": 1, "prototype": 1,
    }

    # Keywords indicating modification risk.
    _RISK_KEYWORDS = {
        "core": 2, "critical": 3, "refactor": 2, "rewrite": 3,
        "migrate": 3, "upgrade": 2, "replace": 2, "delete": 3,
    }

    def __init__(self, correction_history: Optional[List[CorrectionRecord]] = None) -> None:
        self._corrections: List[CorrectionRecord] = correction_history or []

    def analyze(self, task: Task, resources: Optional[Dict[str, Any]] = None
                ) -> TaskAnalysis:
        """Analyze a task and return structured analysis."""
        complexity = self._estimate_complexity(task)
        subtasks = self._estimate_subtasks(task)
        uncertainty = self._estimate_uncertainty(task)
        risk = self._estimate_risk(task)

        # Apply correction factor from history if available.
        correction = self._get_correction_factor(task.task_id)
        if correction != 1.0:
            logger.debug("Applying correction factor %.2f for task %s", correction, task.task_id)
            complexity = max(1, min(5, round(complexity * correction)))

        return TaskAnalysis(
            task_id=task.task_id,
            complexity=complexity,
            independent_subtasks=subtasks,
            uncertainty=uncertainty,
            risk_level=risk,
            needs_verification=self._needs_verification(task, complexity),
            available_resources=resources or {},
            token_budget_estimate=self._estimate_token_budget(task, complexity, subtasks),
            time_budget_estimate_seconds=self._estimate_time_budget(complexity, subtasks),
        )

    def record_observation(self, task_id: str, estimated: TaskAnalysis,
                           actual_passed: bool, actual_steps: int = 0,
                           actual_tokens: int = 0) -> None:
        """Record an observation to refine future estimates."""
        # Infer actual complexity from outcomes.
        actual_complexity = min(5, max(1, estimated.complexity))
        if not actual_passed:
            actual_complexity = min(5, actual_complexity + 1)
        if actual_steps > estimated.independent_subtasks * 2:
            actual_complexity = min(5, actual_complexity + 1)

        correction = self._compute_correction(estimated, actual_complexity, actual_steps)

        record = CorrectionRecord(
            task_id=task_id,
            estimated_complexity=estimated.complexity,
            actual_complexity=actual_complexity,
            estimated_subtasks=estimated.independent_subtasks,
            actual_subtasks=actual_steps,
            correction_factor=correction,
        )
        self._corrections.append(record)
        logger.debug("Recorded correction for task %s: factor=%.2f", task_id, correction)

    def _estimate_complexity(self, task: Task) -> int:
        """Estimate complexity 1-5 from description and metadata."""
        score = 1  # base

        # Use provided difficulty if available.
        if task.difficulty is not None:
            return max(1, min(5, task.difficulty))

        # Heuristic from description keywords.
        desc_lower = task.description.lower()
        for keyword, points in self._COMPLEXITY_KEYWORDS.items():
            if keyword in desc_lower:
                score += points

        # Context budget as signal.
        if task.context_budget_tokens > 8192:
            score += 1
        elif task.context_budget_tokens > 4096:
            score += 0.5

        return max(1, min(5, round(score)))

    def _estimate_subtasks(self, task: Task) -> int:
        """Estimate number of independent sub-tasks."""
        desc_lower = task.description.lower()

        # Count explicit decomposition signals (allow space between keyword and digit).
        separators = len(re.findall(r'\b(?:step|phase|part|module|component)\s*\d', desc_lower))
        numbered = len(re.findall(r'\d+[.)]\s*\w+', desc_lower))

        base = max(1, separators + (1 if numbered > 0 else 0))

        # Scale by complexity.
        complexity = self._estimate_complexity(task)
        return max(base, min(10, base + complexity - 1))

    def _estimate_uncertainty(self, task: Task) -> UncertaintyLevel:
        """Estimate uncertainty from description."""
        desc_lower = task.description.lower()
        uncertainty_signals = sum(
            pts for word, pts in self._UNCERTAINTY_KEYWORDS.items()
            if word in desc_lower
        )

        if uncertainty_signals >= 3:
            return UncertaintyLevel.HIGH
        if uncertainty_signals >= 1:
            return UncertaintyLevel.MEDIUM
        return UncertaintyLevel.LOW

    def _estimate_risk(self, task: Task) -> RiskLevel:
        """Estimate modification risk."""
        desc_lower = task.description.lower()
        risk_signals = sum(
            pts for word, pts in self._RISK_KEYWORDS.items()
            if word in desc_lower
        )

        if risk_signals >= 3:
            return RiskLevel.HIGH
        if risk_signals >= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _needs_verification(self, task: Task, complexity: int) -> bool:
        """Tasks with complexity >= 3 or explicit verification need."""
        if complexity >= 3:
            return True
        return "verify" in task.description.lower() or "test" in task.description.lower()

    def _estimate_token_budget(self, task: Task, complexity: int,
                                subtasks: int) -> int:
        """Estimate token budget based on complexity and subtasks."""
        base = task.context_budget_tokens if task.context_budget_tokens > 0 else 4096
        # Scale by complexity and subtask count.
        return max(base, base * complexity // 3 * max(1, subtasks))

    def _estimate_time_budget(self, complexity: int, subtasks: int) -> float:
        """Estimate time budget in seconds."""
        # Rough heuristic: 30s per complexity point + 60s per subtask.
        return 30 * complexity + 60 * subtasks

    def _get_correction_factor(self, task_id: str) -> float:
        """Get correction factor from history for a task pattern."""
        if not self._corrections:
            return 1.0

        # Look for similar past tasks (by ID prefix or exact match).
        for record in reversed(self._corrections):
            if record.task_id == task_id or task_id.startswith(record.task_id.split("_")[0]):
                return record.correction_factor

        # Fall back to average of all corrections.
        if self._corrections:
            avg = sum(r.correction_factor for r in self._corrections) / len(self._corrections)
            return avg

        return 1.0

    def _compute_correction(self, estimated: TaskAnalysis,
                             actual_complexity: int, actual_steps: int) -> float:
        """Compute correction factor from observed vs estimated."""
        if estimated.complexity == 0:
            return 1.0
        complexity_ratio = actual_complexity / estimated.complexity
        subtask_ratio = actual_steps / max(1, estimated.independent_subtasks)
        # Blend ratios, cap at reasonable range.
        factor = 0.6 * complexity_ratio + 0.4 * subtask_ratio
        return max(0.5, min(2.0, round(factor, 2)))

    def get_learning_summary(self) -> Dict[str, Any]:
        """Return summary of learning from past corrections."""
        if not self._corrections:
            return {"corrections_count": 0}

        avg_factor = sum(r.correction_factor for r in self._corrections) / len(self._corrections)
        overestimated = sum(1 for r in self._corrections if r.correction_factor < 0.8)
        underestimated = sum(1 for r in self._corrections if r.correction_factor > 1.25)

        return {
            "corrections_count": len(self._corrections),
            "average_correction_factor": round(avg_factor, 3),
            "overestimated_count": overestimated,
            "underestimated_count": underestimated,
            "last_corrections": [
                {
                    "task_id": r.task_id,
                    "estimated": r.estimated_complexity,
                    "actual": r.actual_complexity,
                    "factor": r.correction_factor,
                }
                for r in self._corrections[-5:]
            ],
        }
