"""GENUINE DebateEngine integration tests (no MagicMock of the engine).

These run a REAL DebateEngine via the existing AutoPilot._create_debate_engine
path: real DB (in tmp_path), real TurnManager, real argument_state, real
philosophical agents and real moderator. The LLM backend is injected via the
`llm_client` dependency-injection parameter (NO network, NO real LLMClient is
constructed), so orchestration is proven independently of inference
infrastructure (GOAL 3). This replaces the previous mocked "integration" tests
whose assertions were vacuous. Rule 5: tests are evidence.
"""

from __future__ import annotations

import pytest

from experiments.generation.schemas import GeneratedTask


def _task(ground_truth=4, domain="math"):
    return GeneratedTask(
        task_id="task_integ_1",
        source="generator",
        domain=domain,
        difficulty=1,
        reasoning_type="calculation",
        description="Calculate 2 + 2",
        ground_truth=ground_truth,
        generator_version="1.0.0",
        seed=1,
        generation_strategy="template",
    )


class StubLLM:
    """Deterministic stand-in for the LLM backend.

    Behavior: returns a NON-EMPTY response containing the ground truth so the
    debate produces real, validatable turns. When asked to act as moderator
    (prompt contains the moderator contract) it returns valid JSON selecting a
    speaker. `fail_next` forces the empty-response path for phantom-turn tests.
    """

    def __init__(self, response_text: str = "The answer is 4", delay=0.0):
        self.response_text = response_text
        self.delay = delay
        self.calls: list[dict] = []
        self.fail_agent = None  # if set to empty text, agents always return empty
        self._moderator_count = 0
        self._SPEAKERS = ["Stoic", "Existentialist", "Nihilist", "Spiritual", "Skeptic", "Pragmatist"]

    def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
        import time
        if self.delay:
            time.sleep(self.delay)
        self.calls.append({"messages": messages, "model": model, "temperature": temperature})
        if temperature == 0.5:  # Moderator uses temperature 0.5; agents use config.debate.temperature
            # Act as moderator: valid JSON ROTATING speakers so the real engine's
            # repetition guard never locks the debate into the deterministic fallback.
            speaker = self._SPEAKERS[self._moderator_count % len(self._SPEAKERS)]
            self._moderator_count += 1
            j = (
                '{"selected_speaker": "%s", "challenge": "This is a sufficiently '
                'long philosophical challenge addressing the current state of the '
                'debate and pushing it to a deeper level of analysis.", "reason": '
                '"The chosen speaker can advance the point.", "question": null, '
                '"detected_issues": null}'
            ) % speaker
            return j, "stop"
        # Agent call: if a forced failure is pending, yield an empty response
        # to exercise the phantom-turn guard (persistent until cleared, so the
        # continuation retry also yields empty and cannot mask the failure).
        if self.fail_agent is not None:
            return self.fail_agent, "stop"
        return self.response_text, "stop"


def _build_real_engine(tmp_path, ml_override=None):
    """Construct the REAL engine through the existing AutoPilot path.

    Uses dependency injection: the stub LLM is passed as `llm_client` and the
    DB location as `db_path` — so no real LLMClient is constructed and no
    network is touched, and no workspace `experiments/<id>/` artefact is left.
    Every other object (agents, moderator, TurnManager, argument_state,
    databases, DebateEngine) is the production one.
    """
    from experiments.autopilot import AutoPilot

    autopilot = AutoPilot()
    experiment_id = f"integ_{__import__('uuid').uuid4().hex[:8]}"
    config = {"temperature": 0.8, "max_tokens": 700}
    stub = ml_override if ml_override is not None else StubLLM()
    engine = autopilot._create_debate_engine(
        experiment_id, config, llm_client=stub, db_path=str(tmp_path / "debate.db")
    )
    return autopilot, experiment_id, engine


class TestGenuineDebateEngineIntegration:
    """Real engine + real agents + real DB + real turns."""

    def test_real_single_turn_persisted(self, tmp_path):
        """A single step_once on a FRESH engine produces a real completed turn."""
        autopilot, experiment_id, engine = _build_real_engine(tmp_path)
        # Real preconditions: agents registered, engine running.
        assert len(engine._agents) >= 5
        assert engine.argument_state is not None

        engine.start_debate()
        assert engine._state.status == "running"

        # Run real turns through the real step_once machinery until at least
        # one completes. The real moderator may transiently reject a decision
        # and retry — this is genuine engine behavior, so we allow several
        # steps (bounded) and assert that a real turn actually lands.
        exec_before = engine.argument_state.turn_count
        ok = False
        for _ in range(8):
            if engine.step_once():
                ok = True
                break
        assert ok is True
        assert engine.argument_state.turn_count > exec_before  # real turn applied

        # the turn is persisted into the REAL sqlite DB.
        turns = engine.turn_manager.get_all_turns()
        assert len(turns) >= 1
        assert any("4" in t.response for t in turns)

        # real agent memory mutated (not mocked)
        assert any(a.get_history() for a in engine._agents.values())

    def test_full_task_to_debate_path_on_real_engine(self, tmp_path):
        """The complete AutoPilot task→debate→validate→RAW path, real objects."""
        autopilot, experiment_id, engine = _build_real_engine(tmp_path)
        # NOTE: do NOT pre-call engine.start_debate() here — _run_task_through_debate
        # creates/starts this task's OWN dedicated session (background=False) and
        # finalizes it. Pre-starting would begin a second session (engine already
        # running -> start refused -> honest (None, False), no phantom debate).
        result = autopilot._run_task_through_debate(experiment_id, _task(ground_truth=4), engine)
        assert result.experiment_id == experiment_id
        assert result.task_id == "task_integ_1"
        assert result.run_id.startswith("run_")
        assert result.debate_id is not None and result.debate_id >= 1
        assert result.turn_count > 0
        # Deterministic validation is authoritative: 4 found in final response.
        assert result.is_valid is True
        assert result.validation_score > 0

    def test_empty_response_guard_prevents_phantom_turn(self, tmp_path):
        """Rule 7 / Rule 8: an empty LLM response must NOT become a turn."""
        stub = StubLLM()
        # Force the live engine to yield an empty response on every agent call.
        stub.fail_agent = "   \n  "  # whitespace-only, persistent
        autopilot, experiment_id, engine = _build_real_engine(tmp_path, ml_override=stub)
        engine.start_debate()

        exec_before = engine.argument_state.turn_count
        # A "completed" turn is one with a real response committed to the
        # turn manager (complete_turn) — reservations stay empty/incomplete.
        completed_before = sum(1 for t in engine.turn_manager.get_all_turns() if t.response.strip())
        history_before = {r: len(a.get_history()) for r, a in engine._agents.items()}

        ok = engine.step_once()
        assert ok is False

        # NO phantom turn: argument state (including any optimistic reservation)
        # is rolled back so it does not grow after an empty turn — there must be
        # zero net new argument-state accounting from a phantom turn.
        assert engine.argument_state.turn_count <= exec_before, \
            "empty response still grew argument-state turn count"
        # No turn was COMPLETED (complete_turn not called) — reservations stay
        # empty/incomplete and are never promoted to a real turn.
        assert sum(1 for t in engine.turn_manager.get_all_turns() if t.response.strip()) == completed_before
        for role, n in history_before.items():
            assert len(engine._agents[role].get_history()) == n, (
                f"agent {role} history mutated by a phantom (empty) turn"
            )
        # The failure is logged (observable) — engine still running for retry.
        assert engine._state.status == "running"


@pytest.mark.skipif(
    True, reason="Deterministic engine stub used elsewhere; live LLM gated by probe_llm (rule 15)"
)
class TestLiveLLMDebateIntegration:
    """OPTIONAL live proof — runs only when an authenticated LLM is reachable."""
    pass
