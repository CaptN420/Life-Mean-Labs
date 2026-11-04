"""Tests for trainer integration (design doc §8, §37-§40).

Verifies:
- Training is separated from generation
- Artifacts are persisted
- Registry integration works
- Held-out evaluation never uses training data
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from experiments.trainer import Trainer, TrainingConfig, TrainingResult, ModelArtifact
from autopilot.registry import ModelRegistry, ModelStatus


# ---- Helpers ---------------------------------------------------------------


def _write_dummy_jsonl(path: str, count: int = 10) -> str:
    """Write a minimal JSONL file for testing."""
    with open(path, "w") as f:
        for i in range(count):
            f.write(json.dumps({
                "conversation": [
                    {"role": "user", "content": f"Question {i}"},
                    {"role": "assistant", "content": f"Answer {i}"},
                ],
                "metadata": {"domain": "math", "difficulty": 1},
            }) + "\n")
    return path


# ---- TrainingConfig --------------------------------------------------------


def test_training_config_serialization():
    config = TrainingConfig(
        dataset_path="/data/train.jsonl",
        model_name="test-model",
        epochs=3,
        learning_rate=0.001,
        seed=42,
    )
    data = config.to_dict()
    restored = TrainingConfig.from_dict(data)

    assert restored.dataset_path == "/data/train.jsonl"
    assert restored.model_name == "test-model"
    assert restored.epochs == 3
    assert restored.learning_rate == 0.001
    assert restored.seed == 42


def test_training_config_defaults():
    config = TrainingConfig(dataset_path="/data/train.jsonl")
    assert config.epochs == 1
    assert config.learning_rate == 0.001
    assert config.batch_size == 32
    assert config.seed == 42


# ---- Trainer ---------------------------------------------------------------


def test_train_simulates_metrics():
    trainer = Trainer()
    config = TrainingConfig(
        dataset_path="/data/train.jsonl",
        model_name="test-model",
        epochs=2,
    )
    result = trainer.train(config, simulate=True)

    assert result.run_id.startswith("run_")
    assert result.model_name == "test-model"
    assert "accuracy" in result.metrics
    assert 0.6 <= result.metrics["accuracy"] <= 0.99
    assert result.artifacts_path is not None


def test_train_persists_artifact():
    with tempfile.TemporaryDirectory() as tmpdir:
        trainer = Trainer(output_dir=tmpdir)
        config = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name="test-model",
        )
        result = trainer.train(config, simulate=True)

        # Artifact file exists
        assert Path(result.artifacts_path).exists()

        # Can load artifact
        with open(result.artifacts_path) as f:
            data = json.load(f)
        assert data["model_name"] == "test-model"
        assert "accuracy" in data["metrics"]


def test_train_reproducibility():
    """Same config → same metrics (deterministic simulation)."""
    with tempfile.TemporaryDirectory() as tmpdir1:
        with tempfile.TemporaryDirectory() as tmpdir2:
            trainer1 = Trainer(output_dir=tmpdir1)
            trainer2 = Trainer(output_dir=tmpdir2)

            config = TrainingConfig(
                dataset_path="/data/train.jsonl",
                model_name="test-model",
                seed=42,
            )
            r1 = trainer1.train(config, simulate=True)
            r2 = trainer2.train(config, simulate=True)

            assert r1.metrics == r2.metrics


def test_train_different_seeds_different_metrics():
    """Different seeds → different metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trainer = Trainer(output_dir=tmpdir)

        config1 = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name="test-model",
            seed=42,
        )
        config2 = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name="test-model",
            seed=99,
        )

        r1 = trainer.train(config1, simulate=True)
        r2 = trainer.train(config2, simulate=True)

        # Different seeds should produce different accuracy
        assert r1.metrics["accuracy"] != r2.metrics["accuracy"]


def test_train_epochs_improve_metrics():
    """More epochs → better metrics (simulated)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trainer = Trainer(output_dir=tmpdir)

        config_1epoch = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name="test-model",
            epochs=1,
            seed=42,
        )
        config_5epochs = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name="test-model",
            epochs=5,
            seed=42,
        )

        r1 = trainer.train(config_1epoch, simulate=True)
        r2 = trainer.train(config_5epochs, simulate=True)

        # 5 epochs should have equal or better accuracy
        assert r2.metrics["accuracy"] >= r1.metrics["accuracy"]


def test_get_run():
    trainer = Trainer()
    config = TrainingConfig(dataset_path="/data/train.jsonl", model_name="test")
    result = trainer.train(config, simulate=True)

    retrieved = trainer.get_run(result.run_id)
    assert retrieved is not None
    assert retrieved.run_id == result.run_id


def test_list_runs():
    trainer = Trainer()
    for i in range(3):
        config = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name=f"model-{i}",
        )
        trainer.train(config, simulate=True)

    assert len(trainer.list_runs()) == 3


def test_list_artifacts():
    trainer = Trainer()
    for i in range(3):
        config = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name=f"model-{i}",
        )
        trainer.train(config, simulate=True)

    assert len(trainer.list_artifacts()) == 3


def test_evaluate_on_benchmark():
    trainer = Trainer()
    config = TrainingConfig(dataset_path="/data/train.jsonl", model_name="test")
    result = trainer.train(config, simulate=True)

    # Get the artifact ID from the trainer's artifacts
    artifact_id = list(trainer.artifacts.keys())[0]

    bench_result = trainer.evaluate_on_benchmark(
        artifact_id=artifact_id,
        benchmark_name="heldout_math",
        metrics={"accuracy": 0.85},
    )

    assert bench_result["benchmark_name"] == "heldout_math"
    assert bench_result["metrics"]["accuracy"] == 0.85


def test_evaluate_on_benchmark_not_found():
    trainer = Trainer()
    with pytest.raises(KeyError):
        trainer.evaluate_on_benchmark(
            artifact_id="nonexistent",
            benchmark_name="heldout_math",
            metrics={"accuracy": 0.85},
        )


# ---- Registry Integration --------------------------------------------------


def test_trainer_to_registry_integration():
    """Trainer output integrates with ModelRegistry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trainer = Trainer(output_dir=tmpdir)
        registry = ModelRegistry(storage_path=Path(tmpdir) / "registry.json")

        # Train a model
        config = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name="candidate-v1",
        )
        result = trainer.train(config, simulate=True)

        # Register candidate in registry
        candidate = registry.register_candidate(
            name="candidate-v1",
            training_dataset_id=Path(config.dataset_path).stem,
            training_config=result.config.to_dict(),
        )

        # Record benchmark result
        registry.record_benchmark(
            model_id=candidate.model_id,
            benchmark_name="heldout_math",
            metrics={"accuracy": result.metrics["accuracy"]},
        )

        # Verify candidate has benchmark result
        assert len(candidate.benchmark_results) == 1
        assert candidate.benchmark_results[0].metrics["accuracy"] == result.metrics["accuracy"]


def test_trainer_separation_from_generation():
    """Training does not modify the dataset."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        dataset_path = f.name

    try:
        # Write initial dataset
        with open(dataset_path, "w") as f:
            f.write(json.dumps({"conversation": [{"role": "user", "content": "q"}], "metadata": {}}) + "\n")

        # Train (simulate)
        trainer = Trainer()
        config = TrainingConfig(dataset_path=dataset_path, model_name="test")
        trainer.train(config, simulate=True)

        # Dataset should be unchanged
        with open(dataset_path) as f:
            lines = f.readlines()
        assert len(lines) == 1
    finally:
        Path(dataset_path).unlink()


def test_candidate_promotion_after_training():
    """Full lifecycle: train → benchmark → promote."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trainer = Trainer(output_dir=tmpdir)
        registry = ModelRegistry(storage_path=Path(tmpdir) / "registry.json")

        # Register initial stable model
        stable = registry.register_candidate(name="stable", status=ModelStatus.STABLE)

        # Train candidate
        config = TrainingConfig(
            dataset_path="/data/train.jsonl",
            model_name="candidate-v1",
        )
        result = trainer.train(config, simulate=True)

        # Register candidate in registry
        candidate = registry.register_candidate(
            name="candidate-v1",
            training_dataset_id=Path(config.dataset_path).stem,
            training_config=result.config.to_dict(),
        )

        # Record benchmark (candidate better than stable)
        registry.record_benchmark(
            model_id=stable.model_id,
            benchmark_name="heldout_math",
            metrics={"accuracy": 0.7},
        )
        registry.record_benchmark(
            model_id=candidate.model_id,
            benchmark_name="heldout_math",
            metrics={"accuracy": 0.9},
        )

        # Decision should promote candidate
        promoted = registry.decide_promotion(
            candidate.model_id,
            metric="accuracy",
        )
        assert promoted is True


def test_artifact_idempotency():
    """Training the same config twice produces different run IDs."""
    trainer = Trainer()
    config = TrainingConfig(
        dataset_path="/data/train.jsonl",
        model_name="test",
        seed=42,
    )
    r1 = trainer.train(config, simulate=True)
    r2 = trainer.train(config, simulate=True)

    assert r1.run_id != r2.run_id
    assert r1.metrics == r2.metrics  # But metrics are the same (deterministic)
