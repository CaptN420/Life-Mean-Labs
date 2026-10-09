"""Phase 6 Tests — Experiment Layer

Tests for:
- Condition creation and serialization
- Study management with multiple conditions
- Run lifecycle (start, complete, fail)
- Result tracking and statistics
- ExperimentManager operations
"""

from __future__ import annotations

import pytest
import time

from experiments.config import ExperimentConfig
from experiments.experiment_layer import (
    Condition,
    ExperimentManager,
    Run,
    RunResult,
    Study,
)


class TestCondition:
    """Tests for Condition schema."""

    def test_condition_creation(self):
        """Test creating a condition."""
        config = ExperimentConfig(domain="math", num_tasks=50)
        condition = Condition(name="test", config=config)
        assert condition.name == "test"
        assert condition.config.domain == "math"

    def test_condition_serialization(self):
        """Test condition serialization."""
        config = ExperimentConfig(domain="physics", num_tasks=100)
        condition = Condition(
            name="physics_test",
            config=config,
            description="Physics experiment",
        )
        d = condition.to_dict()
        assert d["name"] == "physics_test"
        assert d["config"]["domain"] == "physics"

    def test_condition_from_dict(self):
        """Test condition deserialization."""
        data = {
            "name": "chem_test",
            "config": {"domain": "chemistry", "num_tasks": 75},
            "description": "Chemistry experiment",
        }
        condition = Condition.from_dict(data)
        assert condition.name == "chem_test"
        assert condition.config.domain == "chemistry"


class TestStudy:
    """Tests for Study schema."""

    def test_study_creation(self):
        """Test creating a study."""
        study = Study(title="Test Study", hypothesis="H1")
        assert study.title == "Test Study"
        assert study.hypothesis == "H1"
        assert len(study.conditions) == 0

    def test_add_condition(self):
        """Test adding conditions to a study."""
        study = Study(title="Test Study")
        config = ExperimentConfig(domain="math")
        study.add_condition(Condition(name="cond1", config=config))
        assert len(study.conditions) == 1
        assert study.get_condition("cond1") is not None

    def test_get_condition_not_found(self):
        """Test getting non-existent condition."""
        study = Study(title="Test Study")
        assert study.get_condition("nonexistent") is None

    def test_study_serialization(self):
        """Test study serialization."""
        config = ExperimentConfig(domain="math", num_tasks=100)
        study = Study(
            title="Math Study",
            hypothesis="H1: Deterministic > LLM",
        )
        study.add_condition(Condition(name="deterministic", config=config))

        d = study.to_dict()
        assert d["title"] == "Math Study"
        assert len(d["conditions"]) == 1
        assert d["conditions"][0]["name"] == "deterministic"

    def test_study_from_dict(self):
        """Test study deserialization."""
        data = {
            "title": "Physics Study",
            "hypothesis": "H1",
            "study_id": "study_123",
            "conditions": [
                {
                    "name": "cond1",
                    "config": {"domain": "physics"},
                    "description": "Test",
                }
            ],
        }
        study = Study.from_dict(data)
        assert study.study_id == "study_123"
        assert len(study.conditions) == 1


class TestRun:
    """Tests for Run schema."""

    def test_run_creation(self):
        """Test creating a run."""
        run = Run(study_id="study_1", condition_name="cond1")
        assert run.status == "pending"
        assert run.start_time is None

    def test_run_lifecycle(self):
        """Test run start and complete."""
        run = Run(study_id="study_1", condition_name="cond1")
        run.start()
        assert run.status == "running"
        assert run.start_time is not None

        time.sleep(0.01)
        run.complete()
        assert run.status == "completed"
        assert run.end_time is not None
        assert run.elapsed_seconds >= 0

    def test_run_fail(self):
        """Test run failure."""
        run = Run(study_id="study_1", condition_name="cond1")
        run.start()
        run.fail("Test error")
        assert run.status == "failed"

    def test_run_stats_empty(self):
        """Test stats with no results."""
        run = Run()
        assert run.success_rate == 0.0
        assert run.avg_score == 0.0

    def test_run_stats_with_results(self):
        """Test stats with results."""
        run = Run()
        run.add_result(RunResult(
            task_id="t1",
            experiment_id="exp_1",
            run_id="run_1",
            condition_name="cond1",
            success=True,
            score=0.9,
        ))
        run.add_result(RunResult(
            task_id="t2",
            experiment_id="exp_1",
            run_id="run_1",
            condition_name="cond1",
            success=False,
            score=0.3,
        ))

        assert run.success_rate == 0.5
        assert run.avg_score == 0.6

    def test_run_serialization(self):
        """Test run serialization."""
        run = Run(
            study_id="study_1",
            condition_name="cond1",
            status="completed",
        )
        run.add_result(RunResult(
            task_id="t1",
            experiment_id="exp_1",
            run_id=run.run_id,
            condition_name="cond1",
            success=True,
            score=0.95,
        ))

        d = run.to_dict()
        assert d["study_id"] == "study_1"
        assert d["num_results"] == 1
        assert d["success_rate"] == 1.0


class TestRunResult:
    """Tests for RunResult schema."""

    def test_result_creation(self):
        """Test creating a result."""
        result = RunResult(
            task_id="task_1",
            experiment_id="exp_1",
            run_id="run_1",
            condition_name="cond1",
            success=True,
            score=0.95,
        )
        assert result.task_id == "task_1"
        assert result.success is True

    def test_result_serialization(self):
        """Test result serialization."""
        result = RunResult(
            task_id="task_1",
            experiment_id="exp_1",
            run_id="run_1",
            condition_name="cond1",
            success=True,
            answer="42",
            ground_truth="42",
            score=1.0,
        )
        d = result.to_dict()
        assert d["answer"] == "42"
        assert d["score"] == 1.0


class TestExperimentManager:
    """Tests for ExperimentManager."""

    def test_create_study(self):
        """Test creating a study."""
        manager = ExperimentManager()
        study = Study(title="Test Study")
        created = manager.create_study(study)
        assert created is study
        assert manager.get_study(study.study_id) is not None

    def test_get_nonexistent_study(self):
        """Test getting non-existent study."""
        manager = ExperimentManager()
        assert manager.get_study("nonexistent") is None

    def test_create_run(self):
        """Test creating a run."""
        manager = ExperimentManager()
        study = Study(title="Test Study")
        manager.create_study(study)

        run = manager.create_run(
            study_id=study.study_id,
            condition_name="cond1",
        )
        assert run.study_id == study.study_id
        assert run.condition_name == "cond1"

    def test_start_and_complete_run(self):
        """Test starting and completing a run."""
        manager = ExperimentManager()
        study = Study(title="Test Study")
        manager.create_study(study)

        run = manager.create_run(
            study_id=study.study_id,
            condition_name="cond1",
        )

        assert manager.start_run(run.run_id) is True
        assert manager.complete_run(run.run_id) is True

    def test_start_nonexistent_run(self):
        """Test starting non-existent run."""
        manager = ExperimentManager()
        assert manager.start_run("nonexistent") is False

    def test_add_result(self):
        """Test adding results."""
        manager = ExperimentManager()
        study = Study(title="Test Study")
        manager.create_study(study)

        run = manager.create_run(
            study_id=study.study_id,
            condition_name="cond1",
        )

        result = RunResult(
            task_id="t1",
            experiment_id="exp_1",
            run_id=run.run_id,
            condition_name="cond1",
            success=True,
            score=0.9,
        )
        manager.add_result(result)

        results = manager.get_run_results(run.run_id)
        assert len(results) == 1
        assert results[0].success is True

    def test_get_statistics(self):
        """Test getting run statistics."""
        manager = ExperimentManager()
        study = Study(title="Test Study")
        manager.create_study(study)

        run = manager.create_run(
            study_id=study.study_id,
            condition_name="cond1",
        )

        # Add 10 results, 8 successful
        for i in range(10):
            result = RunResult(
                task_id=f"t{i}",
                experiment_id="exp_1",
                run_id=run.run_id,
                condition_name="cond1",
                success=i < 8,
                score=0.9 if i < 8 else 0.4,
            )
            manager.add_result(result)

        stats = manager.get_statistics(run.run_id)
        assert stats["num_tasks"] == 10
        assert abs(stats["success_rate"] - 0.8) < 0.01
        # avg_score = (8 * 0.9 + 2 * 0.4) / 10 = 8.0 / 10 = 0.8
        assert abs(stats["avg_score"] - 0.8) < 0.01

    def test_get_study_runs(self):
        """Test getting all runs for a study."""
        manager = ExperimentManager()
        study = Study(title="Test Study")
        manager.create_study(study)

        run1 = manager.create_run(
            study_id=study.study_id,
            condition_name="cond1",
        )
        run2 = manager.create_run(
            study_id=study.study_id,
            condition_name="cond2",
        )

        runs = manager.get_study_runs(study.study_id)
        assert len(runs) == 2
        assert run1.run_id in [r.run_id for r in runs]
        assert run2.run_id in [r.run_id for r in runs]


class TestEndToEndExperiment:
    """End-to-end experiment lifecycle tests."""

    def test_full_experiment_lifecycle(self):
        """Test complete experiment lifecycle."""
        manager = ExperimentManager()

        # Create study with conditions
        study = Study(
            title="Math vs Physics",
            hypothesis="H1: Math tasks have higher pass rates",
        )
        study.add_condition(Condition(
            name="math",
            config=ExperimentConfig(domain="math", num_tasks=50),
        ))
        study.add_condition(Condition(
            name="physics",
            config=ExperimentConfig(domain="physics", num_tasks=50),
        ))
        manager.create_study(study)

        # Create and run experiments
        run1 = manager.create_run(
            study_id=study.study_id,
            condition_name="math",
        )
        run2 = manager.create_run(
            study_id=study.study_id,
            condition_name="physics",
        )

        # Simulate execution
        manager.start_run(run1.run_id)
        for i in range(5):
            result = RunResult(
                task_id=f"math_t{i}",
                experiment_id="exp_1",
                run_id=run1.run_id,
                condition_name="math",
                success=True,
                score=0.9 + i * 0.01,
            )
            manager.add_result(result)
        manager.complete_run(run1.run_id)

        manager.start_run(run2.run_id)
        for i in range(5):
            result = RunResult(
                task_id=f"phys_t{i}",
                experiment_id="exp_1",
                run_id=run2.run_id,
                condition_name="physics",
                success=i < 4,
                score=0.8 + i * 0.02,
            )
            manager.add_result(result)
        manager.complete_run(run2.run_id)

        # Verify statistics
        stats1 = manager.get_statistics(run1.run_id)
        stats2 = manager.get_statistics(run2.run_id)

        assert stats1["num_tasks"] == 5
        assert stats1["success_rate"] == 1.0
        assert stats2["num_tasks"] == 5
        assert stats2["success_rate"] == 0.8

    def test_multiple_studies(self):
        """Test managing multiple studies."""
        manager = ExperimentManager()

        study1 = Study(title="Math Study")
        study2 = Study(title="Physics Study")
        manager.create_study(study1)
        manager.create_study(study2)

        run1 = manager.create_run(
            study_id=study1.study_id,
            condition_name="cond1",
        )
        run2 = manager.create_run(
            study_id=study2.study_id,
            condition_name="cond1",
        )

        # Results should be isolated by run
        result1 = RunResult(
            task_id="t1",
            experiment_id="exp_1",
            run_id=run1.run_id,
            condition_name="cond1",
            success=True,
            score=0.9,
        )
        result2 = RunResult(
            task_id="t2",
            experiment_id="exp_1",
            run_id=run2.run_id,
            condition_name="cond1",
            success=False,
            score=0.3,
        )

        manager.add_result(result1)
        manager.add_result(result2)

        assert len(manager.get_run_results(run1.run_id)) == 1
        assert len(manager.get_run_results(run2.run_id)) == 1
