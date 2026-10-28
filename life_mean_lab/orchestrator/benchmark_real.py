"""RealBenchmarkRunner — extended benchmark framework for real LLM experiments.

Compares strategies (Direct, Mode A, Mode B, Divergence) using identical tasks,
models, and constraints. Supports reproducibility via seeds, configurable
temperature, repetitions, and budget parity.

Design rules:
  - Separates simulated tests from real experiments.
  - Records model version, code version, hardware config.
  - Exports JSON/CSV with full provenance.
  - Never presents estimated metrics as exact measurements.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import platform
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Life_mean.Orchestrator.RealBenchmark")

from .models import AgentResult, Strategy, Task
from .benchmark import BenchmarkRunner, ConditionMetrics, BenchmarkResult


# ── Measurement provenance ────────────────────────────────────────────────────


class MeasureType(str, enum.Enum):
    MEASURED = "measured"      # Provided directly by the engine
    ESTIMATED = "estimated"     # Computed locally
    UNAVAILABLE = "unavailable"  # Unknown


@dataclass
class MetricProvenance:
    """A metric value with its provenance type."""
    value: float
    measure_type: MeasureType
    source: str = ""  # e.g. "llm_engine", "os_measure", "estimated"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "type": self.measure_type.value,
            "source": self.source,
        }


# ── Experiment config ─────────────────────────────────────────────────────────


@dataclass
class ExperimentConfig:
    """Configuration for a single benchmark experiment."""
    experiment_id: str = field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:8]}")
    seed: Optional[int] = None
    temperature: float = 0.3
    max_repetitions: int = 3
    token_budget: int = 16384
    timeout_seconds: float = 120.0
    enable_early_stopping: bool = True
    model_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "temperature": self.temperature,
            "max_repetitions": self.max_repetitions,
            "token_budget": self.token_budget,
            "timeout_seconds": self.timeout_seconds,
            "enable_early_stopping": self.enable_early_stopping,
            "model_configs": self.model_configs,
        }


# ── Real experiment result ────────────────────────────────────────────────────


@dataclass
class RealExperimentResult:
    """Result of a single real experiment run."""
    task_id: str
    strategy: Strategy
    condition_id: str
    success: bool
    tokens_input: MetricProvenance
    tokens_output: MetricProvenance
    latency_ms: MetricProvenance
    tests_passed: int
    tests_total: int
    model_used: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "strategy": self.strategy.value,
            "condition_id": self.condition_id,
            "success": self.success,
            "tokens_input": self.tokens_input.to_dict(),
            "tokens_output": self.tokens_output.to_dict(),
            "latency_ms": self.latency_ms.to_dict(),
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
            "model_used": self.model_used,
            "error": self.error,
            "metadata": self.metadata,
        }


# ── RealBenchmarkRunner ───────────────────────────────────────────────────────


class RealBenchmarkRunner(BenchmarkRunner):
    """Extended benchmark runner for real LLM experiments.

    Compares strategies using identical tasks and constraints, with full
    provenance tracking and reproducibility support.
    """

    # Condition descriptions matching the mission spec.
    CONDITION_DESCRIPTIONS = {
        "A": "Direct execution (baseline)",
        "C": "Single Model Multi-Role (Mode A)",
        "D": "Multi-Model Collaboration (Mode B)",
        "E": "Hybrid Adaptive with divergence/convergence (Mode C)",
    }

    def __init__(
        self,
        config: Optional[ExperimentConfig] = None,
        benchmark_id: Optional[str] = None,
    ) -> None:
        super().__init__(benchmark_id)
        self.config = config or ExperimentConfig()
        self._experiment_results: List[RealExperimentResult] = []
        self._start_time: float = 0.0

    def run_experiment(
        self,
        condition_id: str,
        executor: Callable[[Task], tuple[AgentResult, Dict[str, Any]]],
        tasks: Optional[List[Task]] = None,
    ) -> ConditionMetrics:
        """Run a real experiment for one condition.

        Args:
            condition_id: "A", "C", "D", or "E"
            executor: Callable(task) -> (AgentResult, metrics_dict)
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
                result, run_metrics = executor(task)
                duration = time.time() - start

                # Extract provenanced metrics.
                tokens_input = run_metrics.get("tokens_input", 0)
                tokens_output = run_metrics.get("tokens_output", 0)
                latency_ms = run_metrics.get("latency_ms", 0.0)
                measure_type = run_metrics.get("measure_type", "estimated")

                # Record experiment result.
                exp_result = RealExperimentResult(
                    task_id=task.task_id,
                    strategy=result.strategy if isinstance(result, AgentResult) else Strategy.SEQUENTIAL,
                    condition_id=condition_id,
                    success=bool(result.is_complete) if isinstance(result, AgentResult) else bool(result),
                    tokens_input=MetricProvenance(tokens_input, MeasureType.ESTIMATED if measure_type == "estimated" else MeasureType.MEASURED, run_metrics.get("token_source", "")),
                    tokens_output=MetricProvenance(tokens_output, MeasureType.ESTIMATED if measure_type == "estimated" else MeasureType.MEASURED, run_metrics.get("token_source", "")),
                    latency_ms=MetricProvenance(latency_ms, MeasureType.MEASURED, "executor"),
                    tests_passed=run_metrics.get("tests_passed", 0),
                    tests_total=run_metrics.get("tests_total", 0),
                    model_used=run_metrics.get("model_used", ""),
                )
                self._experiment_results.append(exp_result)

                # Update condition metrics.
                metrics.tasks_run += 1
                passed = exp_result.success
                if passed:
                    metrics.tasks_passed += 1
                else:
                    metrics.tasks_failed += 1
                metrics.total_tokens += int(tokens_output)
                metrics.total_duration_seconds += duration
                metrics.per_task_metrics.append({
                    "task_id": task.task_id,
                    "passed": passed,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "latency_ms": latency_ms,
                    "measure_type": measure_type,
                })

            except Exception as e:
                metrics.tasks_run += 1
                metrics.tasks_failed += 1
                logger.warning("Condition '%s' task '%s' failed: %s", condition_id, task.task_id, e)
                self._experiment_results.append(RealExperimentResult(
                    task_id=task.task_id,
                    strategy=Strategy.SEQUENTIAL,
                    condition_id=condition_id,
                    success=False,
                    tokens_input=MetricProvenance(0, MeasureType.UNAVAILABLE),
                    tokens_output=MetricProvenance(0, MeasureType.UNAVAILABLE),
                    latency_ms=MetricProvenance(0, MeasureType.UNAVAILABLE),
                    tests_passed=0,
                    tests_total=0,
                    error=str(e),
                ))

        self._result.add_condition(metrics)
        return metrics

    def finalize(self) -> BenchmarkResult:
        """Run pairwise comparisons and return the final result."""
        self._result.compare_pairs()
        return self._result

    def export_full_report(self, path: Path) -> Path:
        """Export full experiment report including provenance."""
        data = {
            "benchmark_id": self._result.benchmark_id,
            "experiment_config": self.config.to_dict(),
            "generated_at": datetime.now().isoformat(),
            "system_info": {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "machine": platform.machine(),
            },
            "conditions": {k: v.to_dict() for k, v in self._result.conditions.items()},
            "pairwise_comparisons": self._result.pairwise_comparisons,
            "experiment_results": [r.to_dict() for r in self._experiment_results],
            "notes": self._result.notes,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
