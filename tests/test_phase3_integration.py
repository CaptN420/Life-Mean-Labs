"""Phase 3 Tests — Experiment Runner Integration

Tests for:
- ExperimentRunner basic execution
- Routing integration with SmartRouter
- ToolWorker integration
- Validation logic
- Result provenance tracking
"""

from __future__ import annotations

import pytest

from experiments.context import ExperimentContext
from experiments.generation.schemas import GeneratedTask
from experiments.generation.task_generator import TaskGenerator
from experiments.runner import ExperimentResult, ExperimentRunner, ValidationResult


class TestExperimentResult:
    """Tests for ExperimentResult schema."""

    def test_result_creation(self):
        """Test creating an experiment result."""
        result = ExperimentResult(
            run_id="run_123",
            task_id="task_456",
            experiment_id="exp_789",
            generation_id="gen_001",
            config={"deterministic": True},
            routing_decision={"selected": ["tool_worker"]},
            workers_used=["tool_worker"],
            tools_used=["math_calculation"],
            answer=42,
            ground_truth=42,
            validation_result=ValidationResult(valid=True, score=1.0),
        )

        assert result.run_id == "run_123"
        assert result.is_valid is True
        assert result.is_successful is True

    def test_result_serialization(self):
        """Test result serialization."""
        result = ExperimentResult(
            run_id="run_123",
            task_id="task_456",
            experiment_id="exp_789",
            generation_id="gen_001",
            config={"seed": 42},
            routing_decision={"selected": ["tool_worker"]},
            workers_used=["tool_worker"],
            tools_used=["math_calculation"],
            answer=10,
            ground_truth=10,
        )

        d = result.to_dict()
        assert d["run_id"] == "run_123"
        assert d["answer"] == 10
        assert d["ground_truth"] == 10

    def test_result_invalid(self):
        """Test invalid result."""
        result = ExperimentResult(
            run_id="run_123",
            task_id="task_456",
            experiment_id="exp_789",
            generation_id="gen_001",
            config={},
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer=None,
        )

        assert result.is_valid is False
        assert result.is_successful is False


class TestValidationResult:
    """Tests for ValidationResult schema."""

    def test_valid_result(self):
        """Test valid validation result."""
        vr = ValidationResult(
            valid=True,
            score=1.0,
            method="deterministic",
        )
        assert vr.valid is True
        assert vr.score == 1.0

    def test_invalid_result(self):
        """Test invalid validation result."""
        vr = ValidationResult(
            valid=False,
            score=0.0,
            method="llm_judge",
            error="Answer mismatch",
        )
        assert vr.valid is False
        assert vr.error == "Answer mismatch"

    def test_result_serialization(self):
        """Test validation result serialization."""
        vr = ValidationResult(
            valid=True,
            score=0.95,
            method="hybrid",
            evidence={"comparison": "pass"},
        )
        d = vr.to_dict()
        assert d["valid"] is True
        assert d["score"] == 0.95


class TestExperimentRunnerBasic:
    """Tests for basic ExperimentRunner functionality."""

    def test_runner_initialization(self):
        """Test runner initialization."""
        runner = ExperimentRunner()
        assert runner.event_bus is not None
        assert len(runner.get_results()) == 0

    def test_runner_with_config(self):
        """Test runner with configuration."""
        config = {"deterministic": True, "seed": 123}
        runner = ExperimentRunner(config=config)
        assert runner.config["deterministic"] is True

    def test_get_statistics_empty(self):
        """Test statistics with no results."""
        runner = ExperimentRunner()
        stats = runner.get_statistics()
        assert stats["total_runs"] == 0
        assert stats["validation_pass_rate"] == 0.0


class TestExperimentRunnerExecution:
    """Tests for task execution through the pipeline."""

    def test_run_single_task(self):
        """Test running a single task."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        task = generator.generate(
            domain="math",
            difficulty=2,
            reasoning_type="calculation",
        )

        context = ExperimentContext(
            domain="math",
            difficulty=2,
        )

        result = runner.run_task(task, context)

        assert result.task_id == task.task_id
        assert result.experiment_id == context.experiment_id
        assert result.generation_id == context.generation_id
        assert result.run_id is not None

    def test_run_batch_tasks(self):
        """Test running a batch of tasks."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        tasks = generator.generate_batch(
            domain="math",
            difficulty_range=(1, 3),
            count=5,
        )

        results = runner.run_batch(tasks)

        assert len(results) == 5
        for result in results:
            assert result.task_id is not None

    def test_result_has_provenance(self):
        """Test that results have provenance tracking."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        task = generator.generate(
            domain="math",
            difficulty=2,
        )

        context = ExperimentContext(
            domain="math",
            difficulty=2,
        )

        result = runner.run_task(task, context)

        assert result.provenance is not None
        assert result.provenance.experiment_id == context.experiment_id
        assert result.provenance.task_id == task.task_id


class TestExperimentRunnerRouting:
    """Tests for routing integration with SmartRouter."""

    def test_routing_decision_contains_selected(self):
        """Test that routing decision contains selected workers."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        task = generator.generate(
            domain="math",
            difficulty=2,
        )

        context = ExperimentContext()
        result = runner.run_task(task, context)

        assert "selected" in result.routing_decision
        assert len(result.routing_decision["selected"]) > 0

    def test_routing_records_workers_used(self):
        """Test that workers used are recorded."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        task = generator.generate(
            domain="math",
            difficulty=2,
        )

        context = ExperimentContext()
        result = runner.run_task(task, context)

        assert len(result.workers_used) > 0


class TestExperimentRunnerValidation:
    """Tests for validation logic."""

    def test_validation_with_matching_answer(self):
        """Test validation when answer matches ground truth."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        task = generator.generate(
            domain="math",
            difficulty=2,
        )

        # Manually create result with correct answer and validation
        result = ExperimentResult(
            run_id="run_test",
            task_id=task.task_id,
            experiment_id="exp_test",
            generation_id="gen_test",
            config={},
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer=task.ground_truth,
            ground_truth=task.ground_truth,
            validation_result=ValidationResult(valid=True, score=1.0),
        )

        assert result.is_valid is True

    def test_validation_with_wrong_answer(self):
        """Test validation when answer is wrong."""
        task = GeneratedTask(
            domain="math",
            description="Calculate 5 + 3",
            ground_truth=8,
        )

        vr = ValidationResult(valid=False, score=0.0)
        assert vr.valid is False


class TestExperimentRunnerProvenance:
    """Tests for provenance tracking."""

    def test_provenance_chain_complete(self):
        """Test complete provenance chain."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        task = generator.generate(
            domain="math",
            difficulty=2,
        )

        context = ExperimentContext(
            domain="math",
            difficulty=2,
            seed=42,
        )

        result = runner.run_task(task, context)

        # Verify full traceability
        prov = result.provenance
        assert prov.experiment_id == context.experiment_id
        assert prov.generation_id == context.generation_id
        assert prov.task_id == task.task_id
        assert prov.run_id == result.run_id
        assert prov.generator_version == task.generator_version
        assert prov.seed == task.seed

    def test_provenance_records_routing(self):
        """Test that provenance records routing decision."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        task = generator.generate(
            domain="math",
            difficulty=2,
        )

        context = ExperimentContext()
        result = runner.run_task(task, context)

        prov = result.provenance
        assert prov.routing_decision is not None


class TestExperimentRunnerStatistics:
    """Tests for statistics tracking."""

    def test_statistics_after_execution(self):
        """Test statistics after running tasks."""
        generator = TaskGenerator(seed=42)
        runner = ExperimentRunner()

        # Run multiple tasks
        for i in range(5):
            task = generator.generate(
                domain="math",
                difficulty=2,
            )
            context = ExperimentContext()
            runner.run_task(task, context)

        stats = runner.get_statistics()
        assert stats["total_runs"] == 5
        assert stats["successful_runs"] >= 0
        assert 0.0 <= stats["validation_pass_rate"] <= 1.0


class TestEndToEndPipeline:
    """End-to-end tests for the experiment pipeline."""

    def test_full_pipeline_generation_to_validation(self):
        """Test full pipeline from generation to validation."""
        # Generate tasks
        generator = TaskGenerator(seed=42)
        tasks = generator.generate_batch(
            domain="math",
            difficulty_range=(1, 3),
            count=3,
        )

        # Run through experiment pipeline
        runner = ExperimentRunner()
        context = ExperimentContext(domain="math", difficulty=2)
        results = runner.run_batch(tasks, context)

        # Verify all tasks executed
        assert len(results) == 3

        # Verify provenance for each result
        for result in results:
            assert result.provenance is not None
            assert result.provenance.task_id in [t.task_id for t in tasks]

    def test_pipeline_preserves_config(self):
        """Test that experiment configuration is preserved."""
        config = {
            "deterministic": True,
            "llm_reasoning": False,
            "seed": 123,
        }
        runner = ExperimentRunner(config=config)

        generator = TaskGenerator(seed=42)
        task = generator.generate(domain="math", difficulty=2)
        context = ExperimentContext()

        result = runner.run_task(task, context)

        assert result.config["deterministic"] is True
        assert result.config["seed"] == 123
