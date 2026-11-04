"""Model trainer integration for the ADSG pipeline.

Design doc §8, §37-§40: training is SEPARATE from generation.
This module provides:
- A Trainer that consumes exported JSONL datasets
- Model artifact serialization (weights/metrics/config)
- Integration with ModelRegistry for candidate lifecycle
- Held-out benchmark evaluation (never trained on benchmarks)

Key principle: The trainer does NOT modify the dataset. It only reads
from exported paths and writes model artifacts to a separate directory.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Trainer")


@dataclass
class TrainingConfig:
    """Configuration for a training run."""

    dataset_path: str
    model_name: str = ""
    epochs: int = 1
    learning_rate: float = 0.001
    batch_size: int = 32
    max_steps: Optional[int] = None
    seed: int = 42
    extra_args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "model_name": self.model_name,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "max_steps": self.max_steps,
            "seed": self.seed,
            "extra_args": self.extra_args,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingConfig":
        return cls(
            dataset_path=data["dataset_path"],
            model_name=data.get("model_name", ""),
            epochs=data.get("epochs", 1),
            learning_rate=data.get("learning_rate", 0.001),
            batch_size=data.get("batch_size", 32),
            max_steps=data.get("max_steps"),
            seed=data.get("seed", 42),
            extra_args=data.get("extra_args", {}),
        )


@dataclass
class TrainingResult:
    """Result of a training run."""

    run_id: str
    model_name: str
    dataset_path: str
    config: TrainingConfig
    metrics: Dict[str, float] = field(default_factory=dict)
    artifacts_path: Optional[str] = None
    error: Optional[str] = None
    steps_completed: int = 0
    seed: int = 42
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_name": self.model_name,
            "dataset_path": self.dataset_path,
            "config": self.config.to_dict(),
            "metrics": dict(self.metrics),
            "artifacts_path": self.artifacts_path,
            "error": self.error,
            "steps_completed": self.steps_completed,
            "timestamp": self.timestamp,
        }


@dataclass
class ModelArtifact:
    """Serialized model artifact for registry integration."""

    artifact_id: str = field(default_factory=lambda: f"artifact_{uuid.uuid4().hex[:8]}")
    model_name: str = ""
    training_run_id: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    dataset_id: Optional[str] = None
    path: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "model_name": self.model_name,
            "training_run_id": self.training_run_id,
            "metrics": dict(self.metrics),
            "config_snapshot": self.config_snapshot,
            "dataset_id": self.dataset_id,
            "path": self.path,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelArtifact":
        return cls(
            artifact_id=data.get("artifact_id", f"artifact_{uuid.uuid4().hex[:8]}"),
            model_name=data.get("model_name", ""),
            training_run_id=data.get("training_run_id", ""),
            metrics=data.get("metrics", {}),
            config_snapshot=data.get("config_snapshot", {}),
            dataset_id=data.get("dataset_id"),
            path=data.get("path", ""),
            created_at=data.get("created_at", time.time()),
        )


class Trainer:
    """Trains models from exported datasets.

    Training is separated from generation: the trainer only reads from
    exported JSONL paths and never mutates the source dataset.
    """

    def __init__(self, output_dir: str = "artifacts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._runs: Dict[str, TrainingResult] = {}
        self._artifacts: Dict[str, ModelArtifact] = {}

    @property
    def runs(self) -> Dict[str, TrainingResult]:
        return dict(self._runs)

    @property
    def artifacts(self) -> Dict[str, ModelArtifact]:
        return dict(self._artifacts)

    def train(
        self,
        config: TrainingConfig,
        simulate: bool = True,
        seed: Optional[int] = None,
    ) -> TrainingResult:
        """Run a training iteration.

        Args:
            config: Training configuration
            simulate: If True, simulate metrics (no real training).
                If False, would run actual training (future integration).
            seed: Override seed for reproducibility.

        Returns:
            TrainingResult with metrics and artifact path.
        """
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        result = TrainingResult(
            run_id=run_id,
            model_name=config.model_name,
            dataset_path=config.dataset_path,
            config=config,
            seed=seed if seed is not None else config.seed,
        )

        if simulate:
            # Simulate training metrics based on dataset properties
            result.metrics = self._simulate_metrics(config)
            result.steps_completed = config.epochs * 100
        else:
            # Real training integration would go here
            raise NotImplementedError("Real training not yet integrated")

        # Save artifact
        artifact = self._save_artifact(run_id, result)
        result.artifacts_path = artifact.path

        self._runs[run_id] = result
        self._artifacts[artifact.artifact_id] = artifact

        logger.info(
            "Training complete: %s (metrics=%s)", run_id, result.metrics
        )
        return result

    def _simulate_metrics(self, config: TrainingConfig) -> Dict[str, float]:
        """Simulate training metrics for testing.

        In production, this would be replaced with real training output.
        Metrics are deterministic based on dataset path and config seed.
        """
        import hashlib

        # Create a deterministic hash from dataset path + config
        hash_input = f"{config.dataset_path}:{config.seed}:{config.epochs}"
        h = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)

        # Simulate accuracy between 0.6 and 0.95
        base_accuracy = 0.6 + (h % 3500) / 10000.0
        # Improve with more epochs
        epoch_bonus = min(0.1, config.epochs * 0.02)
        accuracy = min(0.99, base_accuracy + epoch_bonus)

        return {
            "accuracy": round(accuracy, 4),
            "loss": round(max(0.01, 1.0 - accuracy), 4),
            "f1": round(accuracy * 0.95, 4),
        }

    def _save_artifact(self, run_id: str, result: TrainingResult) -> ModelArtifact:
        """Save model artifact to disk."""
        artifact = ModelArtifact(
            model_name=result.model_name,
            training_run_id=run_id,
            metrics=result.metrics,
            config_snapshot=result.config.to_dict(),
            dataset_id=self._extract_dataset_id(result.dataset_path),
            path=str(self.output_dir / f"{run_id}.json"),
        )

        with open(artifact.path, "w") as f:
            json.dump(artifact.to_dict(), f, indent=2)

        logger.info("Saved artifact %s to %s", artifact.artifact_id, artifact.path)
        return artifact

    def _extract_dataset_id(self, dataset_path: str) -> Optional[str]:
        """Extract dataset ID from path."""
        try:
            path = Path(dataset_path)
            if path.suffix == ".jsonl":
                return path.stem
            return None
        except Exception:
            return None

    def get_run(self, run_id: str) -> Optional[TrainingResult]:
        """Get a training run by ID."""
        return self._runs.get(run_id)

    def get_artifact(self, artifact_id: str) -> Optional[ModelArtifact]:
        """Get a model artifact by ID."""
        return self._artifacts.get(artifact_id)

    def list_runs(self) -> List[TrainingResult]:
        """List all training runs."""
        return list(self._runs.values())

    def list_artifacts(self) -> List[ModelArtifact]:
        """List all model artifacts."""
        return list(self._artifacts.values())

    def evaluate_on_benchmark(
        self,
        artifact_id: str,
        benchmark_name: str,
        metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        """Evaluate an artifact on a held-out benchmark.

        Args:
            artifact_id: Model artifact to evaluate
            benchmark_name: Name of the benchmark
            metrics: Computed metrics

        Returns:
            Benchmark result dict
        """
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise KeyError(f"Artifact {artifact_id} not found")

        return {
            "artifact_id": artifact_id,
            "benchmark_name": benchmark_name,
            "metrics": metrics,
            "timestamp": time.time(),
        }
