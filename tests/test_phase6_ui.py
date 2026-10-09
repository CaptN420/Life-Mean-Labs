"""Phase 6 Tests — UI Experiment Controls

Tests for:
- ExperimentUIController state management
- Experiment lifecycle (start/stop)
- Metrics updates
- Dashboard data generation
"""

from __future__ import annotations

import pytest
import time

from experiments.ui_controller import ExperimentUIController, ExperimentState


class TestExperimentState:
    """Tests for ExperimentState schema."""

    def test_state_creation(self):
        """Test creating an experiment state."""
        state = ExperimentState(experiment_id="exp_123")
        assert state.experiment_id == "exp_123"
        assert state.is_running is False
        assert state.tasks_generated == 0

    def test_state_serialization(self):
        """Test state serialization."""
        state = ExperimentState(
            experiment_id="exp_123",
            is_running=True,
            tasks_generated=100,
            tasks_completed=80,
            tasks_valid=75,
            current_pass_rate=0.9375,
        )
        d = state.to_dict()
        assert d["experiment_id"] == "exp_123"
        assert d["is_running"] is True
        assert d["tasks_generated"] == 100
        assert d["pass_rate"] == 0.9375


class TestExperimentUIController:
    """Tests for ExperimentUIController."""

    def test_register_experiment(self):
        """Test registering a new experiment."""
        controller = ExperimentUIController()
        state = controller.register_experiment("exp_1", {"domain": "math"})
        assert state.experiment_id == "exp_1"
        assert state.is_running is False

    def test_start_experiment(self):
        """Test starting an experiment."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        result = controller.start_experiment("exp_1")
        assert result is True
        state = controller.get_experiment("exp_1")
        assert state.is_running is True
        assert state.start_time is not None

    def test_stop_experiment(self):
        """Test stopping an experiment."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        controller.start_experiment("exp_1")
        result = controller.stop_experiment("exp_1")
        assert result is True
        state = controller.get_experiment("exp_1")
        assert state.is_running is False

    def test_stop_nonexistent_experiment(self):
        """Test stopping a non-existent experiment."""
        controller = ExperimentUIController()
        result = controller.stop_experiment("nonexistent")
        assert result is False

    def test_update_metrics(self):
        """Test updating experiment metrics."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        controller.start_experiment("exp_1")

        controller.update_metrics("exp_1", {
            "tasks_generated": 100,
            "tasks_completed": 80,
            "tasks_valid": 75,
            "pass_rate": 0.9375,
        })

        state = controller.get_experiment("exp_1")
        assert state.tasks_generated == 100
        assert state.tasks_completed == 80
        assert state.tasks_valid == 75
        assert state.current_pass_rate == 0.9375

    def test_add_error(self):
        """Test adding errors to an experiment."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        controller.add_error("exp_1", "Test error")
        state = controller.get_experiment("exp_1")
        assert len(state.errors) == 1
        assert state.errors[0] == "Test error"

    def test_get_all_experiments(self):
        """Test getting all experiments."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        controller.register_experiment("exp_2", {})
        experiments = controller.get_all_experiments()
        assert len(experiments) == 2
        assert "exp_1" in experiments
        assert "exp_2" in experiments

    def test_get_nonexistent_experiment(self):
        """Test getting a non-existent experiment."""
        controller = ExperimentUIController()
        state = controller.get_experiment("nonexistent")
        assert state is None

    def test_dashboard_data(self):
        """Test dashboard data generation."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {"domain": "math"})
        controller.start_experiment("exp_1")
        controller.update_metrics("exp_1", {
            "tasks_generated": 50,
            "tasks_completed": 40,
            "pass_rate": 0.8,
        })

        data = controller.get_dashboard_data()
        assert data["total_experiments"] == 1
        assert data["running_count"] == 1
        assert "exp_1" in data["experiments"]

    def test_subscribe_callback(self):
        """Test subscribing to events."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})

        received = []
        controller.subscribe("exp_1", "started", lambda data: received.append(data))

        # Trigger event
        controller.start_experiment("exp_1")
        assert len(received) == 1

    def test_unsubscribe_callback(self):
        """Test unsubscribing from events."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})

        received = []
        callback = lambda data: received.append(data)
        controller.subscribe("exp_1", "started", callback)
        controller.unsubscribe("exp_1", "started", callback)

        # Trigger event - should not be received
        controller.start_experiment("exp_1")
        assert len(received) == 0


class TestExperimentLifecycle:
    """Tests for full experiment lifecycle."""

    def test_full_lifecycle(self):
        """Test complete experiment lifecycle."""
        controller = ExperimentUIController()

        # Register
        state = controller.register_experiment("exp_1", {"domain": "math", "num_tasks": 100})
        assert state.experiment_id == "exp_1"

        # Start
        controller.start_experiment("exp_1")
        state = controller.get_experiment("exp_1")
        assert state.is_running is True

        # Update metrics multiple times
        for i in range(5):
            controller.update_metrics("exp_1", {
                "tasks_generated": 20 * (i + 1),
                "tasks_completed": 18 * (i + 1),
                "tasks_valid": 17 * (i + 1),
                "pass_rate": 0.94,
            })

        # Add some errors
        controller.add_error("exp_1", "Timeout on task 5")
        controller.add_error("exp_1", "Invalid answer format")

        # Stop
        controller.stop_experiment("exp_1")
        state = controller.get_experiment("exp_1")
        assert state.is_running is False
        assert state.tasks_generated == 100
        assert len(state.errors) == 2

    def test_multiple_experiments(self):
        """Test managing multiple experiments."""
        controller = ExperimentUIController()

        # Create and start multiple experiments
        for i in range(3):
            controller.register_experiment(f"exp_{i}", {"domain": "math"})
            controller.start_experiment(f"exp_{i}")

        # Update each with different metrics
        controller.update_metrics("exp_0", {"tasks_generated": 10, "pass_rate": 0.9})
        controller.update_metrics("exp_1", {"tasks_generated": 20, "pass_rate": 0.85})
        controller.update_metrics("exp_2", {"tasks_generated": 30, "pass_rate": 0.95})

        # Get dashboard data
        data = controller.get_dashboard_data()
        assert data["total_experiments"] == 3
        assert data["running_count"] == 3


class TestMetricsTracking:
    """Tests for metrics tracking."""

    def test_pass_rate_calculation(self):
        """Test pass rate calculation."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        controller.start_experiment("exp_1")

        # Simulate 10 tasks, 8 valid
        controller.update_metrics("exp_1", {
            "tasks_generated": 10,
            "tasks_completed": 10,
            "tasks_valid": 8,
            "pass_rate": 0.8,
        })

        state = controller.get_experiment("exp_1")
        assert state.current_pass_rate == 0.8

    def test_novelty_score_tracking(self):
        """Test novelty score tracking."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        controller.start_experiment("exp_1")

        controller.update_metrics("exp_1", {
            "novelty_score": 0.75,
        })

        state = controller.get_experiment("exp_1")
        assert state.avg_novelty_score == 0.75

    def test_elapsed_time(self):
        """Test elapsed time tracking."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {})
        controller.start_experiment("exp_1")

        time.sleep(0.1)  # Small delay

        state = controller.get_experiment("exp_1")
        assert state.start_time is not None
        elapsed = time.time() - state.start_time
        assert elapsed >= 0.1
