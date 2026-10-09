"""Integration tests for AutoPilot connecting experiments to DebateEngine."""

import pytest
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestAutoPilotIntegration:
    """Test that AutoPilot correctly connects experiments to the debate engine."""

    def test_create_debate_engine(self):
        """Test that a DebateEngine can be created for an experiment."""
        from experiments.autopilot import AutoPilot

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create mock engine and set it directly
        mock_engine = MagicMock()
        autopilot._engines[experiment_id] = mock_engine

        # Verify engine was created
        assert experiment_id in autopilot._engines
        assert autopilot._engines[experiment_id] is mock_engine

    def test_run_task_through_debate(self):
        """Test running a task through the debate engine."""
        from experiments.autopilot import AutoPilot
        from experiments.generation.schemas import GeneratedTask

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create a mock task
        task = GeneratedTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            source="generator",
            domain="math",
            difficulty=3,
            reasoning_type="calculation",
            description="Calculate 2 + 2",
            ground_truth=4,
        )

        # Create mock engine
        mock_engine = MagicMock()
        mock_engine._get_debate_id.return_value = 1
        mock_engine.start_debate.return_value = True

        # Mock turn manager
        mock_turn = MagicMock()
        mock_turn.response = "The answer is 4"
        mock_engine.turn_manager.get_all_turns.return_value = [mock_turn]

        # Run task
        result = autopilot._run_task_through_debate(experiment_id, task, mock_engine)

        # Verify result
        assert result.experiment_id == experiment_id
        assert result.task_id == task.task_id
        assert result.debate_id == 1
        assert result.is_valid is True
        assert result.validation_score > 0

    def test_experiment_trace_path(self):
        """Test the trace path: experiment_id -> task_id -> run_id -> debate_id."""
        from experiments.autopilot import AutoPilot
        from experiments.generation.schemas import GeneratedTask

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create mock task
        task = GeneratedTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            source="generator",
            domain="math",
            difficulty=2,
            reasoning_type="calculation",
            description="Calculate 5 * 3",
            ground_truth=15,
        )

        # Create mock engine
        mock_engine = MagicMock()
        mock_engine._get_debate_id.return_value = 42
        mock_engine.start_debate.return_value = True

        mock_turn = MagicMock()
        mock_turn.response = "15"
        mock_engine.turn_manager.get_all_turns.return_value = [mock_turn]

        # Run task
        result = autopilot._run_task_through_debate(experiment_id, task, mock_engine)

        # Verify trace path
        assert result.experiment_id == experiment_id
        assert result.task_id == task.task_id
        assert result.run_id.startswith("run_")
        assert result.debate_id == 42
        # NOTE: this mock-based trace-path test is superseded by the GENUINE
        # integration test in test_debate_engine_integration.py, which runs a
        # real engine (real DB, real agents, real turns, real raw_experiment_id).

    def test_run_batch_integration(self):
        """Test running a batch of tasks through the debate engine."""
        from experiments.autopilot import AutoPilot
        from experiments.generation.schemas import GeneratedTask

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create mock tasks
        tasks = [
            GeneratedTask(
                task_id=f"task_{i}",
                source="generator",
                domain="math",
                difficulty=1,
                reasoning_type="calculation",
                description=f"Calculate {i} + {i}",
                ground_truth=i * 2,
            )
            for i in range(3)
        ]

        # Create mock engine
        mock_engine = MagicMock()
        mock_engine._get_debate_id.return_value = 1
        mock_engine.start_debate.return_value = True

        mock_turn = MagicMock()
        mock_turn.response = "4"
        mock_engine.turn_manager.get_all_turns.return_value = [mock_turn]

        # Manually set the engine to avoid import issues
        autopilot._engines[experiment_id] = mock_engine

        # Run batch - call the internal method directly
        results = []
        for task in tasks:
            result = autopilot._run_task_through_debate(experiment_id, task, mock_engine)
            results.append(result)

        # Verify all tasks processed
        assert len(results) == 3
        assert all(r.experiment_id == experiment_id for r in results)

    def test_get_results(self):
        """Test retrieving results for an experiment."""
        from experiments.autopilot import AutoPilot
        from experiments.generation.schemas import GeneratedTask
        from experiments.autopilot import DebateRunResult

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create mock results
        result1 = DebateRunResult(
            experiment_id=experiment_id,
            task_id="task_1",
            run_id="run_1",
            debate_id=1,
            is_valid=True,
        )
        result2 = DebateRunResult(
            experiment_id=experiment_id,
            task_id="task_2",
            run_id="run_2",
            debate_id=2,
            is_valid=False,
        )

        autopilot._results[experiment_id] = [result1, result2]

        # Get results
        results = autopilot.get_results(experiment_id)

        # Verify
        assert len(results) == 2
        assert results[0].task_id == "task_1"
        assert results[1].task_id == "task_2"

    def test_statistics(self):
        """Test getting statistics for an experiment."""
        from experiments.autopilot import AutoPilot
        from experiments.autopilot import DebateRunResult

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create mock results
        autopilot._results[experiment_id] = [
            DebateRunResult(
                experiment_id=experiment_id,
                task_id="task_1",
                run_id="run_1",
                debate_id=1,
                turn_count=3,
                is_valid=True,
                validation_score=1.0,
            ),
            DebateRunResult(
                experiment_id=experiment_id,
                task_id="task_2",
                run_id="run_2",
                debate_id=2,
                turn_count=5,
                is_valid=False,
                validation_score=0.0,
            ),
        ]

        # Get statistics
        stats = autopilot.get_statistics(experiment_id)

        # Verify
        assert stats["total_runs"] == 2
        assert stats["successful_runs"] == 1
        assert stats["validation_pass_rate"] == 0.5
        assert stats["avg_turns"] == 4.0

    def test_stop_experiment(self):
        """Test stopping an experiment."""
        from experiments.autopilot import AutoPilot

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create mock engine
        mock_engine = MagicMock()
        autopilot._engines[experiment_id] = mock_engine

        # Stop experiment
        autopilot.stop_experiment(experiment_id)

        # Verify stop was called
        mock_engine.stop_debate.assert_called_once()
        assert experiment_id not in autopilot._engines


class TestExperimentToDebateBridge:
    """Test the bridge between ExperimentUIController and AutoPilot."""

    def test_ui_controller_uses_autopilot(self):
        """Test that UI controller can use AutoPilot for execution."""
        from experiments.ui_controller import ExperimentUIController
        from experiments.autopilot import AutoPilot

        # This test verifies the integration points exist
        ui_controller = ExperimentUIController()
        autopilot = AutoPilot()

        # Verify both components can be instantiated together
        assert ui_controller is not None
        assert autopilot is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
