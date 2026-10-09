"""Phase 5 Tests — Dataset Builder + JSONL Export

Tests for:
- DatasetBuilder SFT example creation
- Preference dataset building
- JSONL export
- Manifest generation
- Statistics computation
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from experiments.generation.dataset_builder import DatasetBuilder, DatasetExample, DatasetManifest
from experiments.generation.schemas import GeneratedTask
from experiments.runner import ExperimentResult, ValidationResult
from experiments.validation.schemas import FailureRecord


class TestDatasetExample:
    """Tests for DatasetExample schema."""

    def test_example_creation(self):
        """Test creating a dataset example."""
        example = DatasetExample(
            conversation=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ],
            tags=["test"],
        )
        assert len(example.conversation) == 2
        assert example.tags == ["test"]

    def test_example_serialization(self):
        """Test example serialization."""
        example = DatasetExample(
            conversation=[{"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}],
            metadata={"key": "value"},
            tags=["tag1"],
        )
        d = example.to_dict()
        assert d["conversation"][0]["role"] == "user"
        assert d["metadata"]["key"] == "value"

    def test_example_from_dict(self):
        """Test example deserialization."""
        data = {
            "conversation": [{"role": "user", "content": "Test"}],
            "metadata": {},
            "tags": [],
        }
        example = DatasetExample.from_dict(data)
        assert len(example.conversation) == 1


class TestDatasetManifest:
    """Tests for DatasetManifest schema."""

    def test_manifest_creation(self):
        """Test creating a dataset manifest."""
        manifest = DatasetManifest(
            dataset_id="test_ds",
            version="1.0.0",
            example_count=100,
            domains={"math": 50, "physics": 50},
            difficulty_distribution={"2": 30, "3": 70},
            config_snapshot={},
        )
        assert manifest.dataset_id == "test_ds"
        assert manifest.example_count == 100

    def test_manifest_serialization(self):
        """Test manifest serialization."""
        manifest = DatasetManifest(
            dataset_id="test_ds",
            version="1.0.0",
            example_count=50,
            domains={"math": 25},
            difficulty_distribution={"3": 25},
            config_snapshot={},
        )
        d = manifest.to_dict()
        assert d["dataset_id"] == "test_ds"
        assert d["example_count"] == 50

    def test_manifest_from_dict(self):
        """Test manifest deserialization."""
        data = {
            "dataset_id": "test_ds",
            "version": "1.0.0",
            "example_count": 100,
            "domains": {"math": 50},
            "difficulty_distribution": {"2": 50},
        }
        manifest = DatasetManifest.from_dict(data)
        assert manifest.dataset_id == "test_ds"
        assert manifest.example_count == 100


class TestDatasetBuilder:
    """Tests for DatasetBuilder."""

    def test_builder_initialization(self):
        """Test builder initialization."""
        builder = DatasetBuilder()
        assert builder.dataset_version == "1.0.0"

    def test_build_sft_examples(self):
        """Test building SFT examples from results."""
        builder = DatasetBuilder()

        # Create valid result
        result = ExperimentResult(
            run_id="run_1",
            task_id="task_1",
            experiment_id="exp_1",
            generation_id="gen_1",
            config={},
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer="42",
            ground_truth=42,
            validation_result=ValidationResult(valid=True, score=1.0),
        )

        examples = builder.build_sft([result])
        assert len(examples) == 1
        assert examples[0].tags == ["synthetic", "validated"]

    def test_build_sft_filters_invalid(self):
        """Test that invalid results are filtered."""
        builder = DatasetBuilder()

        valid_result = ExperimentResult(
            run_id="run_1",
            task_id="task_1",
            experiment_id="exp_1",
            generation_id="gen_1",
            config={},
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer="42",
            ground_truth=42,
            validation_result=ValidationResult(valid=True, score=1.0),
        )

        invalid_result = ExperimentResult(
            run_id="run_2",
            task_id="task_2",
            experiment_id="exp_1",
            generation_id="gen_1",
            config={},
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer=None,
            ground_truth=42,
            validation_result=ValidationResult(valid=False, score=0.0),
        )

        examples = builder.build_sft([valid_result, invalid_result])
        assert len(examples) == 1

    def test_build_preference_examples(self):
        """Test building preference examples."""
        builder = DatasetBuilder()

        # Create results with different scores
        chosen_result = ExperimentResult(
            run_id="run_1",
            task_id="task_1",
            experiment_id="exp_1",
            generation_id="gen_1",
            config={},
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer="Correct",
            ground_truth="Correct",
            validation_result=ValidationResult(valid=True, score=0.95),
        )

        rejected_result = ExperimentResult(
            run_id="run_2",
            task_id="task_1",
            experiment_id="exp_1",
            generation_id="gen_1",
            config={},
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer="Wrong",
            ground_truth="Correct",
            validation_result=ValidationResult(valid=False, score=0.2),
        )

        examples = builder.build_preference([chosen_result, rejected_result])
        assert len(examples) == 1

    def test_export_jsonl(self):
        """Test JSONL export."""
        builder = DatasetBuilder()
        examples = [
            DatasetExample(
                conversation=[{"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}],
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            path = Path(f.name)

        try:
            builder.export_jsonl(examples, str(path))
            assert path.exists()

            # Verify content
            with open(path, "r", encoding="utf-8") as f:
                line = f.readline()
                data = json.loads(line)
                assert "conversation" in data
        finally:
            path.unlink(missing_ok=True)

    def test_export_json(self):
        """Test JSON export."""
        builder = DatasetBuilder()
        examples = [
            DatasetExample(
                conversation=[{"role": "user", "content": "Q"}],
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            builder.export_json(examples, str(path))
            assert path.exists()

            # Verify content
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert "examples" in data
                assert len(data["examples"]) == 1
        finally:
            path.unlink(missing_ok=True)

    def test_compute_statistics(self):
        """Test statistics computation."""
        builder = DatasetBuilder()

        results = [
            ExperimentResult(
                run_id="run_1",
                task_id="task_1",
                experiment_id="exp_1",
                generation_id="gen_1",
                config={},
                routing_decision={},
                workers_used=[],
                tools_used=[],
                answer="42",
                ground_truth=42,
                validation_result=ValidationResult(valid=True, score=1.0),
            ),
            ExperimentResult(
                run_id="run_2",
                task_id="task_2",
                experiment_id="exp_1",
                generation_id="gen_1",
                config={},
                routing_decision={},
                workers_used=[],
                tools_used=[],
                answer=None,
                ground_truth=42,
                validation_result=ValidationResult(valid=False, score=0.0),
            ),
        ]

        stats = builder.compute_statistics(results)
        assert stats["total_examples"] == 2
        assert stats["valid_examples"] == 1
        assert stats["invalid_examples"] == 1
        assert stats["pass_rate"] == 0.5

    def test_create_manifest(self):
        """Test manifest creation."""
        builder = DatasetBuilder()

        results = [
            ExperimentResult(
                run_id="run_1",
                task_id="task_1",
                experiment_id="exp_1",
                generation_id="gen_1",
                config={},
                routing_decision={},
                workers_used=[],
                tools_used=[],
                answer="42",
                ground_truth=42,
                validation_result=ValidationResult(valid=True, score=1.0),
            ),
        ]

        manifest = builder.create_manifest(results, config_snapshot={"seed": 42})
        assert manifest.dataset_id.startswith("dataset_")
        assert manifest.example_count == 1
        assert manifest.config_snapshot["seed"] == 42


class TestEndToEndDataset:
    """End-to-end tests for dataset generation."""

    def test_full_pipeline_generation_to_export(self):
        """Test full pipeline from task generation to dataset export."""
        from experiments.generation.task_generator import TaskGenerator

        # Generate tasks
        generator = TaskGenerator(seed=42)
        tasks = generator.generate_batch(
            domain="math",
            difficulty_range=(1, 3),
            count=5,
        )

        # Run through experiment pipeline
        from experiments.runner import ExperimentRunner
        runner = ExperimentRunner()
        results = []
        for task in tasks:
            result = runner.run_task(task)
            results.append(result)

        # Build dataset
        builder = DatasetBuilder()
        examples = builder.build_sft(results)

        # Export to JSONL
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            path = Path(f.name)

        try:
            manifest = builder.create_manifest(results)
            builder.export_jsonl(examples, str(path), manifest)
            assert path.exists()
        finally:
            path.unlink(missing_ok=True)

    def test_dataset_with_metadata(self):
        """Test dataset with full provenance metadata."""
        from experiments.generation.task_generator import TaskGenerator
        from experiments.runner import ExperimentRunner

        generator = TaskGenerator(seed=42)
        task = generator.generate(domain="math", difficulty=2)

        runner = ExperimentRunner()
        result = runner.run_task(task)

        builder = DatasetBuilder()
        # Include invalid results for this test
        examples = builder.build_sft([result], include_metadata=True)

        # Result may be invalid if no answer computed, check accordingly
        if result.is_successful:
            assert len(examples) == 1
            example = examples[0]
            assert "experiment_id" in example.metadata
            assert "task_id" in example.metadata


class TestDatasetIntegration:
    """Integration tests for dataset building."""

    def test_multiple_domains(self):
        """Test building dataset from multiple domains."""
        builder = DatasetBuilder()

        results = []
        for domain in ["math", "physics", "chemistry"]:
            result = ExperimentResult(
                run_id=f"run_{domain}",
                task_id=f"task_{domain}",
                experiment_id="exp_multi",
                generation_id="gen_1",
                config={"domain": domain},
                routing_decision={},
                workers_used=[],
                tools_used=[],
                answer="answer",
                ground_truth="answer",
                validation_result=ValidationResult(valid=True, score=1.0),
            )
            results.append(result)

        examples = builder.build_sft(results)
        assert len(examples) == 3

    def test_large_dataset_export(self):
        """Test exporting a large dataset."""
        builder = DatasetBuilder()

        # Create 100 examples
        examples = []
        for i in range(100):
            example = DatasetExample(
                conversation=[
                    {"role": "user", "content": f"Question {i}"},
                    {"role": "assistant", "content": f"Answer {i}"},
                ],
                tags=["synthetic"],
            )
            examples.append(example)

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            path = Path(f.name)

        try:
            manifest = DatasetManifest(
                dataset_id="large_ds",
                version="1.0.0",
                example_count=100,
                domains={"math": 100},
                difficulty_distribution={"3": 100},
                config_snapshot={},
            )
            builder.export_jsonl(examples, str(path), manifest)
            assert path.exists()

            # Verify line count
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                assert len(lines) == 100
        finally:
            path.unlink(missing_ok=True)
