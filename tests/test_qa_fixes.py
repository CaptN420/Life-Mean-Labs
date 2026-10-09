"""Regression tests for QA dogfood fixes (dashboard + runner)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from experiments.dashboard import DashboardHandler
from experiments.ui_controller import ExperimentUIController


def _make_controller():
    ui = ExperimentUIController()
    ui.register_experiment("exp_qa", {
        "domain": "math", "difficulty_range": (1, 3), "num_tasks": 5, "seed": 1,
    })
    return ui


class _FakeRequest:
    """Stub HTTP request sending a POST body to the handler."""

    def __init__(self, path, body=b"", method="POST"):
        self.path = path
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = type("R", (), {"read": lambda self, n: body})()
        self.method = method


class _FakeHandler(DashboardHandler):
    """Handler with dummy socket methods so we can call do_* directly."""

    def __init__(self, *args, **kwargs):
        # Bypass BaseHTTPRequestHandler.__init__ (needs a real socket).
        self._code = None
        self._err = None
        self._resp = None
        self.path = ""
        self.headers = {}
        self.rfile = type("R", (), {"read": lambda self, n: b""})()
        self.wfile = type("W", (), {"write": lambda self, b: b""})()

    def handle_one(self):
        pass

    def send_response(self, code):
        self._code = code

    def send_header(self, k, v):
        self._headers = getattr(self, "_headers", {})
        self._headers[k] = v

    def end_headers(self):
        pass

    def _send_json(self, data):
        self._resp = data
        self._code = 200

    def _send_error(self, status, message, code="error", request_id=None):
        self._code = status
        self._err = message


# ---- #4/#5/#6: input validation -------------------------------------------

def test_negative_num_tasks_rejected():
    ui = _make_controller()
    h = _FakeHandler()
    h.ui_controller = ui
    body = json.dumps({"num_tasks": -3}).encode()
    h.rfile = _FakeRequest("/api/experiments", body).rfile
    h._create_experiment({"num_tasks": -3})
    assert h._code == 400
    assert h._err == "Number of tasks must be a positive integer"


def test_string_num_tasks_clean_message():
    h = _FakeHandler()
    h.ui_controller = _make_controller()
    h._create_experiment({"num_tasks": "abc"})
    assert h._code == 400
    assert h._err == "Number of tasks must be a positive integer"


def test_reversed_range_rejected_before_running():
    h = _FakeHandler()
    h.ui_controller = _make_controller()
    h._create_experiment(
        {"domain": "math", "difficulty_range": [5, 1], "num_tasks": 5}
    )
    assert h._code == 400
    assert "ascending" in h._err


def test_empty_difficulty_range_clean_message():
    h = _FakeHandler()
    h.ui_controller = _make_controller()
    h._create_experiment({"difficulty_range": "", "num_tasks": 5})
    assert h._code == 400
    assert "two numbers" in h._err


def test_bad_range_format_clean_message():
    h = _FakeHandler()
    h.ui_controller = _make_controller()
    h._create_experiment({"difficulty_range": "[1]", "num_tasks": 5})
    assert h._code == 400
    assert "exactly two" in h._err


def test_stray_ui_field_like_deterministic_force_ignored_not_500():
    """The dashboard used to forward a `_deterministic_force` checkbox that
    ExperimentConfig does not accept. A stray/unknown UI key must be ignored
    (the mode selector stays the single source of truth), NOT crash into the
    opaque 500 'Failed to create experiment'."""
    h = _FakeHandler()
    h.ui_controller = _make_controller()
    h._create_experiment({
        "domain": "math", "difficulty_range": [1, 5], "num_tasks": 5, "seed": 42,
        "mode": "deterministic",
        "_deterministic_force": True,  # exact legacy key from the reported crash
        "widget_factor": "x",          # any other unknown key
    })
    assert h._code == 200, f"expected created, got {h._code}: {getattr(h, '_err', None)}"
    assert h._resp["status"] == "created"
    assert h._resp["experiment_id"]


# ---- #1: delete ------------------------------------------------------------

def test_delete_experiment_removes():
    ui = _make_controller()
    assert ui.get_experiment("exp_qa") is not None
    assert ui.delete_experiment("exp_qa") is True
    assert ui.get_experiment("exp_qa") is None


def test_delete_missing_returns_false():
    ui = _make_controller()
    assert ui.delete_experiment("nope") is False


def test_do_DELETE_route():
    ui = _make_controller()
    h = _FakeHandler()
    h.ui_controller = ui
    h._code = None
    h.do_DELETE()
    h.path = "/api/experiments/exp_qa"
    # route is matched by calling do_DELETE on the right path
    hdo = _FakeHandler()
    hdo.ui_controller = ui
    hdo.path = "/api/experiments/exp_qa"
    hdo.rfile = type("R", (), {"read": lambda self, n: b""})()
    hdo.do_DELETE()
    assert hdo._code == 200
    assert hdo._resp.get("status") == "deleted"
    assert ui.get_experiment("exp_qa") is None


# ---- #2: valid counter -----------------------------------------------------

def test_metrics_report_valid_and_invalid():
    ui = _make_controller()
    ui.update_metrics("exp_qa", {"tasks_completed": 5, "tasks_valid": 3, "tasks_invalid": 2})
    st = ui.get_experiment("exp_qa")
    assert st.tasks_valid == 3
    assert st.tasks_invalid == 2


def test_runner_loop_sets_valid_counts():
    """Ensures _run_experiment_loop passes valid/invalid to update_metrics."""
    import sys
    import types

    from experiments.ui_controller import ExperimentUIController
    ui = ExperimentUIController()
    ui.register_experiment("exp_run", {
        "domain": "math", "difficulty_range": (1, 3), "num_tasks": 2, "seed": 2,
    })

    class _FakeResult:
        def __init__(self, v):
            self.is_valid = v

    fake_runner = MagicMock()
    fake_runner.run_batch.return_value = [_FakeResult(True), _FakeResult(False)]
    fake_runner.get_statistics.return_value = {"validation_pass_rate": 0.5}

    fake_mod = types.ModuleType("experiments.runner")
    fake_mod.ExperimentRunner = MagicMock(return_value=fake_runner)

    class _FakeContext:
        def __init__(self, **kwargs):
            self.experiment_id = kwargs.get("experiment_id", "")
            self.generation_id = kwargs.get("generation_id", "")
            self.domain = kwargs.get("domain", "math")
            self.difficulty = kwargs.get("difficulty", 1)

    fake_mod.ExperimentContext = _FakeContext
    fake_mod.GeneratedTask = object

    orig = sys.modules.get("experiments.runner")
    sys.modules["experiments.runner"] = fake_mod

    try:
        # Run synchronously in-process for determinism.
        ui._run_experiment_loop("exp_run", {
            "domain": "math", "difficulty_range": (1, 3), "num_tasks": 2, "seed": 2,
        })
        st = ui.get_experiment("exp_run")
        assert st.tasks_valid == 1
        assert st.tasks_invalid == 1
        assert st.tasks_completed == 2
        assert st.current_pass_rate == 0.5
    finally:
        if orig is not None:
            sys.modules["experiments.runner"] = orig
        else:
            sys.modules.pop("experiments.runner", None)