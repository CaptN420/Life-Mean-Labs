"""P0.3 — a finished run must still be listed after a process restart.

Before this, restarting the dashboard emptied `/api/experiments` while the RAW
evidence stayed on disk: the data existed, the state that makes it queryable did
not. The controller now writes a run summary per finished experiment and
rebuilds its registry from those summaries at start.
"""

from __future__ import annotations

import json
import time

import pytest

from experiments.ui_controller import ExperimentUIController


CONFIG = {
    "domain": "math",
    "difficulty_range": (1, 1),
    "num_tasks": 2,
    "seed": 13,
    "deterministic": True,
    "prompt": "gcd durability probe",
}


def _run_one(monkeypatch, runs_dir, exp_id="exp_durable"):
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(runs_dir))
    ui = ExperimentUIController()
    ui.register_experiment(exp_id, dict(CONFIG))
    assert ui.start_experiment(exp_id)
    for _ in range(60):
        time.sleep(0.25)
        if not ui.get_experiment(exp_id).is_running:
            break
    state = ui.get_experiment(exp_id)
    assert not state.is_running, "run did not finish in time"
    return ui, state


def test_finished_run_writes_a_summary(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    ui, state = _run_one(monkeypatch, runs_dir)
    summary = runs_dir / "exp_durable.json"
    assert summary.exists()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["schema"] == "experiment-run/1"
    assert payload["experiment_id"] == "exp_durable"
    assert payload["state"]["tasks_completed"] >= 2
    assert payload["config"]["seed"] == 13


def test_restart_rehydrates_the_registry(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    _run_one(monkeypatch, runs_dir)

    # New process: fresh controller, nothing in memory, same summaries on disk.
    fresh = ExperimentUIController()
    assert fresh.get_dashboard_data()["total_experiments"] == 0
    restored = fresh.rehydrate_from_summaries()
    assert restored == 1

    data = fresh.get_dashboard_data()
    assert data["total_experiments"] == 1
    entry = data["experiments"]["exp_durable"]
    assert entry["status"] == "COMPLETED"
    assert entry["is_running"] is False
    assert entry["rehydrated"] is True
    assert entry["tasks_completed"] >= 2
    # config survived, so the run is re-executable with the same parameters
    assert fresh._configurations["exp_durable"]["seed"] == 13


def test_rehydration_does_not_duplicate_or_resurrect_running(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    ui, _ = _run_one(monkeypatch, runs_dir)
    # Rehydrating the SAME controller must not double-register or flip state.
    assert ui.rehydrate_from_summaries() == 0
    assert ui.get_dashboard_data()["total_experiments"] == 1
    assert ui.get_dashboard_data()["running_count"] == 0


def test_corrupt_summary_is_skipped(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    _run_one(monkeypatch, runs_dir)
    (runs_dir / "broken.json").write_text("{not json", encoding="utf-8")
    (runs_dir / "foreign.json").write_text(
        json.dumps({"schema": "other/9", "experiment_id": "exp_foreign"}), encoding="utf-8"
    )

    fresh = ExperimentUIController()
    assert fresh.rehydrate_from_summaries() == 1
    assert set(fresh.get_dashboard_data()["experiments"]) == {"exp_durable"}


def test_no_runs_dir_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(tmp_path / "does-not-exist"))
    assert ExperimentUIController().rehydrate_from_summaries() == 0


def test_rehydrated_run_still_exports_a_manifest(monkeypatch, tmp_path):
    """After a restart the manifest must exist and be honest: exact config and
    seed, rehydrated flag set, and the persisted events restored.

    (P0.4 changed this: events used to be lost on restart — the assertion here
    said ``events == []``. They are now persisted as a bounded copy, and the
    runner emits RoutingRule/ValidationRule traces, so the test asserts the new
    contract instead of the old limitation.)"""
    runs_dir = tmp_path / "runs"
    _run_one(monkeypatch, runs_dir)

    fresh = ExperimentUIController()
    fresh.rehydrate_from_summaries()
    manifest = fresh.export_experiment_manifest("exp_durable")
    assert manifest is not None
    assert manifest["rehydrated"] is True
    assert manifest["config"]["seed"] == 13
    assert manifest["reproducibility"]["seed"] == 13
    assert manifest["events"], "events are persisted now, not lost on restart"
    assert manifest["traces"], "deterministic traces are recorded and persisted"
    assert manifest["traces_absent_reason"] is None
    assert manifest["reproducibility_fingerprint"]
    assert "bounded copies" in manifest["note"]

    # an unknown id is still a real 404, never an empty manifest
    assert fresh.export_experiment_manifest("exp_nope") is None
