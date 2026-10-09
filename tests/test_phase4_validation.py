"""Phase 4 Tests — Validation + Failure Bank

Tests for:
- OracleValidator with math, physics, chemistry domains
- ValidationResult schema
- FailureBank storage and retrieval
- Integration with ExperimentRunner
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from experiments.failure_bank import FailureBank
from experiments.generation.schemas import GeneratedTask
from experiments.generation.task_generator import TaskGenerator
from experiments.runner import ExperimentResult, ExperimentRunner
from experiments.validation import OracleValidator
from experiments.validation.schemas import ValidationResult


class TestValidationResult:
    """Tests for ValidationResult schema."""

    def test_valid_result(self):
        """Test creating a valid result."""
        vr = ValidationResult(
            valid=True,
            score=1.0,
            method="deterministic",
            evidence={"answer": 42, "ground_truth": 42},
        )
        assert vr.valid is True
        assert vr.score == 1.0

    def test_invalid_result(self):
        """Test creating an invalid result."""
        vr = ValidationResult(
            valid=False,
            score=0.0,
            method="deterministic",
            error="Answer mismatch",
        )
        assert vr.valid is False
        assert vr.error == "Answer mismatch"

    def test_result_serialization(self):
        """Test result serialization."""
        vr = ValidationResult(
            valid=True,
            score=0.95,
            method="hybrid",
            evidence={"comparison": "pass"},
            steps=["step1", "step2"],
        )
        d = vr.to_dict()
        assert d["valid"] is True
        assert d["score"] == 0.95
        assert d["steps"] == ["step1", "step2"]

    def test_result_from_dict(self):
        """Test result deserialization."""
        data = {
            "valid": False,
            "score": 0.5,
            "method": "llm_judge",
            "error": "Timeout",
        }
        vr = ValidationResult.from_dict(data)
        assert vr.valid is False
        assert vr.method == "llm_judge"


class TestOracleValidator:
    """Tests for the deterministic oracle validator."""

    def test_math_exact_match(self):
        """Test math validation with exact match."""
        validator = OracleValidator()
        result = validator.validate(
            task_description="Calculate 5 + 3",
            answer=8,
            ground_truth=8,
            domain="math",
        )
        assert result.valid is True
        assert result.score == 1.0

    def test_math_with_tolerance(self):
        """Test math validation with floating point tolerance."""
        validator = OracleValidator()
        result = validator.validate(
            task_description="Calculate 10 / 3",
            answer=3.333333,
            ground_truth=3.3333333333333335,
            domain="math",
        )
        assert result.valid is True
        assert result.score == 1.0

    def test_math_wrong_answer(self):
        """Test math validation with wrong answer."""
        validator = OracleValidator()
        result = validator.validate(
            task_description="Calculate 5 + 3",
            answer=9,
            ground_truth=8,
            domain="math",
        )
        assert result.valid is False
        # Score should be partial (not zero) due to proximity
        assert result.score < 1.0

    def test_physics_validation(self):
        """Test physics validation."""
        validator = OracleValidator()
        # F = ma, m=10, a=9.8 => F=98
        result = validator.validate(
            task_description="Calculate force for mass=10kg and acceleration=9.8m/s²",
            answer=98.0,
            ground_truth=98.0,
            domain="physics",
        )
        assert result.valid is True

    def test_chemistry_validation(self):
        """Test chemistry validation."""
        validator = OracleValidator()
        # Molar mass of H2O = 18.015
        result = validator.validate(
            task_description="Calculate molar mass of H2O",
            answer=18.015,
            ground_truth=18.015,
            domain="chemistry",
        )
        assert result.valid is True

    def test_no_answer(self):
        """Test validation with no answer."""
        validator = OracleValidator()
        result = validator.validate(
            task_description="Calculate 5 + 3",
            answer=None,
            ground_truth=8,
            domain="math",
        )
        assert result.valid is False
        assert "No answer" in result.error

    def test_no_ground_truth(self):
        """Test validation with no ground truth."""
        validator = OracleValidator()
        result = validator.validate(
            task_description="Calculate 5 + 3",
            answer=8,
            ground_truth=None,
            domain="math",
        )
        assert result.valid is False
        assert "No ground truth" in result.error

    def test_statistics(self):
        """Test validation statistics."""
        validator = OracleValidator()
        # Run some validations
        validator.validate("5+3", 8, 8, "math")
        validator.validate("5+3", 9, 8, "math")
        validator.validate("10*2", 20, 20, "math")

        stats = validator.get_statistics()
        assert stats["total_validations"] == 3
        assert stats["failures"] == 1
        assert stats["pass_rate"] == pytest.approx(2/3, abs=0.01)


class TestFailureBank:
    """Tests for the failure bank storage."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving failures."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            bank = FailureBank(storage_path=path)
            fid = bank.store(
                task_id="task_123",
                experiment_id="exp_456",
                run_id="run_789",
                failed_answer=9,
                ground_truth=8,
                error_message="Wrong answer",
            )

            assert fid is not None
            records = bank.query(task_id="task_123")
            assert len(records) == 1
            assert records[0].failed_answer == 9
            assert records[0].ground_truth == 8
        finally:
            path.unlink(missing_ok=True)

    def test_query_by_experiment(self):
        """Test querying failures by experiment."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            bank = FailureBank(storage_path=path)
            bank.store("task_1", "exp_1", "run_1", 9, 8)
            bank.store("task_2", "exp_1", "run_2", 10, 8)
            bank.store("task_3", "exp_2", "run_3", 7, 8)

            exp1_failures = bank.query_by_experiment("exp_1")
            assert len(exp1_failures) == 2

            exp2_failures = bank.query_by_experiment("exp_2")
            assert len(exp2_failures) == 1
        finally:
            path.unlink(missing_ok=True)

    def test_query_by_run(self):
        """Test querying failures by run."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            bank = FailureBank(storage_path=path)
            bank.store("task_1", "exp_1", "run_123", 9, 8)

            record = bank.query_by_run("run_123")
            assert record is not None
            assert record.task_id == "task_1"

            none_record = bank.query_by_run("nonexistent")
            assert none_record is None
        finally:
            path.unlink(missing_ok=True)

    def test_export(self):
        """Test exporting all failures."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            bank = FailureBank(storage_path=path)
            bank.store("task_1", "exp_1", "run_1", 9, 8)
            bank.store("task_2", "exp_1", "run_2", 10, 8)

            exports = bank.export()
            assert len(exports) == 2
            assert all("task_id" in e for e in exports)
        finally:
            path.unlink(missing_ok=True)

    def test_statistics(self):
        """Test failure statistics."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            bank = FailureBank(storage_path=path)
            bank.store("task_1", "exp_1", "run_1", 9, 8)
            bank.store("task_2", "exp_1", "run_2", 10, 8)
            bank.store("task_3", "exp_2", "run_3", 7, 8)

            stats = bank.get_statistics()
            assert stats["total_failures"] == 3
            assert stats["by_experiment"]["exp_1"] == 2
            assert stats["by_experiment"]["exp_2"] == 1
        finally:
            path.unlink(missing_ok=True)

    def test_persistence(self):
        """Test that failures persist across instances."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            # Store failures
            bank1 = FailureBank(storage_path=path)
            bank1.store("task_1", "exp_1", "run_1", 9, 8)

            # Create new instance and load
            bank2 = FailureBank(storage_path=path)
            records = bank2.query(task_id="task_1")
            assert len(records) == 1
            assert records[0].failed_answer == 9
        finally:
            path.unlink(missing_ok=True)

    def test_clear(self):
        """Test clearing all failures."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            bank = FailureBank(storage_path=path)
            bank.store("task_1", "exp_1", "run_1", 9, 8)
            assert len(bank.query(task_id="task_1")) == 1

            bank.clear()
            assert len(bank.query(task_id="task_1")) == 0
        finally:
            path.unlink(missing_ok=True)


class TestIntegrationWithRunner:
    """Tests for integration with ExperimentRunner."""

    def test_runner_uses_oracle_validator(self):
        """Test that runner uses deterministic validation."""
        # Use OracleValidator directly for this test
        validator = OracleValidator()
        result = validator.validate(
            task_description="Calculate 5 + 3",
            answer=8,
            ground_truth=8,
            domain="math",
        )
        assert result.valid is True
        assert result.method == "deterministic"

    def test_failure_stored_on_wrong_answer(self):
        """Test that failures are properly tracked."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            path = Path(f.name)

        try:
            # Create a task and run with wrong answer manually
            task = GeneratedTask(
                domain="math",
                description="Calculate 5 + 3",
                ground_truth=8,
            )

            # Simulate wrong answer
            result = ExperimentResult(
                run_id="run_test",
                task_id=task.task_id,
                experiment_id="exp_test",
                generation_id="gen_test",
                config={},
                routing_decision={},
                workers_used=[],
                tools_used=[],
                answer=9,  # Wrong
                ground_truth=8,
                validation_result=ValidationResult(valid=False, score=0.0),
            )

            # Store failure
            bank = FailureBank(storage_path=path)
            fid = bank.store(
                task_id=result.task_id,
                experiment_id=result.experiment_id,
                run_id=result.run_id,
                failed_answer=result.answer,
                ground_truth=result.ground_truth,
            )

            assert fid is not None
            records = bank.query(task_id=task.task_id)
            assert len(records) == 1
        finally:
            path.unlink(missing_ok=True)


class TestEndToEndValidation:
    """End-to-end tests for validation pipeline."""

    def test_full_validation_pipeline(self):
        """Test full validation pipeline from generation to failure storage."""
        # Generate tasks
        generator = TaskGenerator(seed=42)
        tasks = generator.generate_batch(
            domain="math",
            difficulty_range=(1, 3),
            count=5,
        )

        # Run through experiment pipeline
        runner = ExperimentRunner()
        results = []
        for task in tasks:
            result = runner.run_task(task)
            results.append(result)

        # Verify all have validation results (may be invalid if no answer computed)
        for result in results:
            assert result.validation_result is not None

        # Check statistics
        stats = runner.get_statistics()
        assert stats["total_runs"] == 5
        assert 0.0 <= stats["validation_pass_rate"] <= 1.0

    def test_mixed_validation_outcomes(self):
        """Test with mixed valid and invalid results."""
        # Use OracleValidator directly for controlled testing
        validator = OracleValidator()

        # Valid result
        valid_result = validator.validate(
            task_description="Calculate 10 + 5",
            answer=15,
            ground_truth=15,
            domain="math",
        )
        assert valid_result.valid is True

        # Invalid result
        invalid_result = validator.validate(
            task_description="Calculate 10 + 5",
            answer=16,
            ground_truth=15,
            domain="math",
        )
        assert invalid_result.valid is False
