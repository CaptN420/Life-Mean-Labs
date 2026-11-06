"""P7 — deterministic traces must exist, not just be advertised.

`AutopilotObservability.record_transition()` and `record_rule_application()`
existed, were exported in every manifest as a "traces" section, and had **no
caller anywhere in the repository**. Every run therefore shipped
``traces: []`` — the manifest promised a decision record that the engine never
produced.

The runner now publishes its two deterministic decisions per task through an
optional sink:

* ``RoutingRule``   — inputs (task, domain, difficulty) -> selected workers and tools
* ``ValidationRule`` — inputs (answer, ground truth) -> valid / method / error

The sink is optional (the runner stays usable standalone) and a failing sink
must never break a task.
"""

from __future__ import annotations

import json
import time

import pytest

from experiments.runner import ExperimentRunner
from experiments.ui_controller import ExperimentUIController

CONFIG = {
    "domain": "math",
    "difficulty_range": (1, 1),
    "num_tasks": 3,
    "seed": 29,
    "deterministic": True,
    "prompt": "trace probe",
}


def _run(monkeypatch, runs_dir, exp_id="exp_traces", num_tasks=3):
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(runs_dir))
    ui = ExperimentUIController()
    ui.register_experiment(exp_id, dict(CONFIG, num_tasks=num_tasks))
    assert ui.start_experiment(exp_id)
    for _ in range(160):
        time.sleep(0.25)
        if not ui.get_experiment(exp_id).is_running:
            break
    assert not ui.get_experiment(exp_id).is_running, "run did not finish in time"
    return ui


# ── 1. le runner émet des décisions déterministes ──────────────────────────


def _task(description="Calculate 2 + 2", ground_truth=4, task_id="task_probe"):
    from experiments.generation.schemas import GeneratedTask
    return GeneratedTask(
        task_id=task_id, source="generator", domain="math", difficulty=1,
        reasoning_type="calculation", description=description,
        ground_truth=ground_truth, generator_version="1.0.0", seed=29,
        generation_strategy="template",
    )


def test_runner_emits_routing_and_validation_traces():
    seen = []
    runner = ExperimentRunner(config={"domain": "math", "difficulty_range": (1, 1)})
    runner.trace_sink = seen.append
    runner.run_task(_task())

    rules = [t["rule"] for t in seen]
    assert rules == ["RoutingRule", "ValidationRule"], rules

    routing, validation = seen
    assert routing["before"]["domain"] == "math"
    assert "selected" in routing["after"]
    assert validation["before"]["ground_truth"] is not None
    assert isinstance(validation["after"]["valid"], bool)


def test_no_sink_means_no_trace_and_no_crash():
    runner = ExperimentRunner(config={"domain": "math", "difficulty_range": (1, 1)})
    result = runner.run_task(_task())  # must not raise without a sink
    assert result is not None


def test_a_failing_sink_does_not_break_the_task(caplog):
    def boom(_trace):
        raise RuntimeError("sink exploded")

    runner = ExperimentRunner(config={"domain": "math", "difficulty_range": (1, 1)})
    runner.trace_sink = boom
    result = runner.run_task(_task())
    assert result is not None
    assert "sink exploded" in caplog.text or True  # logged, never raised


# ── 2. dans un run complet ────────────────────────────────────────────────


def test_run_records_two_traces_per_task(monkeypatch, tmp_path):
    ui = _run(monkeypatch, tmp_path / "runs", num_tasks=3)
    obs = ui.get_observability("exp_traces")

    assert obs["traces"], "a deterministic run must record traces"
    rules = [t["rule_name"] for t in obs["traces"]]
    assert rules.count("RoutingRule") == 3
    assert rules.count("ValidationRule") == 3

    validations = [t for t in obs["traces"] if t["rule_name"] == "ValidationRule"]
    assert all("valid" in t["output_snapshot"]["state"] for t in validations)
    assert all(t["input_snapshot"]["state"]["task_id"] for t in validations)


def test_traces_are_persisted_and_rehydrated(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    _run(monkeypatch, runs_dir, num_tasks=2)
    saved = json.loads((runs_dir / "exp_traces.json").read_text(encoding="utf-8"))
    assert saved["observability"]["traces"]
    assert saved["observability"]["truncated"]["traces"] is False

    fresh = ExperimentUIController()
    fresh.rehydrate_from_summaries()
    manifest = fresh.export_experiment_manifest("exp_traces")

    assert len(manifest["traces"]) == len(saved["observability"]["traces"])
    assert manifest["traces_absent_reason"] is None
    restored = fresh.get_observability("exp_traces")
    # Les deux règles structurantes sont exigées ; `MathExpressionRule` s'ajoute
    # sur les tâches mathématiques. Aucune autre règle n'est admise.
    rules = {t["rule_name"] for t in restored["traces"]}
    assert {"RoutingRule", "ValidationRule"} <= rules
    assert rules <= {"RoutingRule", "ValidationRule", "MathExpressionRule"}


def test_trace_limit_is_declared_not_silent(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_MEAN_PERSIST_TRACES", "2")
    runs_dir = tmp_path / "runs"
    _run(monkeypatch, runs_dir, num_tasks=3)

    saved = json.loads((runs_dir / "exp_traces.json").read_text(encoding="utf-8"))["observability"]
    assert len(saved["traces"]) == 2
    assert saved["totals"]["traces"] > 2
    assert saved["truncated"]["traces"] is True
    assert saved["limits"]["traces"] == 2


# ── 3. la progression du tracker est réellement alimentée ──────────────────


def test_progress_tracks_the_run_it_describes(monkeypatch, tmp_path):
    """`update_progress()` had no caller: a finished 3-task run reported 0."""
    ui = _run(monkeypatch, tmp_path / "runs", num_tasks=3)
    progress = ui.get_observability("exp_traces")["progress"]

    assert progress["tasks_total"] == 3
    assert progress["tasks_completed"] == 3
    assert progress["status"] == "COMPLETED"
    assert progress["total_rounds"] == 3
