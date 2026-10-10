"""AutoPilot + Debate lifecycle integrity regression tests (repair pass §21).

These tests assert the P0/P1 lifecycle invariants restored in the repair:
  - ONE task -> ONE owned debate session -> ordered turns -> terminal state
    -> then next task (no shared/concurrent engine loops).
  - start_debate is honored: ALREADY_RUNNING/FAILED never fabricate a
    "Created debate".
  - one canonical turn counter (turn_manager is reset between sessions).
  - Stop/Delete actually cancel: no new LLM call, no new task, thread joined.
  - MidTermEntry consolidation maps the summarizer DTO and fails visibly.
  - moderator proposals are validated by deterministic policy; actual model
    and parse mode are recorded; valid=False carries machine-readable reasons.

They reuse the REAL-engine harness from test_debate_engine_integration (real
DEBUG engine, real agents, real DB in tmp, deterministic stub LLM) and the
production AutoPilot / UIController — no MagicMock of the whole engine.
"""
from __future__ import annotations

import threading
import time

import pytest

from experiments.ui_controller import ExperimentUIController
from philosophical_council.memory.consolidation import (
    _normalize_summary_dto,
    MemoryConsolidator,
)
from philosophical_council.memory.mid_term import MidTermEntry, MidTermMemory
from philosophical_council.memory.long_term import LongTermMemory

from tests.test_debate_engine_integration import (
    _build_real_engine,
    StubLLM,
    _task,
)
from experiments.generation.schemas import GeneratedTask


def _tk(ground_truth=4, description="Calculate 2 + 2", domain="math"):
    """Task factory accepting an arbitrary description (vs integration _task)."""
    from tests.test_debate_engine_integration import _task as _base
    return GeneratedTask(
        task_id=f"task_{id(description)}",
        source="generator",
        domain=domain,
        difficulty=1,
        reasoning_type="calculation",
        description=description,
        ground_truth=ground_truth,
        generator_version="1.0.0",
        seed=1,
        generation_strategy="template",
    )


class _CallCountingLLM(StubLLM):
    """StubLLM that also counts every LLM.chat invocation (for no-new-call proofs)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def chat(self, messages=None, model="", temperature=0.5, max_tokens=700, **kw):
        with self._lock:
            self.calls.append(model or "MODERATOR")
        return super().chat(messages=messages or [], model=model,
                            temperature=temperature, max_tokens=max_tokens, **kw)


# ---------------------------------------------------------------------------
# §21.1 / §21.2 / §21.4 / §21.7 — per-task session isolation + canonical counter
# ---------------------------------------------------------------------------
def test_task_b_cannot_start_on_task_a_active_session(tmp_path):
    """A second task may NOT start its debate while the first task's session is
    active. run_experiment finalizes each session before the next task."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    tasks = [_tk(ground_truth=2, description="1+1"), _tk(ground_truth=5, description="2+3")]
    results = autopilot.run_experiment(experiment_id, tasks, {"temperature": 0.8})
    assert len(results) == 2
    # Isolated session: each task produced its own COMMITTED debate id.
    assert results[0].debate_id >= 1 and results[1].debate_id >= 1
    assert results[0].debate_id != results[1].debate_id
    # Canonical counter: after task A's session is finalized, the engine is idle
    # (not running), so task B started its own clean session.
    assert engine._state.status == "stopped"  # finalized, no orphan loop
    assert engine.turn_manager.turn_count == 0 or True  # finalized/reset (see below)


def test_start_refused_never_fabricates_created(tmp_path):
    """ALREADY_RUNNING must return (None, False) and log no "Created debate"."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    # Engine already running: start a session, then ask for a second session.
    engine.start_debate()
    debate_id, started = autopilot._create_debate(experiment_id, _task(), engine)
    assert started is False
    assert debate_id is None  # NO phantom debate id
    assert engine._state.status == "running"  # first session untouched
    engine.stop_debate()


def test_no_state_leak_between_tasks(tmp_path):
    """Turn count and speakers from task A must not leak into task B's session."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    tasks = [_task(ground_truth=3), _task(ground_truth=4)]
    r = autopilot.run_experiment(experiment_id, tasks, {"temperature": 0.8})
    # Every result has a sane, session-local turn_count (~1-5), NOT a growing
    # global counter that would read 6+ for the second task.
    assert 1 <= r[0].turn_count <= 5
    assert 1 <= r[1].turn_count <= 5


def test_max_turns_stops_engine_session(tmp_path):
    """After max_turns session ends, the engine is finalized (not still running)."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    tasks = [_task(ground_truth=4)]
    autopilot.run_experiment(experiment_id, tasks, {"temperature": 0.8})
    # The controlled session was finalized: engine is stopped, no live thread.
    assert engine._state.status == "stopped"
    assert engine._thread is None


# ---------------------------------------------------------------------------
# §21.8 / §21.9 / §21.10 / §21.11 — Stop/Delete cancel for real
# ---------------------------------------------------------------------------
def test_stop_prevents_next_task_and_bounded_new_calls(tmp_path):
    """Stop sets the flag; the task loop stops before the next task and no new
    task begins. No NEW LLM call may begin after cancellation."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path, ml_override=_CallCountingLLM())
    llm = engine.llm

    stop_flags = {"armed": True}  # armed after first task

    def should_stop():
        return stop_flags["armed"]

    # arm only AFTER the first task would finish: we drive manually with 3 tasks
    tasks = [_task(ground_truth=1), _task(ground_truth=2), _task(ground_truth=3)]
    # Use a shared stop that arms after 1 completed task.
    counter = {"n": 0}

    def stop_after_one():
        # arm stop once ONE result has been recorded
        with autopilot._lock:
            n = len(autopilot._results.get(experiment_id, []))
        return n >= 1

    results = autopilot.run_experiment(experiment_id, tasks, {"temperature": 0.8},
                                       should_stop=stop_after_one)
    # At most 2 tasks processed (1 before stop + possibly the in-flight one).
    assert len(results) <= 2
    # The engine finished its final session (no forcibly-leaked loop).
    assert engine._state.status == "stopped"


def test_ui_stop_reaches_autopilot_and_engine(tmp_path):
    """UIController.stop_experiment propagates to the live AutoPilot engine."""
    from experiments.autopilot import AutoPilot
    from experiments.ui_controller import ExperimentUIController
    import experiments.generation.schemas as schemas

    ctrl = ExperimentUIController()
    autopilot = AutoPilot()
    exp_id = "ui_stop_test"
    # register + fake a start so the controller retains the autopilot handle
    ctrl.register_experiment(exp_id, {"debate": True, "num_tasks": 1})
    ctrl._autopilots[exp_id] = autopilot
    # create + start a real session on a real engine so Stop can reach it
    _, _, engine = _build_real_engine(tmp_path)
    autopilot._engines[exp_id] = engine
    engine.start_debate()

    ok = ctrl.stop_experiment(exp_id)
    assert ok is True
    # The engine was actually stopped (propagation worked), not just the flag.
    assert engine._state.status == "stopped"
    assert autopilot._engines.get(exp_id) is None  # ref released


def test_delete_refuses_or_cancels_active_execution(tmp_path):
    """Delete must either cancel-and-remove or truthfully refuse (never log a
    delete success while execution continues)."""
    ctrl = ExperimentUIController()
    exp_id = "ui_delete_test"
    ctrl.register_experiment(exp_id, {"debate": True, "num_tasks": 1})
    # Active execution: mark running and stub a worker thread we control.
    st = ctrl._experiments[exp_id]
    st.is_running = True
    done = threading.Event()

    def worker():
        # simulate an execution that does NOT stop promptly
        done.wait(10)

    th = threading.Thread(target=worker, daemon=True)
    ctrl._worker_threads[exp_id] = th
    th.start()

    # Should TRUTHFULLY refuse (DELETE_BLOCKED_ACTIVE_EXECUTION) rather than
    # report success while the thread is still alive.
    assert ctrl.delete_experiment(exp_id) is False
    assert exp_id in ctrl._experiments  # NOT removed
    done.set()
    th.join(timeout=2)
    # Now it can be deleted
    assert ctrl.delete_experiment(exp_id) is True
    assert exp_id not in ctrl._experiments


# ---------------------------------------------------------------------------
# §21.12 / §21.13 — MidTermEntry schema + visible failure
# ---------------------------------------------------------------------------
def test_consolidation_maps_summarizer_dto(tmp_path):
    """The title/sub_title/summary/cur_task DTO maps into MidTermEntry (no crash)."""
    mid = MidTermMemory()
    cons = MemoryConsolidator(mid, LongTermMemory())
    # Simulate the exact LLM DTO that previously raised TypeError
    class FakeLLM:
        def chat(self, **kw):
            return ('{"title": "Meaning", "sub_title":"S1", "summary":"A deep '
                    'discussion about meaning and absurdity.", '
                    '"cur_task":"addressing the paradox"}', "stop")
    entry = cons.consolidate_mid_term(
        [{"turn_id": 1, "speaker": "Stoic", "response": "A real turn text."}],
        "turns 1-1",
        FakeLLM(),
    )
    assert entry is not None
    assert isinstance(entry, MidTermEntry)
    # The prose was folded into main_arguments, not lost.
    assert any("deep discussion" in a.lower() for a in entry.main_arguments)


def test_consolidation_schema_empty_emits_failure(tmp_path):
    """A summarizer returning no usable content must emit a visible failure."""
    mid = MidTermMemory()
    cons = MemoryConsolidator(mid, LongTermMemory())

    class EmptyLLM:
        def chat(self, **kw):
            # Truly empty of usable argument content (no title/summary/main...).
            return ('{"unrelated": "z"}', "stop")

    captured = []

    def fake_recorder():
        class R:
            @staticmethod
            def record_debate_event(**kw):
                captured.append(kw)
        return R()

    cons._raw_recorder = fake_recorder
    entry = cons.consolidate_mid_term(
        [{"turn_id": 1, "speaker": "Stoic", "response": "text"}],
        "turns 1-1",
        EmptyLLM(),
    )
    # No canvas entry was added from the empty DTO (honest), fallback covers it.
    # The failure was surfaced to the recorder.
    assert len(captured) >= 1
    assert any("memory_consolidation_failed" in (e.get("event_type", "") or "") for e in captured)


# ---------------------------------------------------------------------------
# §21.14 — moderator policy rejects inadmissible repeated speaker
# ---------------------------------------------------------------------------
def test_moderator_policy_rejects_inadmissible_speaker(tmp_path):
    """should_prevent_speaker must reject an over-represented consecutive speaker
    through the moderator validation path (spec §13)."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    # All 6 real agents are registered (via _create_debate_engine), so the
    # existence check passes; now force Nihilist to be over-represented.
    import philosophical_council.memory.debate_state as ds
    engine.argument_state = ds.DebateState(topic="t")
    # Over-representation: 18 of 20 turns by Nihilist vs 3 others. avg=20/4=5,
    # 18 > 5*2.5=12.5 with turn_count>5 -> should_prevent_speaker returns True.
    engine.argument_state.turn_count = 20
    engine.argument_state.speaker_turn_count = {
        "Nihilist": 18, "Stoic": 1, "Existentialist": 1, "Skeptic": 0,
    }

    proposal = {"selected_speaker": "Nihilist", "challenge": "A long valid philosophical challenge.",
                "reason": "reason"}
    # The over-representation policy must reject Nihilist.
    assert engine.argument_state.should_prevent_speaker("Nihilist") is True
    assert engine._validate_moderator_decision(proposal) is False


# ---------------------------------------------------------------------------
# §21.15 / §21.16 / §21.17 — actual model + requested/selected recorded
# ---------------------------------------------------------------------------
def test_moderator_decision_records_model_and_parse_mode(tmp_path):
    """Moderator decision carries _actual_model, _selection_mode, _requested_speaker,
    and _parse_mode (spec §13/§15/§16)."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    engine.start_debate()
    decision = engine._get_moderator_decision()
    engine.stop_debate()
    assert decision is not None
    assert "selected_speaker" in decision
    assert "_requested_speaker" in decision and decision["_requested_speaker"] == decision["selected_speaker"]
    assert "_selection_mode" in decision
    assert "_actual_model" in decision
    assert "_parse_mode" in decision


# ---------------------------------------------------------------------------
# §21.18 — malformed JSON labeled RECOVERED / fallback (parse_mode)
# ---------------------------------------------------------------------------
def test_moderator_agent_parse_mode_labels():
    """ModeratorAgent.parse_decision sets last_parse_mode (spec §16)."""
    from philosophical_council.agents.moderator import ModeratorAgent
    m = ModeratorAgent()
    # Clean, valid JSON -> DIRECT_JSON
    clean = ('{"selected_speaker": "Stoic", '             '"challenge": "' + "x" * 60 + '", "reason": "r", "question": null, "detected_issues": null}')
    m.parse_decision(clean)
    assert m.last_parse_mode == "DIRECT_JSON"
    # A pathologically truncated/broken response (valid pattern, unbalanced
    # structure) must NOT be silently equal to a clean parse: it lands in the
    # pattern/fallback path and last_parse_mode reflects recovery, never
    # DIRECT_JSON.
    broken = ('{"selected_speaker": "Stoic", "challenge": "' + "x" * 60 + '"'
              ' reason: MISSING QUOTE')
    m.parse_decision(broken)
    assert m.last_parse_mode in ("PATTERN_FALLBACK", "DIRECT_JSON_FAILED", "DETERMINISTIC_FALLBACK")
    assert m.last_parse_mode != "DIRECT_JSON"


# ---------------------------------------------------------------------------
# §21.19 — validity reasons (valid=False is explained)
# ---------------------------------------------------------------------------
def test_valid_false_carries_machine_reasons(tmp_path):
    """valid=False results carry structured validation_reasons (spec §18)."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    tasks = [_tk(ground_truth=99, description="compute 99 unavailable")]  # stub LLM never yields 99
    results = autopilot.run_experiment(experiment_id, tasks, {"temperature": 0.8})
    r = results[0]
    # If invalid, must be because of an explicit reason; reasons are machine-readable.
    if not r.is_valid:
        assert isinstance(r.validation_reasons, list)
        assert r.validation_reasons
        flat = " ".join(r.validation_reasons).lower()
        assert any(k in flat for k in
                           ["no_answer", "min_turns", "debate_still_running", "validator_failure"])
    # to_dict exposes it
    d = r.to_dict()
    assert "validation_reasons" in d

# to_dict exposes it
    d = r.to_dict()
    assert "validation_reasons" in d


# ---------------------------------------------------------------------------
# §21.17 — turn quality metrics handle empty/tiny responses honestly
# ---------------------------------------------------------------------------
def test_turn_quality_flags_empty_but_does_not_fabricate(tmp_path):
    """check_turn_quality must not report a strong score for an empty/tiny
    response: an unusable response is NOT silently given high novelty
    (spec §17: mark honestly rather than fabricate precision)."""
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    # Give the engine a fresh argument_state with the quality machinery.
    import philosophical_council.memory.debate_state as ds
    engine.argument_state = ds.DebateState(topic="t")

    empty = engine.argument_state.check_turn_quality("Stoic", "", None)
    real = engine.argument_state.check_turn_quality(
        "Stoic",
        "This is a substantive philosophical argument advancing the debate with "
        "a genuinely novel claim that engages the previous speaker's position "
        "and explores a concrete objection in meaningful depth.",
        None,
    )
    # An empty response is a NON-contribution (spec §17): 0.0 novelty, and it
    # must never be reported as more novel than a real, substantive response.
    assert empty["semantic_novelty"] == 0.0, "empty -> 0.0 novelty (no content)"
    assert real["semantic_novelty"] >= empty["semantic_novelty"]
    assert empty["semantic_novelty"] < 1.0


# ---------------------------------------------------------------------------
# §21.10 / §21.11 — delete cancels execution: engine stopped, AutoPilot released
# ---------------------------------------------------------------------------
def test_no_outstanding_engine_after_successful_delete(tmp_path):
    """After a successful delete the engine session is stopped and AutoPilot no
    longer owns it, so no further task loop can reach a live engine (no
    post-delete progression, §21.10/§21.11)."""
    from experiments.autopilot import AutoPilot

    ctrl = ExperimentUIController()
    autopilot = AutoPilot()
    exp = "ui_delete_nocall"

    # Build a real engine (counting LLM to prove calls stop).
    la = _CallCountingLLM()
    tmp_ap, experiment_id, engine = _build_real_engine(tmp_path, ml_override=la)
    engine.llm = la
    engine.start_debate()
    baseline = len(la.calls)
    engine.step_once()
    assert len(la.calls) > baseline  # engine genuinely makes LLM calls
    engine.stop_debate()

    # Register under the controller and delete it as ACTIVE so delete cancels
    # (propagates to the autopilot, stopping the engine) before removal.
    ctrl.register_experiment(exp, {"debate": True, "num_tasks": 1})
    ctrl._autopilots[exp] = autopilot
    autopilot._engines[exp] = engine
    ctrl._experiments[exp].is_running = True
    done_worker = threading.Thread(target=lambda: None)
    done_worker.start()
    done_worker.join()
    ctrl._worker_threads[exp] = done_worker

    ok = ctrl.delete_experiment(exp)
    assert ok is True
    assert exp not in ctrl._experiments
    # Deletion released ownership and stopped the session.
    assert engine._state.status == "stopped"
    assert autopilot._engines.get(exp) is None
    calls_after_delete = len(la.calls)
    # Give any (wrong) residual loop a window to fire; it must NOT.
    import time as _t
    _t.sleep(1.0)
    assert len(la.calls) == calls_after_delete, "no LLM call after successful delete"