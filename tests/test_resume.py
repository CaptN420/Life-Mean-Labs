"""Real resumption: `continue_experiment` must resume, not restart.

Before this change `continue_experiment` called `start_experiment` (a fresh run
from task 0) and, for a finished run, silently restarted it. A user who pressed
"Continue" got a brand-new experiment with no warning.

The contract pinned here:

1. nothing recorded → refuse (and say why);
2. interrupted run → only the remaining tasks execute, evidence accumulates;
3. finished run → refuse, never restart silently;
4. checkpoint that no longer matches the config → refuse;
5. a corrupt checkpoint line is skipped, never guessed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from experiments.runner import ExperimentRunner
from experiments.ui_controller import ExperimentUIController


def _wait_idle(controller: ExperimentUIController, exp_id: str, timeout: float = 60.0) -> bool:
    """Wait until the worker thread for ``exp_id`` has left the registry."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if exp_id not in controller._worker_threads:
            return True
        time.sleep(0.02)
    return False


def _lines(path: Path) -> list:
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _task_entries(controller: ExperimentUIController, exp_id: str) -> list:
    _, entries = controller._load_progress(exp_id)
    return entries


def _raw_lines(tmp_path: Path, exp_id: str) -> list:
    raw = tmp_path / "data" / "raw_debates" / f"{exp_id}.jsonl"
    return _lines(raw)


@pytest.fixture
def ctl(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.chdir(tmp_path)  # RAW root follows the cwd by design
    controller = ExperimentUIController()
    yield controller


def _stop_after(monkeypatch, controller, exp_id, n):
    """Stop the run right after the n-th executed task (real cancellation).

    Returns the call counter and the genuine method, so the caller can restore
    it without accidentally restoring the wrapper.
    """
    original = ExperimentRunner.run_task
    calls = {"n": 0}

    def wrapper(self, task, context=None):
        calls["n"] += 1
        result = original(self, task, context)
        if calls["n"] == n:
            controller.stop_experiment(exp_id)
        return result

    monkeypatch.setattr(ExperimentRunner, "run_task", wrapper)
    return calls, original


@pytest.fixture
def interrupted(tmp_path, ctl, monkeypatch):
    """A run stopped after 3 of 6 tasks, with its checkpoint on disk."""
    exp_id = "exp_resume"
    ctl.register_experiment(exp_id, {"seed": 42, "domain": "math", "num_tasks": 6})
    calls, original = _stop_after(monkeypatch, ctl, exp_id, 3)

    assert ctl.start_experiment(exp_id) is True
    assert _wait_idle(ctl, exp_id), "worker did not stop"

    entries = _task_entries(ctl, exp_id)
    assert len(entries) == 3, f"expected 3 recorded tasks, got {len(entries)}"
    assert calls["n"] == 3
    assert len(_raw_lines(tmp_path, exp_id)) == 3
    monkeypatch.setattr(ExperimentRunner, "run_task", original)
    return exp_id


# ── 1. rien à reprendre ─────────────────────────────────────────────────────


def test_continue_without_checkpoint_is_refused(ctl):
    ctl.register_experiment("exp_none", {"seed": 42, "domain": "math", "num_tasks": 3})

    assert ctl.continue_experiment("exp_none") is False
    state = ctl.get_experiment("exp_none")
    assert state.is_running is False
    assert any("aucune progression" in e for e in state.errors)


def test_continue_of_unknown_experiment_is_refused(ctl):
    assert ctl.continue_experiment("nope") is False


# ── 2. reprise réelle ───────────────────────────────────────────────────────


def test_continue_runs_only_the_remaining_tasks(tmp_path, ctl, interrupted, monkeypatch):
    before = _task_entries(ctl, interrupted)
    assert len(before) == 3

    original = ExperimentRunner.run_task
    executed = []

    def counting(self, task, context=None):
        executed.append(task.description)
        return original(self, task, context)

    monkeypatch.setattr(ExperimentRunner, "run_task", counting)

    assert ctl.continue_experiment(interrupted) is True
    assert _wait_idle(ctl, interrupted), "resume did not finish"

    after = _task_entries(ctl, interrupted)
    assert len(after) == 6, f"expected 6 recorded tasks, got {len(after)}"
    assert len(executed) == 3, f"resume must not re-run completed tasks, ran {len(executed)}"

    # evidence accumulates, it is not rewritten
    assert len(_raw_lines(tmp_path, interrupted)) == 6
    indices = sorted(e["index"] for e in after)
    assert indices == [0, 1, 2, 3, 4, 5]

    state = ctl.get_experiment(interrupted)
    assert state.tasks_completed == 6
    assert state.tasks_valid == sum(1 for e in after if e["is_valid"])
    assert state.current_pass_rate == pytest.approx(state.tasks_valid / 6)


def test_metrics_are_cumulative_not_reset_by_resume(ctl, interrupted):
    state_before = ctl.get_experiment(interrupted)
    valid_before = state_before.tasks_valid
    assert valid_before >= 0

    assert ctl.continue_experiment(interrupted) is True
    assert _wait_idle(ctl, interrupted)

    state_after = ctl.get_experiment(interrupted)
    assert state_after.tasks_completed == 6
    assert state_after.tasks_valid >= valid_before  # earlier verdicts are kept


# ── 3. une expérience terminée n'est pas une reprise ───────────────────────


def test_continue_of_finished_run_is_refused_and_does_not_restart(ctl, tmp_path):
    exp_id = "exp_done"
    ctl.register_experiment(exp_id, {"seed": 11, "domain": "math", "num_tasks": 2})
    assert ctl.start_experiment(exp_id) is True
    assert _wait_idle(ctl, exp_id)

    before = _task_entries(ctl, exp_id)
    assert len(before) == 2

    assert ctl.continue_experiment(exp_id) is False
    state = ctl.get_experiment(exp_id)
    assert any("déjà terminée" in e for e in state.errors)
    assert len(_task_entries(ctl, exp_id)) == 2      # nothing ran again
    assert len(_raw_lines(tmp_path, exp_id)) == 2


# ── 4. configuration modifiée ──────────────────────────────────────────────


def test_continue_refuses_when_seed_changed(ctl, interrupted):
    ctl._configurations[interrupted]["seed"] = 7

    assert ctl.continue_experiment(interrupted) is False
    state = ctl.get_experiment(interrupted)
    assert any("configuration" in e for e in state.errors)
    assert len(_task_entries(ctl, interrupted)) == 3


# ── 5. checkpoint abîmé ────────────────────────────────────────────────────


def test_corrupt_checkpoint_line_is_skipped_not_guessed(ctl, interrupted):
    path = ctl._progress_path(interrupted)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{this is not json\n")

    assert ctl.continue_experiment(interrupted) is True
    assert _wait_idle(ctl, interrupted)
    assert len(_task_entries(ctl, interrupted)) == 6


# ── 6. NO DELETE : l'ancien checkpoint est archivé ─────────────────────────


def test_restart_archives_the_previous_checkpoint(ctl, interrupted):
    before = ctl._progress_path(interrupted)
    original_meta = before.read_text(encoding="utf-8").splitlines()[0]

    ctl.register_experiment(interrupted, {"seed": 42, "domain": "math", "num_tasks": 6})
    assert ctl.start_experiment(interrupted) is True
    assert _wait_idle(ctl, interrupted)

    archived = list(before.parent.glob("*.jsonl.bak"))
    assert archived, "previous checkpoint must be archived, not deleted"
    assert original_meta in archived[0].read_text(encoding="utf-8")
