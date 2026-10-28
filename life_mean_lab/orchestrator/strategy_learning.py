"""StrategyLearning — lightweight strategy performance tracking and selection.

Records outcomes of each strategy execution (task type, difficulty, models used,
budget, tokens, time, test results) and provides data-driven recommendations
for future task routing.

Design rules:
  - Records explicit statistics; never trains model weights.
  - Requires minimum sample size before recommending a strategy.
  - Preserves deterministic fallback policy when learning is disabled.
  - Never conflates correlation with causation on small samples.
"""

from __future__ import annotations

import enum
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Life_mean.Orchestrator.StrategyLearning")


# ── Strategy outcome ──────────────────────────────────────────────────────────


class TaskType(str, enum.Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    UNCERTAIN = "uncertain"
    REPAIR = "repair"


@dataclass
class StrategyRecord:
    """Outcome record for a single strategy execution."""
    task_type: TaskType
    task_difficulty: int  # 1-5
    strategy_used: str  # e.g. "sequential", "single_model_multi_role", etc.
    models_used: List[str] = field(default_factory=list)
    budget_allocated_tokens: int = 0
    tokens_consumed: int = 0
    duration_seconds: float = 0.0
    tests_passed: int = 0
    tests_total: int = 0
    success: bool = False
    attempts: int = 1
    relative_cost: float = 0.0  # tokens per unit of success

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "task_difficulty": self.task_difficulty,
            "strategy_used": self.strategy_used,
            "models_used": self.models_used,
            "budget_allocated_tokens": self.budget_allocated_tokens,
            "tokens_consumed": self.tokens_consumed,
            "duration_seconds": round(self.duration_seconds, 2),
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
            "success": self.success,
            "attempts": self.attempts,
            "relative_cost": round(self.relative_cost, 4),
        }


# ── StrategyLearning engine ───────────────────────────────────────────────────


class StrategyLearning:
    """Tracks strategy performance and provides data-driven recommendations.

    Uses explicit statistics (win rates, cost efficiency) rather than learned
    weights. Requires minimum samples before making recommendations to avoid
    spurious conclusions on small datasets.
    """

    # Minimum records required before trusting a recommendation.
    MIN_SAMPLES_FOR_RECOMMENDATION = 5
    # Decay factor for recency weighting (exponential moving average).
    DECAY_FACTOR = 0.9

    def __init__(
        self,
        enable_learning: bool = True,
        min_samples: int = MIN_SAMPLES_FOR_RECOMMENDATION,
    ) -> None:
        self.enable_learning = enable_learning
        self.min_samples = min_samples
        self._records: List[StrategyRecord] = []
        self._strategy_stats: Dict[str, Dict[str, Any]] = {}

    def record(
        self,
        task_type: TaskType,
        task_difficulty: int,
        strategy_used: str,
        models_used: List[str],
        tokens_consumed: int,
        duration_seconds: float,
        tests_passed: int,
        tests_total: int,
        success: bool,
        budget_allocated_tokens: int = 0,
        attempts: int = 1,
    ) -> None:
        """Record the outcome of a strategy execution."""
        if not self.enable_learning:
            return

        record = StrategyRecord(
            task_type=task_type,
            task_difficulty=task_difficulty,
            strategy_used=strategy_used,
            models_used=models_used,
            budget_allocated_tokens=budget_allocated_tokens,
            tokens_consumed=tokens_consumed,
            duration_seconds=duration_seconds,
            tests_passed=tests_passed,
            tests_total=tests_total,
            success=success,
            attempts=attempts,
        )
        self._records.append(record)
        self._update_stats(record)
        logger.debug("Recorded strategy outcome: %s on %s task (success=%s)",
                     strategy_used, task_type.value, success)

    def _update_stats(self, record: StrategyRecord) -> None:
        """Update running statistics for a strategy."""
        key = record.strategy_used
        if key not in self._strategy_stats:
            self._strategy_stats[key] = {
                "count": 0,
                "success_count": 0,
                "total_tokens": 0,
                "total_duration": 0.0,
                "weighted_success_rate": 0.0,
            }

        stats = self._strategy_stats[key]
        stats["count"] += 1
        if record.success:
            stats["success_count"] += 1
        stats["total_tokens"] += record.tokens_consumed
        stats["total_duration"] += record.duration_seconds

        # Update weighted success rate with decay.
        n = stats["count"]
        old_rate = stats.get("weighted_success_rate", 0.0)
        new_rate = (old_rate * self.DECAY_FACTOR + (1.0 if record.success else 0.0)) / (
            1.0 - self.DECAY_FACTOR ** (n + 1)
        ) if n > 0 else 0.0
        stats["weighted_success_rate"] = new_rate

    def recommend(
        self,
        task_type: TaskType,
        task_difficulty: int,
    ) -> Optional[str]:
        """Recommend the best strategy for a task type/difficulty.

        Returns None if there are insufficient samples or learning is disabled.
        """
        if not self.enable_learning:
            return None

        # Filter records by task type and difficulty range.
        matching = [
            r for r in self._records
            if r.task_type == task_type and abs(r.task_difficulty - task_difficulty) <= 1
        ]

        if len(matching) < self.min_samples:
            logger.debug("Insufficient samples (%d) for recommendation on %s",
                         len(matching), task_type.value)
            return None

        # Aggregate by strategy.
        agg: Dict[str, Dict[str, Any]] = {}
        for record in matching:
            if record.strategy_used not in agg:
                agg[record.strategy_used] = {
                    "count": 0,
                    "success_count": 0,
                    "total_tokens": 0,
                }
            agg[record.strategy_used]["count"] += 1
            if record.success:
                agg[record.strategy_used]["success_count"] += 1
            agg[record.strategy_used]["total_tokens"] += record.tokens_consumed

        # Score strategies by success rate and cost efficiency.
        scores: Dict[str, float] = {}
        for strategy, data in agg.items():
            count = data["count"]
            if count < self.min_samples:
                continue
            success_rate = data["success_count"] / count
            avg_cost = data["total_tokens"] / count if count > 0 else 0
            # Prefer higher success rate, lower cost.
            score = success_rate - (avg_cost / 10000.0) * 0.1
            scores[strategy] = score

        if not scores:
            return None

        best_strategy = max(scores.items(), key=lambda x: x[1])[0]
        logger.info("Recommended strategy '%s' for %s task (difficulty=%d, samples=%d)",
                     best_strategy, task_type.value, task_difficulty, len(matching))
        return best_strategy

    def get_statistics(self) -> Dict[str, Any]:
        """Return aggregate statistics across all recorded strategies."""
        return {
            "total_records": len(self._records),
            "strategy_stats": {
                k: {
                    "count": v["count"],
                    "success_rate": round(v["success_count"] / v["count"], 4) if v["count"] > 0 else 0.0,
                    "avg_tokens": round(v["total_tokens"] / v["count"], 2) if v["count"] > 0 else 0.0,
                    "avg_duration": round(v["total_duration"] / v["count"], 2) if v["count"] > 0 else 0.0,
                }
                for k, v in self._strategy_stats.items()
            },
        }

    def export_records(self, path: Path) -> Path:
        """Export all records to JSON."""
        data = {
            "records": [r.to_dict() for r in self._records],
            "statistics": self.get_statistics(),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def clear(self) -> None:
        """Clear all records and statistics."""
        self._records.clear()
        self._strategy_stats.clear()
