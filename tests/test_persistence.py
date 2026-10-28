"""Tests for autonomous persistence layer."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_lab.persistence import (
    AutonomousPersistence,
    Checkpoint,
    PerseverancePolicy,
    PipelineState,
    RepairAttempt,
)


class TestPipelineState:
    def test_all_states_exist(self):
        states = [
            PipelineState.PLANNING,
            PipelineState.GENERATING,
            PipelineState.WRITING_FILES,
            PipelineState.BUILDING,
            PipelineState.EXECUTING,
            PipelineState.TESTING,
            PipelineState.ANALYZING_FAILURE,
            PipelineState.REPAIRING,
            PipelineState.RETESTING,
            PipelineState.VALIDATING,
            PipelineState.COMPLETED,
            PipelineState.FAILED,
            PipelineState.STOPPED,
        ]
        assert len(states) == 13


class TestPerseverancePolicy:
    def test_defaults(self):
        policy = PerseverancePolicy()
        assert policy.max_repair_attempts == 30
        assert policy.max_total_iterations == 100
        assert policy.max_consecutive_identical_failures == 3
        assert policy.max_runtime_minutes == 30
        assert policy.max_stagnation_cycles == 5

    def test_serialization(self):
        policy = PerseverancePolicy()
        data = policy.to_dict()
        restored = PerseverancePolicy.from_dict(data)
        assert restored.max_repair_attempts == 30

    def test_custom_values(self):
        policy = PerseverancePolicy(
            max_repair_attempts=10,
            max_total_iterations=50,
        )
        data = policy.to_dict()
        restored = PerseverancePolicy.from_dict(data)
        assert restored.max_repair_attempts == 10
        assert restored.max_total_iterations == 50


class TestRepairAttempt:
    def test_to_dict(self):
        attempt = RepairAttempt(
            attempt_id=1,
            hypothesis="fix_import",
            error_type="import_error",
            error_message="No module named 'foo'",
            files_modified=["main.py"],
            patch_applied="import foo",
            result_after_patch="failed",
            tests_run=5,
            tests_passed=0,
            strategy_used="fix_imports",
        )
        data = attempt.to_dict()
        assert data["attempt_id"] == 1
        assert data["error_type"] == "import_error"
        assert data["strategy_used"] == "fix_imports"


class TestCheckpoint:
    def test_to_dict(self):
        cp = Checkpoint(
            checkpoint_id="cp_001",
            timestamp=1234567890.0,
            files={"main.py": "x = 1"},
            notes="Before repair",
        )
        data = cp.to_dict()
        assert data["checkpoint_id"] == "cp_001"
        assert data["files_count"] == 1
        assert data["notes"] == "Before repair"


class TestAutonomousPersistence:
    def test_basic_operations(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)

        assert persistence.state == PipelineState.PLANNING
        assert persistence.total_repair_attempts == 0
        assert persistence.consecutive_failures == 0

    def test_can_continue_when_ok(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        assert persistence.can_continue() is True

    def test_can_continue_false_when_completed(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        persistence.state = PipelineState.COMPLETED
        assert persistence.can_continue() is False

    def test_can_continue_false_when_stopped(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        persistence.state = PipelineState.STOPPED
        assert persistence.can_continue() is False

    def test_can_continue_false_when_max_iterations(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        persistence.policy.max_total_iterations = 0
        assert persistence.can_continue() is False

    def test_can_continue_false_when_max_consecutive_failures(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        persistence._consecutive_failures = 3
        assert persistence.can_continue() is False

    def test_record_repair_attempt(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        attempt = RepairAttempt(
            attempt_id=1,
            hypothesis="fix",
            error_type="syntax_error",
            error_message="SyntaxError",
            files_modified=[],
            patch_applied="",
            result_after_patch="failed",
            tests_run=5,
            tests_passed=0,
            strategy_used="fix_syntax",
        )
        persistence.record_repair_attempt(attempt)
        assert persistence.total_repair_attempts == 1
        assert persistence.consecutive_failures == 1

    def test_record_successful_repair_resets_counter(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        attempt = RepairAttempt(
            attempt_id=1,
            hypothesis="fix",
            error_type="syntax_error",
            error_message="SyntaxError",
            files_modified=[],
            patch_applied="",
            result_after_patch="passed",
            tests_run=5,
            tests_passed=5,
            strategy_used="fix_syntax",
        )
        persistence.record_repair_attempt(attempt)
        assert persistence.consecutive_failures == 0

    def test_should_change_strategy_on_stagnation(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        # Add 5 identical failures
        for i in range(5):
            attempt = RepairAttempt(
                attempt_id=i,
                hypothesis="fix",
                error_type="same_error",
                error_message="Same error",
                files_modified=[],
                patch_applied="",
                result_after_patch="failed",
                tests_run=5,
                tests_passed=0,
                strategy_used="default",
            )
            persistence.record_repair_attempt(attempt)

        assert persistence.should_change_strategy() is True

    def test_record_checkpoint(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        cp_id = persistence.record_checkpoint(
            files={"main.py": "x = 1"},
            notes="Test checkpoint"
        )
        assert cp_id.startswith("cp_")
        assert len(persistence.checkpoints) == 1

    def test_persist_and_load_state(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        persistence.state = PipelineState.REPAIRING
        persistence._consecutive_failures = 2

        persistence.persist_state()

        # Create new persistence and load
        persistence2 = AutonomousPersistence("run_1", tmp_path)
        loaded = persistence2.load_state()
        assert loaded is not None
        assert loaded["state"] == "REPAIRING"
        assert loaded["consecutive_failures"] == 2

    def test_get_strategy_recommendation(self, tmp_path):
        persistence = AutonomousPersistence("run_1", tmp_path)
        # No attempts yet
        rec = persistence.get_strategy_recommendation()
        assert rec == "initial_development"

        # Add some failed attempts with same strategy
        for i in range(3):
            attempt = RepairAttempt(
                attempt_id=i,
                hypothesis="fix",
                error_type="error",
                error_message="Error",
                files_modified=[],
                patch_applied="",
                result_after_patch="failed",
                tests_run=5,
                tests_passed=0,
                strategy_used="strategy_a",
            )
            persistence.record_repair_attempt(attempt)

        rec = persistence.get_strategy_recommendation()
        assert rec != "strategy_a"
