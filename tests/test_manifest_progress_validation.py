"""`/manifest` doit porter le verdict, pas seulement le compteur de tâches.

Un run terminé annonçait `tasks_completed: 24` sans `tasks_valid` ni `pass_rate` :
pour savoir si le run était bon, il fallait croiser `/api/experiments` et les
traces. Ces tests fixent le contrat : les trois champs sont présents, cohérents,
et `pass_rate` vaut `None` — jamais 0 — quand rien n'a été validé.
"""

from __future__ import annotations

import time

import pytest

from experiments.ui_controller import ExperimentUIController


def _run(monkeypatch, tmp_path, tasks=6):
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(tmp_path / "runs"))
    ui = ExperimentUIController()
    ui.register_experiment("exp_progress", {
        "domain": "math", "difficulty_range": (1, 1), "num_tasks": tasks,
        "seed": 13, "deterministic": True,
    })
    assert ui.start_experiment("exp_progress")
    for _ in range(400):
        time.sleep(0.2)
        if not ui.get_experiment("exp_progress").is_running:
            break
    return ui


def test_manifest_progress_carries_validation(monkeypatch, tmp_path):
    ui = _run(monkeypatch, tmp_path)
    progress = ui.export_experiment_manifest("exp_progress")["progress"]

    assert progress["status"] == "COMPLETED"
    assert progress["tasks_completed"] == 6
    assert progress["tasks_valid"] + progress["tasks_invalid"] == progress["tasks_completed"]
    assert progress["pass_rate"] == pytest.approx(
        progress["tasks_valid"] / progress["tasks_completed"], abs=1e-9
    )
    # un run sain ne peut pas avoir de pass_rate nul avec des tâches valides
    assert progress["tasks_valid"] > 0
    assert progress["pass_rate"] > 0


def test_progress_and_experiment_card_agree(monkeypatch, tmp_path):
    ui = _run(monkeypatch, tmp_path)
    progress = ui.export_experiment_manifest("exp_progress")["progress"]
    card = ui.get_experiment("exp_progress").to_dict()

    assert progress["tasks_valid"] == card["tasks_valid"]
    assert progress["tasks_invalid"] == card["tasks_invalid"]
    assert progress["pass_rate"] == pytest.approx(card["pass_rate"], abs=1e-9)


def test_pass_rate_is_none_before_anything_is_validated():
    from experiments.observability import ExperimentProgress

    assert ExperimentProgress().to_dict()["pass_rate"] is None
