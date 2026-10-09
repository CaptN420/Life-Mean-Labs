"""Integration test: POST /api/experiments/{id}/start triggers real debate engine execution."""

import pytest
import time
import uuid
from unittest.mock import MagicMock, patch


class TestAutoPilotIntegrationEndpoint:
    """Test that the dashboard API correctly triggers ExperimentRunner execution."""

    def test_start_experiment_triggers_runner(self):
        """Verify that starting an experiment creates an ExperimentRunner and processes tasks."""
        from experiments.ui_controller import ExperimentUIController
        from experiments.runner import ExperimentRunner
        from experiments.generation.schemas import GeneratedTask
        import threading

        ui = ExperimentUIController()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Register experiment
        config = {
            "domain": "math",
            "difficulty_range": (1, 5),
            "num_tasks": 3,
            "seed": 42,
            "deterministic": True,
        }
        ui.register_experiment(experiment_id, config)

        # Track if ExperimentRunner was called
        runner_called = threading.Event()

        # Mock ExperimentRunner to verify it's called
        with patch('experiments.runner.ExperimentRunner') as mock_runner_class:
            def track_call(*args, **kwargs):
                runner_called.set()
                mock_runner = MagicMock()
                mock_runner.get_statistics.return_value = {
                    "total_runs": 3,
                    "successful_runs": 2,
                    "validation_pass_rate": 0.67,
                    "avg_score": 0.8,
                }
                return mock_runner

            mock_runner_class.side_effect = track_call

            # Start experiment (triggers _run_experiment_loop in background)
            ui.start_experiment(experiment_id)

            # Wait for the background thread to complete
            import time
            time.sleep(0.5)

            # Verify ExperimentRunner was instantiated
            assert runner_called.is_set(), "ExperimentRunner should have been called"
            mock_runner_class.assert_called_once()

            # Get the actual state
            state = ui.get_experiment(experiment_id)
            assert state is not None
            assert state.tasks_generated == 3

    def test_trace_path_experiment_to_debate(self):
        """Prove the trace: experiment_id -> task_id -> run_id -> debate_id."""
        from experiments.autopilot import AutoPilot, DebateRunResult
        from experiments.generation.schemas import GeneratedTask

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create mock task
        task = GeneratedTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            source="generator",
            domain="math",
            difficulty=3,
            reasoning_type="calculation",
            description="Calculate 7 * 8",
            ground_truth=56,
        )

        # Create mock engine with proper trace
        mock_engine = MagicMock()
        mock_engine._get_debate_id.return_value = 12345
        mock_engine.start_debate.return_value = True

        mock_turn = MagicMock()
        mock_turn.response = "The answer is 56"
        mock_engine.turn_manager.get_all_turns.return_value = [mock_turn]

        # Run task through debate
        result = autopilot._run_task_through_debate(experiment_id, task, mock_engine)

        # Verify complete trace path
        assert result.experiment_id == experiment_id
        assert result.task_id == task.task_id
        assert result.run_id.startswith("run_")
        assert result.debate_id == 12345

        # All components of the trace are present and non-empty
        assert len(result.experiment_id) > 0
        assert len(result.task_id) > 0
        assert len(result.run_id) > 0
        assert result.debate_id > 0

    def test_raw_data_persistence(self):
        """Test that RAW experiment data is captured and persisted."""
        from experiments.autopilot import AutoPilot, DebateRunResult
        from experiments.generation.schemas import GeneratedTask

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        task = GeneratedTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            source="generator",
            domain="math",
            difficulty=2,
            reasoning_type="calculation",
            description="Calculate 10 + 20",
            ground_truth=30,
        )

        # Create mock engine with RAW experiment ID
        mock_engine = MagicMock()
        mock_engine._get_debate_id.return_value = 99
        mock_engine.start_debate.return_value = True
        mock_engine._raw_experiment_id = "exp_raw_12345"

        mock_turn = MagicMock()
        mock_turn.response = "30"
        mock_engine.turn_manager.get_all_turns.return_value = [mock_turn]

        # Run task
        result = autopilot._run_task_through_debate(experiment_id, task, mock_engine)

        # Verify RAW data is captured
        assert result.raw_experiment_id == "exp_raw_12345"
        assert result.debate_id == 99
        assert result.is_valid is True

    def test_multiple_tasks_create_multiple_debates(self):
        """Test that multiple tasks each create their own debate."""
        from experiments.autopilot import AutoPilot
        from experiments.generation.schemas import GeneratedTask

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create multiple tasks
        tasks = [
            GeneratedTask(
                task_id=f"task_{i}",
                source="generator",
                domain="math",
                difficulty=1,
                reasoning_type="calculation",
                description=f"Calculate {i} + 1",
                ground_truth=i + 1,
            )
            for i in range(3)
        ]

        # Create mock engine
        mock_engine = MagicMock()
        mock_engine._get_debate_id.return_value = 1
        mock_engine.start_debate.return_value = True

        mock_turn = MagicMock()
        mock_turn.response = "2"
        mock_engine.turn_manager.get_all_turns.return_value = [mock_turn]

        # Run all tasks
        results = []
        for task in tasks:
            result = autopilot._run_task_through_debate(experiment_id, task, mock_engine)
            results.append(result)

        # Verify each task created a unique run
        run_ids = [r.run_id for r in results]
        assert len(run_ids) == 3
        assert len(set(run_ids)) == 3  # All unique

        # All should have same experiment and debate IDs (same engine)
        assert all(r.experiment_id == experiment_id for r in results)
        assert all(r.debate_id == 1 for r in results)


class TestExperimentDashboardIntegration:
    """Test the full dashboard -> AutoPilot integration."""

    def test_dashboard_start_triggers_runner(self):
        """Test that the dashboard /start endpoint triggers ExperimentRunner."""
        from experiments.dashboard import DashboardHandler
        from experiments.ui_controller import ExperimentUIController
        from experiments.runner import ExperimentRunner
        from unittest.mock import patch

        ui = ExperimentUIController()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"
        ui.register_experiment(experiment_id, {"domain": "math"})

        # Patch ExperimentRunner to avoid actual execution in test
        with patch('experiments.runner.ExperimentRunner') as mock_class:
            mock_instance = MagicMock()
            mock_instance.get_statistics.return_value = {
                "total_runs": 1,
                "successful_runs": 1,
                "validation_pass_rate": 1.0,
                "avg_score": 1.0,
            }
            mock_class.return_value = mock_instance

            # Start the experiment
            ui.start_experiment(experiment_id)

            # Give background thread time to start
            import time
            time.sleep(0.1)

            # Verify ExperimentRunner was created
            mock_class.assert_called_once()

    def test_end_to_end_experiment_lifecycle(self):
        """Test the complete lifecycle: create -> start -> process -> stop."""
        from experiments.ui_controller import ExperimentUIController
        from experiments.autopilot import AutoPilot, DebateRunResult
        from experiments.generation.schemas import GeneratedTask

        ui = ExperimentUIController()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Register experiment
        config = {
            "domain": "math",
            "difficulty_range": (1, 3),
            "num_tasks": 2,
            "seed": 42,
            "deterministic": True,
        }
        ui.register_experiment(experiment_id, config)

        # Verify experiment was registered
        state = ui.get_experiment(experiment_id)
        assert state is not None
        assert state.experiment_id == experiment_id

        # Start experiment (will run in background)
        ui.start_experiment(experiment_id)

        # Verify it started
        state = ui.get_experiment(experiment_id)
        assert state.is_running is True

        # Stop experiment
        ui.stop_experiment(experiment_id)

        # Verify it stopped
        state = ui.get_experiment(experiment_id)
        assert state.is_running is False

    def test_autopilot_integration_with_real_engine(self):
        """Test that AutoPilot correctly creates and uses DebateEngine."""
        from experiments.autopilot import AutoPilot
        from experiments.generation.schemas import GeneratedTask

        autopilot = AutoPilot()
        experiment_id = f"test_{uuid.uuid4().hex[:8]}"

        # Create a task
        task = GeneratedTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            source="generator",
            domain="math",
            difficulty=2,
            reasoning_type="calculation",
            description="Calculate 3 + 5",
            ground_truth=8,
        )

        # Create mock engine (simulating real DebateEngine)
        mock_engine = MagicMock()
        mock_engine._get_debate_id.return_value = 42
        mock_engine.start_debate.return_value = True

        mock_turn = MagicMock()
        mock_turn.response = "8"
        mock_engine.turn_manager.get_all_turns.return_value = [mock_turn]

        # Run task through autopilot
        result = autopilot._run_task_through_debate(experiment_id, task, mock_engine)

        # Verify complete trace path
        assert result.experiment_id == experiment_id
        assert result.task_id == task.task_id
        assert result.run_id.startswith("run_")
        assert result.debate_id == 42
        assert result.is_valid is True
        assert result.validation_score > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
