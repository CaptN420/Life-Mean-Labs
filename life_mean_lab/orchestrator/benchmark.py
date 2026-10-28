"""Benchmark framework — compare orchestration strategies A/B/C/D/E.

Experimental conditions:
  A. Model seul (baseline)
  B. Modèle + outils déterministes
  C. Single Model Multi-Role (Mode A)
  D. Multi-Model Collaboration (Mode B)
  E. Hybrid Adaptive avec divergence/convergence (Mode C)

Each condition runs the SAME tasks with the SAME models and constraints.
Metrics are measured, not assumed. Comparison is deterministic.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Life_mean.Orchestrator.Benchmark")

from .models import AgentResult, Branch, ConvergenceResult, Strategy, Task


# ── Metric collection ────────────────────────────────────────────────────────


@dataclass
class ConditionMetrics:
    """Aggregated metrics for one experimental condition."""
    condition_id: str  # "A", "B", "C", "D", or "E"
    condition_description: str = ""
    tasks_run: int = 0
    tasks_passed: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    per_task_metrics: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        completed = self.tasks_passed + self.tasks_failed
        if completed == 0:
            return 0.0
        return self.tasks_passed / completed

    @property
    def avg_tokens_per_task(self) -> float:
        if self.tasks_run == 0:
            return 0.0
        return self.total_tokens / self.tasks_run

    @property
    def avg_duration_per_task(self) -> float:
        if self.tasks_run == 0:
            return 0.0
        return self.total_duration_seconds / self.tasks_run

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "description": self.condition_description,
            "tasks_run": self.tasks_run,
            "tasks_passed": self.tasks_passed,
            "tasks_failed": self.tasks_failed,
            "tasks_skipped": self.tasks_skipped,
            "success_rate": round(self.success_rate, 4),
            "total_tokens": self.total_tokens,
            "avg_tokens_per_task": round(self.avg_tokens_per_task, 2),
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "avg_duration_per_task": round(self.avg_duration_per_task, 2),
        }


@dataclass
class BenchmarkResult:
    """Full benchmark result comparing all conditions."""
    benchmark_id: str = field(default_factory=lambda: f"bench_{int(time.time())}")
    generated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    conditions: Dict[str, ConditionMetrics] = field(default_factory=dict)
    pairwise_comparisons: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def add_condition(self, metrics: ConditionMetrics) -> None:
        self.conditions[metrics.condition_id] = metrics

    def compare_pairs(self) -> List[Dict[str, Any]]:
        """Generate pairwise comparisons between conditions."""
        comparisons = []
        cond_ids = sorted(self.conditions.keys())
        for i, id_a in enumerate(cond_ids):
            for id_b in cond_ids[i+1:]:
                a = self.conditions[id_a]
                b = self.conditions[id_b]
                diff_rate = a.success_rate - b.success_rate
                diff_tokens = a.total_tokens - b.total_tokens
                comparisons.append({
                    "condition_a": id_a,
                    "condition_b": id_b,
                    "success_rate_diff": round(diff_rate, 4),
                    "tokens_diff": diff_tokens,
                    "duration_diff_seconds": round(
                        a.total_duration_seconds - b.total_duration_seconds, 2
                    ),
                })
        self.pairwise_comparisons = comparisons
        return comparisons

    def export_json(self, path: Path) -> Path:
        """Export benchmark result to JSON."""
        data = {
            "benchmark_id": self.benchmark_id,
            "generated_at": self.generated_at,
            "conditions": {k: v.to_dict() for k, v in self.conditions.items()},
            "pairwise_comparisons": self.pairwise_comparisons,
            "notes": self.notes,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def export_csv(self, path: Path) -> Path:
        """Export benchmark result to CSV."""
        lines = ["condition_id,description,tasks_run,tasks_passed,tasks_failed,"
                 "success_rate,total_tokens,avg_tokens_per_task,"
                 "total_duration_seconds,avg_duration_per_task"]
        for cond in sorted(self.conditions.values(), key=lambda m: m.condition_id):
            d = cond.to_dict()
            lines.append(
                f"{d['condition_id']},{d['description']},{d['tasks_run']},"
                f"{d['tasks_passed']},{d['tasks_failed']},{d['success_rate']},"
                f"{d['total_tokens']},{d['avg_tokens_per_task']},"
                f"{d['total_duration_seconds']},{d['avg_duration_per_task']}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


# ── Benchmark runner ─────────────────────────────────────────────────────────


class BenchmarkRunner:
    """Runs experimental conditions and collects metrics.

    Usage:
        runner = BenchmarkRunner(task_dataset, model_registry)
        runner.run_condition("A", baseline_executor)
        runner.run_condition("C", multi_role_executor)
        result = runner.finalize()
        result.export_json(Path("benchmarks/result.json"))
    """

    # Condition descriptions matching the mission spec.
    CONDITION_DESCRIPTIONS = {
        "A": "Model seul (baseline)",
        "B": "Modèle + outils déterministes",
        "C": "Single Model Multi-Role (Mode A)",
        "D": "Multi-Model Collaboration (Mode B)",
        "E": "Hybrid Adaptive avec divergence/convergence (Mode C)",
    }

    def __init__(self, benchmark_id: Optional[str] = None) -> None:
        self._result = BenchmarkResult(benchmark_id=benchmark_id or "")
        self._task_dataset: List[Task] = []

    @property
    def result(self) -> BenchmarkResult:
        return self._result

    def register_tasks(self, tasks: List[Task]) -> None:
        """Register the task dataset for all conditions to share."""
        self._task_dataset = tasks

    def run_condition(self, condition_id: str, executor,
                      tasks: Optional[List[Task]] = None) -> ConditionMetrics:
        """Run one experimental condition against a subset (or all) tasks.

        Args:
            condition_id: "A", "B", "C", "D", or "E"
            executor: A callable `execute(task) -> AgentResult`
            tasks: Tasks to run (defaults to registered dataset)
        """
        task_list = tasks or self._task_dataset
        if not task_list:
            raise ValueError(f"No tasks registered for condition '{condition_id}'")

        metrics = ConditionMetrics(
            condition_id=condition_id,
            condition_description=self.CONDITION_DESCRIPTIONS.get(condition_id, condition_id),
        )

        for task in task_list:
            try:
                start = time.time()
                result = executor(task)
                duration = time.time() - start

                if isinstance(result, AgentResult):
                    metrics.tasks_run += 1
                    passed = (result.validation_result or result.is_complete)
                    if passed:
                        metrics.tasks_passed += 1
                    else:
                        metrics.tasks_failed += 1
                    metrics.total_tokens += result.tokens_total
                    metrics.total_duration_seconds += duration
                    metrics.per_task_metrics.append({
                        "task_id": task.task_id,
                        "passed": passed,
                        "tokens": result.tokens_total,
                        "duration": duration,
                    })
                else:
                    # Fallback: assume boolean result.
                    metrics.tasks_run += 1
                    if result:
                        metrics.tasks_passed += 1
                    else:
                        metrics.tasks_failed += 1

            except Exception as e:
                metrics.tasks_run += 1
                metrics.tasks_failed += 1
                metrics.per_task_metrics.append({
                    "task_id": task.task_id,
                    "error": str(e),
                })
                logger.warning("Condition '%s' task '%s' failed: %s",
                               condition_id, task.task_id, e)

        self._result.add_condition(metrics)
        return metrics

    def finalize(self) -> BenchmarkResult:
        """Run pairwise comparisons and return the final result."""
        self._result.compare_pairs()
        return self._result
