"""P0.4 — a rehydrated run must keep its events and traces, not just its totals.

Before this, the run summary stored state + config only: after a restart the
manifest answered ``events: []`` / ``traces: []`` with a note saying they were
not persisted. The dashboard could therefore never show *why* a run ended the
way it did once the process had restarted.

What is pinned here:
* the summary now carries bounded copies of the tracker's events, traces and
  agent records;
* a fresh controller restores them and serves the same shape as a live one,
  flagged ``rehydrated``;
* truncation is declared (``truncated`` + ``totals``), never silent;
* an old summary without the block still works (backward compatible).
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
    "seed": 17,
    "deterministic": True,
    "prompt": "observability durability probe",
}


def _run_one(monkeypatch, runs_dir, exp_id="exp_obs", num_tasks=2):
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(runs_dir))
    ui = ExperimentUIController()
    config = dict(CONFIG, num_tasks=num_tasks)
    ui.register_experiment(exp_id, config)
    assert ui.start_experiment(exp_id)
    for _ in range(120):
        time.sleep(0.25)
        if not ui.get_experiment(exp_id).is_running:
            break
    assert not ui.get_experiment(exp_id).is_running, "run did not finish in time"
    return ui


def _summary(runs_dir, exp_id="exp_obs"):
    return json.loads((runs_dir / f"{exp_id}.json").read_text(encoding="utf-8"))


# ── 1. écriture ────────────────────────────────────────────────────────────


def test_summary_contains_events_traces_and_agent_records(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    ui = _run_one(monkeypatch, runs_dir)

    live = ui.get_observability("exp_obs")
    assert live["events"], "the live tracker must have recorded events"

    block = _summary(runs_dir)["observability"]
    assert block["events"], "events must land in the summary"
    assert block["agents"], "agent records must land in the summary"
    assert block["totals"]["events"] >= len(block["events"])
    assert block["truncated"]["events"] is False
    # the persisted copy is what the live tracker had
    assert [e.get("event_id") for e in block["events"]] == [e.get("event_id") for e in live["events"]]
    # traces are produced by the deterministic rules now (RoutingRule + ValidationRule)
    assert block["traces"], "deterministic traces must land in the summary"
    assert block["totals"]["traces"] >= len(block["traces"])


def test_event_limit_truncates_and_says_so(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_MEAN_PERSIST_EVENTS", "1")
    runs_dir = tmp_path / "runs"
    _run_one(monkeypatch, runs_dir, num_tasks=6)

    block = _summary(runs_dir)["observability"]
    assert len(block["events"]) == 1
    assert block["totals"]["events"] > 1
    assert block["truncated"]["events"] is True
    assert block["limits"]["events"] == 1


# ── 2. relecture après "restart" ───────────────────────────────────────────


def test_restored_run_serves_events_and_traces(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    _run_one(monkeypatch, runs_dir)
    saved = _summary(runs_dir)["observability"]

    fresh = ExperimentUIController()
    assert fresh.get_observability("exp_obs") is None  # nothing in memory
    assert fresh.rehydrate_from_summaries() == 1

    restored = fresh.get_observability("exp_obs")
    assert restored["rehydrated"] is True
    assert len(restored["events"]) == len(saved["events"])
    assert len(restored["traces"]) == len(saved["traces"])
    assert restored["agents"]
    assert restored["progress"]["tasks_completed"] >= 2
    assert restored["restored_totals"]["events"] == saved["totals"]["events"]


def test_manifest_of_a_restored_run_carries_the_evidence(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    _run_one(monkeypatch, runs_dir)

    fresh = ExperimentUIController()
    fresh.rehydrate_from_summaries()
    manifest = fresh.export_experiment_manifest("exp_obs")

    assert manifest["rehydrated"] is True
    assert manifest["events"], "a restored manifest must not pretend to be empty"
    assert manifest["agents"]
    assert "events" in manifest["note"]
    # deterministic traces are restored too, and no "why is it empty" reason is needed
    assert manifest["traces"], "a restored manifest must carry the traces it recorded"
    assert manifest["traces_absent_reason"] is None
    assert manifest["reproducibility"]["seed"] == 17
    assert manifest["reproducibility_fingerprint"]


def test_truncation_survives_the_restore(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_MEAN_PERSIST_EVENTS", "1")
    runs_dir = tmp_path / "runs"
    _run_one(monkeypatch, runs_dir, num_tasks=6)

    fresh = ExperimentUIController()
    fresh.rehydrate_from_summaries()
    manifest = fresh.export_experiment_manifest("exp_obs")

    assert len(manifest["events"]) == 1
    assert manifest["truncated"]["events"] is True
    assert manifest["restored_totals"]["events"] > 1


# ── 3. compatibilité ascendante ────────────────────────────────────────────


def test_old_summary_without_the_block_still_rehydrates(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    legacy = {
        "schema": "experiment-run/1",
        "experiment_id": "exp_legacy",
        "state": {"experiment_id": "exp_legacy", "is_running": False,
                  "tasks_completed": 3, "pass_rate": 0.5},
        "config": {"seed": 1, "prompt": "legacy"},
        "finished_at": time.time(),
    }
    (runs_dir / "exp_legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(runs_dir))

    fresh = ExperimentUIController()
    fresh.rehydrate_from_summaries()

    manifest = fresh.export_experiment_manifest("exp_legacy")
    assert manifest["events"] == []
    assert manifest["traces"] == []
    assert "0 of 0 events" in manifest["note"]
    assert fresh.get_observability("exp_legacy") is None


def test_live_manifest_carries_the_deterministic_traces(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    ui = _run_one(monkeypatch, runs_dir)

    manifest = ui.export_experiment_manifest("exp_obs")
    assert manifest["events"]
    assert manifest["traces"], "RoutingRule/ValidationRule traces must be recorded"
    # Les deux règles structurantes doivent être là. `MathExpressionRule`
    # s'ajoute pour les tâches mathématiques (expression, paramètres, verdict) :
    # la comparaison est donc un sous-ensemble exigé, pas une égalité stricte.
    rules = {t["rule_name"] for t in manifest["traces"]}
    assert {"RoutingRule", "ValidationRule"} <= rules
    assert rules <= {"RoutingRule", "ValidationRule", "MathExpressionRule"}
    assert manifest["traces_absent_reason"] is None
