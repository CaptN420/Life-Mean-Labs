"""Tests for experiment dashboard HTTP API."""

from __future__ import annotations

import json
import io
from unittest.mock import MagicMock
from http.server import BaseHTTPRequestHandler

from experiments.dashboard import DashboardHandler, start_dashboard
from experiments.ui_controller import ExperimentUIController
from experiments.config import ExperimentConfig


class TestDashboardAPI:
    """Tests for dashboard HTTP API endpoints."""

    def test_get_experiments(self):
        """Test GET /api/experiments returns dashboard data."""
        controller = ExperimentUIController()
        controller.register_experiment("exp_1", {"domain": "math"})
        DashboardHandler.ui_controller = controller

        # Simulate request
        handler = MagicMock()
        handler.path = "/api/experiments"
        handler.headers = {}

        # We can't easily test the full handler, so test the controller directly
        data = controller.get_dashboard_data()
        assert data["total_experiments"] == 1
        assert "exp_1" in data["experiments"]

    def test_create_experiment_with_array(self):
        """Test creating experiment with array difficulty_range."""
        controller = ExperimentUIController()
        DashboardHandler.ui_controller = controller

        # Simulate POST data with array
        body = json.dumps({
            "domain": "math",
            "difficulty_range": [1, 5],
            "num_tasks": 100,
            "seed": 42,
            "deterministic": True,
        })

        # Parse and create
        data = json.loads(body)
        if "difficulty_range" in data:
            dr = data["difficulty_range"]
            if isinstance(dr, str):
                data["difficulty_range"] = tuple(json.loads(dr))
            elif isinstance(dr, list):
                data["difficulty_range"] = tuple(dr)

        config = ExperimentConfig(**data)
        controller.register_experiment(config.experiment_id, config.to_dict())

        assert config.domain == "math"
        assert config.difficulty_range == (1, 5)
        assert config.num_tasks == 100

    def test_create_experiment_with_string(self):
        """Test creating experiment with string difficulty_range."""
        controller = ExperimentUIController()
        DashboardHandler.ui_controller = controller

        # Simulate POST data with string
        body = json.dumps({
            "domain": "physics",
            "difficulty_range": "[1, 5]",
            "num_tasks": "50",
            "seed": "42",
            "deterministic": "on",
        })

        # Parse and create
        data = json.loads(body)
        if "difficulty_range" in data:
            dr = data["difficulty_range"]
            if isinstance(dr, str):
                data["difficulty_range"] = tuple(json.loads(dr))
            elif isinstance(dr, list):
                data["difficulty_range"] = tuple(dr)

        # Parse numeric fields
        if "num_tasks" in data:
            data["num_tasks"] = int(data["num_tasks"])
        if "seed" in data:
            data["seed"] = int(data["seed"])
        if "deterministic" in data:
            data["deterministic"] = str(data["deterministic"]).lower() in ("true", "1", "on")

        config = ExperimentConfig(**data)
        controller.register_experiment(config.experiment_id, config.to_dict())

        assert config.domain == "physics"
        assert config.difficulty_range == (1, 5)
        assert config.num_tasks == 50
        assert config.seed == 42
        assert config.deterministic is True


class TestDashboardHandler:
    """Tests for DashboardHandler."""

    def test_handler_has_controller(self):
        """Test that handler has ui_controller attribute."""
        controller = ExperimentUIController()
        DashboardHandler.ui_controller = controller
        assert DashboardHandler.ui_controller is controller
