"""Engine timeouts (P4): nothing in core/runtime, core/workers or the runner had one.

Before this, a stalled tool or provider blocked an experiment indefinitely, and
an LLM call could sit on the OpenAI client's 600 s default (with retries).

The contract pinned here:

1. a task that exceeds ``task_timeout_seconds`` returns an explicit
   ``TASK_TIMEOUT`` failure — not a silent success, not an empty answer;
2. its late result is discarded (never counted twice);
3. a run that exceeds ``run_timeout_seconds`` stops itself with ``RUN_TIMEOUT``
   and leaves the recorded tasks resumable;
4. the LLM client always carries a finite timeout and does not retry silently.
"""

from __future__ import annotations

import sys
import time
import types

import pytest

from experiments.generation.schemas import GeneratedTask
from experiments.runner import ExperimentRunner


def _task() -> GeneratedTask:
    return GeneratedTask(
        domain="math",
        difficulty=1,
        description="Find the GCD of 12 and 8",
        ground_truth=4,
    )


# ── 1/2. timeout de tâche ───────────────────────────────────────────────────


def test_task_timeout_is_explicit_and_prompt(monkeypatch):
    runner = ExperimentRunner(config={"task_timeout_seconds": 0.2})

    def slow(self, task, routing_decision):
        time.sleep(3.0)
        return 4

    monkeypatch.setattr(ExperimentRunner, "_execute_task", slow)

    started = time.time()
    result = runner.run_task(_task())
    elapsed = time.time() - started

    assert elapsed < 1.5, f"run_task must stop at its deadline, took {elapsed:.1f}s"
    assert result.error is not None and result.error.startswith("TASK_TIMEOUT")
    assert result.answer is None
    assert result.is_valid is False
    assert result.is_successful is False
    assert result.metadata.get("timed_out") is True


def test_late_result_is_discarded_not_double_counted(monkeypatch):
    runner = ExperimentRunner(config={"task_timeout_seconds": 0.2})

    def slow(self, task, routing_decision):
        time.sleep(0.6)
        return 4

    monkeypatch.setattr(ExperimentRunner, "_execute_task", slow)
    result = runner.run_task(_task())
    assert result.error.startswith("TASK_TIMEOUT")

    time.sleep(0.8)  # let the abandoned thread finish
    assert len(runner._results) == 1, "the late result must not be appended"
    stats = runner.get_statistics()
    assert stats["total_runs"] == 1
    assert stats["successful_runs"] == 0


def test_no_timeout_configured_keeps_old_behaviour(monkeypatch):
    runner = ExperimentRunner(config={"task_timeout_seconds": 0})

    def fast(self, task, routing_decision):
        return task.ground_truth

    monkeypatch.setattr(ExperimentRunner, "_execute_task", fast)
    result = runner.run_task(_task())

    assert result.error is None
    assert result.is_valid is True
    assert len(runner._results) == 1


# ── 3. timeout d'exécution complète ────────────────────────────────────────


def test_run_timeout_stops_the_loop_and_keeps_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.chdir(tmp_path)

    from experiments.ui_controller import ExperimentUIController

    controller = ExperimentUIController()
    config = {"seed": 3, "domain": "math", "num_tasks": 60,
              "run_timeout_seconds": 0.15}
    controller.register_experiment("exp_run_timeout", config)

    original = ExperimentRunner.run_task

    def slow(self, task, context=None):
        time.sleep(0.05)
        return original(self, task, context)

    monkeypatch.setattr(ExperimentRunner, "run_task", slow)

    assert controller.start_experiment("exp_run_timeout") is True
    deadline = time.time() + 30
    while "exp_run_timeout" in controller._worker_threads and time.time() < deadline:
        time.sleep(0.02)

    state = controller.get_experiment("exp_run_timeout")
    assert any(e.startswith("RUN_TIMEOUT") for e in state.errors), state.errors
    assert 0 < state.tasks_completed < 60, state.tasks_completed

    # recorded tasks stay resumable — the checkpoint exists and is shorter
    meta, entries = controller._load_progress("exp_run_timeout")
    assert meta is not None and meta["total"] == 60
    assert len(entries) == state.tasks_completed


# ── 4. timeouts du client LLM ──────────────────────────────────────────────


class _FakeCompletions:
    def __init__(self, record):
        self.record = record

    def create(self, **kwargs):
        self.record.append(kwargs)
        raise TimeoutError("Request timed out.")

    def list(self):
        return types.SimpleNamespace(data=[])


def _install_fake_openai(monkeypatch, record, init_kwargs):
    class _OpenAI:
        def __init__(self, **kwargs):
            init_kwargs.append(kwargs)
            self.chat = types.SimpleNamespace(completions=_FakeCompletions(record))
            self.models = types.SimpleNamespace(list=lambda: types.SimpleNamespace(data=[]))

    module = types.ModuleType("openai")
    module.OpenAI = _OpenAI
    monkeypatch.setitem(sys.modules, "openai", module)
    return module


def test_llm_client_has_a_finite_timeout_and_no_silent_retries(monkeypatch):
    from philosophical_council.llm.client import LLMClient

    init_kwargs, calls = [], []
    _install_fake_openai(monkeypatch, calls, init_kwargs)

    client = LLMClient("http://localhost:1234/v1", "lm-studio")

    assert init_kwargs and init_kwargs[0]["timeout"] == client.timeout
    assert client.timeout > 0 and client.timeout < 600
    assert init_kwargs[0]["max_retries"] == 0


def test_llm_call_passes_its_timeout_and_reports_a_timeout(monkeypatch):
    from philosophical_council.llm.client import LLMClient

    init_kwargs, calls = [], []
    _install_fake_openai(monkeypatch, calls, init_kwargs)

    client = LLMClient("http://localhost:1234/v1", "lm-studio", timeout=7.5)
    text, finish_reason = client.chat([{"role": "user", "content": "hi"}], model="m")

    assert calls[0]["timeout"] == 7.5
    assert finish_reason == "timeout", finish_reason
    assert "LLM_TIMEOUT" in text


def test_timeout_is_overridable_per_client(monkeypatch):
    from philosophical_council.llm.client import LLMClient

    init_kwargs, calls = [], []
    _install_fake_openai(monkeypatch, calls, init_kwargs)

    client = LLMClient("http://localhost:1234/v1", "lm-studio", timeout=2.0)
    assert client.timeout == 2.0
    assert init_kwargs[0]["timeout"] == 2.0
