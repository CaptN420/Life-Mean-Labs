"""
Tests for the Studio's real-engine runner (life_mean_studio.engine.runner).

Three layers:
1. Unit — StudioRunner orchestration against a fake controller/storage.
2. Integration — StudioRunner against the REAL ExperimentUIController, with
   only the LLM-dependent pieces (task generation / ExperimentRunner) stubbed,
   so the genuine thread + event lifecycle is exercised without a backend.
3. UI (offscreen) — Quick Run RUN/STOP controls are wired and flip button state.

These require the Life_mean project root (where ``experiments`` lives) on
sys.path; engine imports are otherwise resolved from the main repo.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

# Add Life_mean project root to path so `experiments.*` resolves.
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from life_mean_studio.engine.runner import StudioRunner, RunnerError  # noqa: E402
from life_mean_studio.engine.storage import StudioStorage  # noqa: E402


# ---------------------------------------------------------------- helpers


def _wait_until(pred, timeout=10.0, step=0.04):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


class FakeState:
    def __init__(self, eid):
        self.experiment_id = eid
        self.is_running = False
        self.errors = []
        self.tasks_valid = 0
        self.tasks_completed = 0
        self.tasks_generated = 0

    def to_dict(self):
        return dict(vars(self))


class FakeController:
    """Duck-typed ExperimentUIController for unit tests."""

    def __init__(self):
        self.states = {}
        self.configs = {}
        self._cb = {}

    def register_experiment(self, eid, config):
        self.states[eid] = FakeState(eid)
        self.configs[eid] = config

    def start_experiment(self, eid):
        self.states[eid].is_running = True
        self.emit(eid, "started")
        return True

    def stop_experiment(self, eid):
        self.states[eid].is_running = False
        self.emit(eid, "stopped")
        return True

    def get_experiment(self, eid):
        return self.states.get(eid)

    def subscribe(self, eid, event, cb):
        self._cb.setdefault(eid, {}).setdefault(event, []).append(cb)

    def emit(self, eid, event):
        for cb in self._cb.get(eid, {}).get(event, []):
            cb({})


class FakeStorage:
    def __init__(self):
        self.sessions = {}
        self.events = []

    def create_session(self, workflow_id=None):
        sid = str(uuid.uuid4())
        self.sessions[sid] = {"status": "idle", "workflow_id": workflow_id}
        return sid

    def update_session(self, sid, updates):
        if updates.get("status") in ("completed", "failed", "cancelled"):
            self.sessions[sid]["completed_at"] = 1
        self.sessions[sid].update(updates)

    def add_event_reference(self, *args, **kwargs):
        self.events.append((args, kwargs))


# ---------------------------------------------------------------- unit tests


class TestBuildConfig:
    def test_single_workflow_maps_to_deterministic(self):
        cfg = StudioRunner.build_config(
            {"config": {"mode": "single", "domain": "code", "num_tasks": 3}})
        assert cfg["debate"] is False
        assert cfg["domain"] == "code"
        assert cfg["num_tasks"] == 3

    def test_multi_workflow_maps_to_debate(self):
        cfg = StudioRunner.build_config({"mode": "multi", "num_tasks": 5})
        assert cfg["debate"] is True
        assert cfg["num_tasks"] == 5

    def test_overrides_win(self):
        cfg = StudioRunner.build_config({"mode": "single"}, debate=True, num_tasks=7)
        assert cfg["debate"] is True
        assert cfg["num_tasks"] == 7

    def test_defaults_when_empty(self):
        cfg = StudioRunner.build_config(None)
        assert cfg["domain"] == "math"
        assert cfg["num_tasks"] == 10
        assert cfg["debate"] is False


class TestStudioRunnerUnit:
    def _runner(self):
        return StudioRunner(storage=FakeStorage(), controller=FakeController())

    def test_start_records_session_and_event(self):
        r = self._runner()
        eid = r.start({"domain": "math", "num_tasks": 2, "debate": False},
                      workflow_id="wf-1")
        assert eid.startswith("studio_")
        assert r.is_active()
        sid = r.status()["session_id"]
        assert r.storage.sessions[sid]["status"] == "running"
        assert any(ev[1]["run_id"] == eid and ev[0][0] == "experiment.started"
                   for ev in r.storage.events)

    def test_finalize_completed(self):
        r = self._runner()
        eid = r.start({"num_tasks": 2}, workflow_id=None)
        sid = r.status()["session_id"]
        # engine emits "stopped" on normal completion
        r.controller.emit(eid, "stopped")
        events = r.drain_events()
        fin = [e for e in events if e["event"] == "finished"]
        assert fin and fin[0]["data"]["status"] == "completed"
        assert r.storage.sessions[sid]["status"] == "completed"
        assert r.is_active() is False

    def test_finalize_cancelled(self):
        r = self._runner()
        eid = r.start({"num_tasks": 2}, workflow_id=None)
        sid = r.status()["session_id"]
        assert r.stop() is True
        r.controller.emit(eid, "stopped")
        fin = [e for e in r.drain_events() if e["event"] == "finished"]
        assert fin[0]["data"]["status"] == "cancelled"
        assert r.storage.sessions[sid]["status"] == "cancelled"

    def test_finalize_failed_when_errors(self):
        r = self._runner()
        eid = r.start({"num_tasks": 2}, workflow_id=None)
        sid = r.status()["session_id"]
        r.controller.states[eid].errors.append("boom")
        r.controller.emit(eid, "stopped")
        fin = [e for e in r.drain_events() if e["event"] == "finished"]
        assert fin[0]["data"]["status"] == "failed"
        assert r.storage.sessions[sid]["status"] == "failed"

    def test_start_rejects_when_busy(self):
        r = self._runner()
        r.start({"num_tasks": 1}, workflow_id=None)
        with pytest.raises(RunnerError):
            r.start({"num_tasks": 1}, workflow_id=None)

    def test_stop_idle_returns_false(self):
        r = self._runner()
        assert r.stop() is False

    def test_status_empty_when_idle(self):
        assert StudioRunner(storage=FakeStorage(), controller=FakeController()).status() == {}


# ------------------------------------------------------- integration (real engine)


@pytest.fixture
def real_engine(tmp_path):
    """A StudioRunner wired to the REAL ExperimentUIController + a real SQLite
    StudioStorage (in a temp file), with LLM-dependent classes stubbed."""
    from experiments.ui_controller import ExperimentUIController

    storage = StudioStorage(db_path=str(tmp_path / "studio.db"))
    controller = ExperimentUIController()
    runner = StudioRunner(storage=storage, controller=controller)

    class FakeResult:
        def __init__(self, valid=True):
            self.is_valid = valid

        def to_dict(self):
            return {"is_valid": self.is_valid, "answer": "ok"}

    class FakeExperimentRunner:
        def __init__(self, config=None):
            self.config = config

        def run_batch(self, tasks, context):
            return [FakeResult(True) for _ in tasks]

        def get_statistics(self):
            return {"validation_pass_rate": 1.0}

    raw_dir = tmp_path / "raw"

    def fake_persist(self, experiment_id, results, mode="deterministic", raw_root=None):
        base = Path(raw_root) if raw_root else raw_dir
        raw = base / f"{experiment_id}.jsonl"
        raw.parent.mkdir(parents=True, exist_ok=True)
        with open(raw, "a", encoding="utf-8") as f:
            for res in results:
                f.write(json.dumps(res.to_dict()) + "\n")
        return raw

    monkey = pytest.MonkeyPatch()
    monkey.setattr("experiments.generation.task_generator.TaskGenerator.generate_batch",
                   lambda self, **kw: [object() for _ in range(kw.get("count", 2))])
    monkey.setattr("experiments.runner.ExperimentRunner", FakeExperimentRunner)
    monkey.setattr(ExperimentUIController, "_persist_results_to_raw", fake_persist)
    runner._monkey = monkey  # keep reference alive for teardown
    return runner, raw_dir


def test_real_engine_completes_run(real_engine, tmp_path):
    runner, raw_dir = real_engine
    eid = runner.start({"seed": 1, "domain": "math", "num_tasks": 2, "debate": False},
                       workflow_id=None)
    assert _wait_until(lambda: not runner.is_active(), timeout=10.0), "run did not finish"

    events = runner.drain_events()
    fin = [e for e in events if e["event"] == "finished"]
    assert fin, "no finished event emitted"
    assert fin[0]["data"]["status"] == "completed"
    assert fin[0]["data"]["metrics"]["tasks_completed"] == 2
    assert fin[0]["data"]["metrics"]["tasks_valid"] == 2

    # The run is still visible on the real controller with truthful metrics.
    state = runner.controller.get_experiment(eid)
    assert state is not None and state.is_running is False
    assert state.errors == []

    # The session was recorded as completed in real SQLite.
    sid = runner.status()["session_id"] if runner.status() else None
    sessions = runner.storage.list_sessions()
    assert sessions and sessions[0]["status"] == "completed"

    # RAW evidence was written (append-only), one line per task.
    raws = list(raw_dir.glob("*.jsonl"))
    assert raws and len(raws[0].read_text(encoding="utf-8").splitlines()) == 2

    # Cleanup the experiment from the real controller.
    runner.controller.delete_experiment(eid)


def test_real_engine_stop_cancels(real_engine):
    runner, _raw_dir = real_engine

    # Make generation block so we can cancel mid-run.
    def blocking(self, **kw):
        time.sleep(2.0)
        return []
    runner._monkey.setattr(
        "experiments.generation.task_generator.TaskGenerator.generate_batch", blocking)

    eid = runner.start({"seed": 2, "domain": "math", "num_tasks": 5, "debate": False},
                       workflow_id=None)
    # Engine marks it running synchronously before returning; wait a tick.
    assert _wait_until(lambda: runner.is_active()), "did not start"
    assert runner.stop() is True

    assert _wait_until(lambda: not runner.is_active(), timeout=10.0), "stop did not finalize"
    fin = [e for e in runner.drain_events() if e["event"] == "finished"]
    assert fin and fin[0]["data"]["status"] == "cancelled"

    # Cleanup the experiment from the real controller.
    runner.controller.delete_experiment(eid)


# ------------------------------------------------------------- UI (offscreen)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


class TestQuickRunUI:
    def test_run_stop_controls_wired(self, qapp, tmp_path):
        from life_mean_studio.launcher.app import LifeMeanStudioApp
        storage = StudioStorage(db_path=str(tmp_path / "ui.db"))
        win = LifeMeanStudioApp(storage=storage)

        assert win.run_btn.isEnabled() is True
        assert win.stop_btn.isEnabled() is False

        # Replace the real runner with a scripted fake to avoid a real engine
        # run; {on_run,on_stop,poll_runner} must still flip the buttons.
        class FakeRunner:
            def __init__(self):
                self.running = False

            def is_active(self):
                return self.running

            def start(self, config, workflow_id=None):
                self.running = True
                return "studio_ui"

            def stop(self):
                self.running = False
                return True

            def drain_events(self):
                # Once the run stopped, emit a terminal finished event on the
                # next poll (mirrors the real engine lifecycle).
                if not self.running:
                    return [{"event": "finished",
                             "data": {"experiment_id": "studio_ui",
                                      "status": "cancelled", "metrics": {}}}]
                return []

        win.runner = FakeRunner()
        win._on_run()
        qapp.processEvents()
        assert win.run_btn.isEnabled() is False
        assert win.stop_btn.isEnabled() is True

        win._on_stop()
        qapp.processEvents()
        win._poll_runner()  # drains the finished event -> re-enables RUN
        assert win.stop_btn.isEnabled() is False
        assert win.run_btn.isEnabled() is True

        win.close()