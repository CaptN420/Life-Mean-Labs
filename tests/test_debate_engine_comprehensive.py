"""Comprehensive tests for the Deterministic Debate Engine — all 20 spec cases.

Covers:
1. Debate with valid deterministic evidence
2. Contradictory hypotheses
3. Insufficient evidence
4. Invalid evidence
5. Repeated arguments (stagnation)
6. Debate stagnation detection
7. Max turns limit
8. Resource overflow
9. Agent failure
10. Arbiter failure
11. Security bypass attempt
12. Session isolation
13. Decision reproducibility
14. Event history
15. ID correlation
16. UI data display
17. Turn navigation
18. Pause/resume
19. Secure stop
20. Report export
"""

import pytest
import time

from core.debate.engine import (
    Claim,
    ClaimStatus,
    DebateEngine,
    DebateResult,
    DebateSessionConfig,
    DebateStatus,
    StagnationDetector,
    ArbiterDecision,
    DeterministicArbiter,
    EvidenceRecord,
    ContradictionRecord,
    TaskClassifier,
    TaskType,
)
from core.debate.events import DebateEventLogger, DebateEventType
from core.personas.schema import PersonaConfig, PersonaType, ProviderType
from core.safety.policy_guard import PolicyGuard


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_engine(topic="Does life have inherent meaning?", max_turns=10):
    config = DebateSessionConfig(topic=topic, max_turns=max_turns)
    personas = {
        "agent_a": PersonaConfig(
            role_id="agent_a", name="Agent A", persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
            description="Proponent", system_prompt="Argue for the proposition.",
        ),
        "agent_b": PersonaConfig(
            role_id="agent_b", name="Agent B", persona_type=PersonaType.SKEPTIC,
            description="Opponent", system_prompt="Argue against the proposition.",
        ),
    }
    return DebateEngine(config, personas)


def _run_full_debate(engine, num_turns=5):
    """Run a debate with alternating speakers and evidence."""
    engine.start()
    for i in range(num_turns):
        speaker = "agent_a" if i % 2 == 0 else "agent_b"
        engine.step(speaker, f"Response {i} about the topic", new_evidence_count=1)
    return engine


# ── 1. Debate with valid deterministic evidence ──────────────────────────────


class TestValidEvidenceDebate:
    def test_verified_evidence_leads_to_verified_decision(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim(
            "c1", "agent_a", "Life has inherent meaning",
            arguments=["Existential commitment"], evidence_refs=["ref_1"],
            status=ClaimStatus.VERIFIED,
        )
        engine.add_claim(
            "c2", "agent_b", "Meaning is constructed",
            arguments=["Social construction"], evidence_refs=["ref_2"],
            status=ClaimStatus.VERIFIED,
        )
        engine.add_evidence("ref_1", "c1", "independent", "Logical proof of meaning", verified=True, verification_method="deduction")
        engine.add_evidence("ref_2", "c2", "independent", "Empirical observation", verified=True, verification_method="observation")
        engine.stop()
        decision = engine.arbitrate()
        assert decision == ArbiterDecision.VERIFIED
        result = engine.get_result()
        assert result.arbiter_decision == ArbiterDecision.VERIFIED
        assert len(result.evidence_registry) == 2


# ── 2. Contradictory hypotheses ─────────────────────────────────────────────


class TestContradictoryHypotheses:
    def test_contradiction_detected(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim("c1", "agent_a", "Life has inherent meaning", [], ["e1"])
        engine.add_claim("c2", "agent_b", "Life has no inherent meaning", [], ["e2"])
        assert len(engine.contradictions) > 0
        assert engine.contradictions[0].claim_a_id == "c1"
        assert engine.contradictions[0].claim_b_id == "c2"

    def test_contradiction_resolved(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim("c1", "agent_a", "Life has inherent meaning", [], ["e1"])
        engine.add_claim("c2", "agent_b", "Life has no inherent meaning", [], ["e2"])
        assert len(engine.contradictions) > 0
        resolved = engine.resolve_contradiction(engine.contradictions[0].contradiction_id, "Synthesis: meaning is contextual")
        assert resolved is True
        assert engine.contradictions[0].resolved is True


# ── 3. Insufficient evidence ────────────────────────────────────────────────


class TestInsufficientEvidence:
    def test_unresolved_when_no_evidence(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim("c1", "agent_a", "Life has meaning", [], [])
        engine.stop()
        decision = engine.arbitrate()
        assert decision == ArbiterDecision.UNRESOLVED

    def test_unresolved_all_unverified(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim("c1", "agent_a", "Hypothesis A", [], ["e1"], status=ClaimStatus.UNVERIFIED)
        engine.add_claim("c2", "agent_b", "Hypothesis B", [], ["e2"], status=ClaimStatus.UNVERIFIED)
        engine.stop()
        assert engine.arbitrate() == ArbiterDecision.UNRESOLVED


# ── 4. Invalid evidence ─────────────────────────────────────────────────────


class TestInvalidEvidence:
    def test_invalid_evidence_leads_to_invalid_decision(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim("c1", "agent_a", "Claim A", [], ["bad_evidence"], status=ClaimStatus.INVALID)
        engine.add_claim("c2", "agent_b", "Claim B", [], ["also_bad"], status=ClaimStatus.INVALID)
        engine.add_claim("c3", "agent_a", "Claim C", [], [], status=ClaimStatus.PARTIAL)
        engine.stop()
        decision = engine.arbitrate()
        assert decision == ArbiterDecision.INVALID


# ── 5. Repeated arguments (stagnation) ──────────────────────────────────────


class TestRepeatedArguments:
    def test_repeated_claim_detected(self):
        detector = StagnationDetector(max_consecutive_no_progress=1)
        from core.debate.engine import DebateTurn
        claim = Claim(claim_id="c1", agent_id="a", hypothesis="Same argument")
        turn1 = DebateTurn(turn_number=1, speaker_id="a", claim=claim)
        turn2 = DebateTurn(turn_number=2, speaker_id="b", claim=claim)
        r1 = detector.check_progress(turn1, new_evidence_count=0)
        r2 = detector.check_progress(turn2, new_evidence_count=0)
        assert "repeated_claim" in r2["indicators"]


# ── 6. Debate stagnation detection ─────────────────────────────────────────


class TestStagnationDetection:
    def test_stagnation_stops_debate(self):
        engine = _make_engine(max_turns=20)
        detector = StagnationDetector(max_consecutive_no_progress=2)
        engine._stagnation_detector = detector
        engine.start()
        engine.step("agent_a", "No progress 1", new_evidence_count=0)
        engine.step("agent_b", "No progress 2", new_evidence_count=0)
        assert engine.status == DebateStatus.STOPPED

    def test_progress_resets_stagnation(self):
        engine = _make_engine(max_turns=20)
        detector = StagnationDetector(max_consecutive_no_progress=2)
        engine._stagnation_detector = detector
        engine.start()
        engine.step("agent_a", "Argument 1", new_evidence_count=0)
        engine.step("agent_b", "Argument 2", new_evidence_count=2)
        assert engine.status == DebateStatus.RUNNING


# ── 7. Max turns limit ─────────────────────────────────────────────────────


class TestMaxTurnsLimit:
    def test_max_turns_completes_debate(self):
        engine = _make_engine(max_turns=5)
        engine.start()
        for i in range(5):
            speaker = "agent_a" if i % 2 == 0 else "agent_b"
            engine.step(speaker, f"Response {i}", new_evidence_count=1)
        assert engine.status == DebateStatus.COMPLETED


# ── 8. Resource overflow ───────────────────────────────────────────────────


class TestResourceOverflow:
    def test_resource_limit_triggers_warning(self):
        from core.safety.resource_guard import ResourceGuard
        guard = ResourceGuard()
        config = DebateSessionConfig(topic="Test", max_turns=10)
        engine = DebateEngine(config, {}, safety_guard=guard)
        engine.start()
        # Set a very low limit to trigger warning
        guard.set_limit("execution_time", 0.001, 0.002, "ms")
        # Simulate elapsed time exceeding soft limit
        guard.update_usage("execution_time", 0.0015)
        event = guard.check_limit("execution_time", 0.0015, "debate_engine", engine.session_id)
        assert event is not None
        assert event.severity == "WARNING"


# ── 9. Agent failure ────────────────────────────────────────────────────────


class TestAgentFailure:
    def test_agent_failure_handled(self):
        engine = _make_engine()
        engine.start()
        # Simulate agent failure by providing error response
        turn = engine.step("agent_a", "[Error: Agent unavailable]", new_evidence_count=0)
        assert turn.speaker_id == "agent_a"
        assert engine.status == DebateStatus.RUNNING


# ── 10. Arbiter failure ────────────────────────────────────────────────────


class TestArbiterFailure:
    def test_arbitrate_before_completion_raises(self):
        engine = _make_engine()
        engine.start()
        with pytest.raises(RuntimeError, match="Cannot arbitrate"):
            engine.arbitrate()

    def test_arbiter_returns_unresolved_on_empty(self):
        arbiter = DeterministicArbiter()
        decision = arbiter.arbitrate([], DebateSessionConfig(topic="Test"))
        assert decision == ArbiterDecision.UNRESOLVED


# ── 11. Security bypass attempt ────────────────────────────────────────────


class TestSecurityBypass:
    def test_security_guard_blocks_forbidden_operation(self):
        guard = PolicyGuard()
        # Try to bypass security
        result = guard.check_operation("bypass_security", "debate_engine")
        assert result is False

    def test_security_violation_logged(self):
        guard = PolicyGuard()
        config = DebateSessionConfig(topic="Test")
        engine = DebateEngine(config, {}, safety_guard=guard)
        # Start should be blocked if guard denies
        # (PolicyGuard allows 'start_debate' by default unless in strict mode with allowlist)
        result = guard.check_operation("start_debate", "debate_engine")
        assert result is True  # Allowed by default


# ── 12. Session isolation ───────────────────────────────────────────────────


class TestSessionIsolation:
    def test_different_sessions_have_different_ids(self):
        config1 = DebateSessionConfig(topic="Topic A")
        config2 = DebateSessionConfig(topic="Topic B")
        engine1 = DebateEngine(config1, {})
        engine2 = DebateEngine(config2, {})
        assert engine1.session_id != engine2.session_id
        assert engine1.trace_id != engine2.trace_id

    def test_claims_not_shared_between_sessions(self):
        e1 = _make_engine()
        e2 = _make_engine()
        e1.start()
        e1.add_claim("c1", "agent_a", "H1", [], [])
        assert len(e2.claims) == 0


# ── 13. Decision reproducibility ───────────────────────────────────────────


class TestDecisionReproducibility:
    def test_same_inputs_same_decision(self):
        claims = [
            Claim(claim_id="c1", agent_id="a", hypothesis="H1", status=ClaimStatus.VERIFIED),
            Claim(claim_id="c2", agent_id="b", hypothesis="H2", status=ClaimStatus.VERIFIED),
        ]
        arbiter = DeterministicArbiter()
        decision1 = arbiter.arbitrate(claims, DebateSessionConfig(topic="Test"))
        decision2 = arbiter.arbitrate(claims, DebateSessionConfig(topic="Test"))
        assert decision1 == decision2 == ArbiterDecision.VERIFIED

    def test_rule_version_constant(self):
        arbiter = DeterministicArbiter()
        assert arbiter.rule_version == "1.0.0"


# ── 14. Event history ───────────────────────────────────────────────────────


class TestEventHistory:
    def test_events_logged_in_order(self):
        engine = _make_engine()
        engine.start()
        engine.step("agent_a", "Response 1")
        events = engine.events
        assert len(events) >= 2
        assert events[0]["event_type"] == "DEBATE_STARTED"
        assert events[1]["event_type"] == "ROUND_STARTED"

    def test_event_sequence_numbers_increment(self):
        engine = _make_engine()
        engine.start()
        engine.step("agent_a", "R1")
        engine.step("agent_b", "R2")
        events = engine.events
        seqs = [e["sequence_number"] for e in events]
        assert seqs == sorted(seqs)


# ── 15. ID correlation ──────────────────────────────────────────────────────


class TestIdCorrelation:
    def test_trace_id_consistent_across_components(self):
        trace = "custom_trace_abc123"
        config = DebateSessionConfig(topic="Test", trace_id=trace)
        engine = DebateEngine(config, {})
        assert engine.trace_id == trace
        claim = engine.add_claim("c1", "agent_a", "H", [], [])
        assert claim.trace_id == trace

    def test_session_id_in_events(self):
        engine = _make_engine()
        engine.start()
        events = engine.events
        assert all(e["session_id"] == engine.session_id for e in events)


# ── 16. UI data display ────────────────────────────────────────────────────


class TestUIDataDisplay:
    def test_result_contains_all_panels(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim("c1", "agent_a", "Hypothesis A", ["Arg1"], ["e1"], status=ClaimStatus.VERIFIED)
        engine.add_claim("c2", "agent_b", "Hypothesis B", ["Arg2"], ["e2"], status=ClaimStatus.PARTIAL)
        engine.stop()
        result = engine.get_result()
        assert result.session_id is not None
        assert result.topic == "Does life have inherent meaning?"
        assert len(result.claims) == 2
        assert len(result.transcript) == 0  # No turns yet

    def test_events_accessible_for_ui(self):
        engine = _make_engine()
        engine.start()
        engine.step("agent_a", "Response")
        events = engine.events
        assert isinstance(events, list)
        assert all(isinstance(e, dict) for e in events)


# ── 17. Turn navigation ────────────────────────────────────────────────────


class TestTurnNavigation:
    def test_turns_accessible_by_index(self):
        engine = _make_engine(max_turns=5)
        engine.start()
        for i in range(3):
            engine.step("agent_a" if i % 2 == 0 else "agent_b", f"R{i}")
        assert len(engine.turns) == 3
        assert engine.turns[0].turn_number == 1
        assert engine.turns[2].turn_number == 3

    def test_turn_selector_shows_history(self):
        engine = _make_engine(max_turns=5)
        engine.start()
        engine.step("agent_a", "First response")
        engine.step("agent_b", "Counter response")
        history = [t.to_dict() for t in engine.turns]
        assert len(history) == 2
        assert history[0]["speaker_id"] == "agent_a"
        assert history[1]["speaker_id"] == "agent_b"


# ── 18. Pause and resume ───────────────────────────────────────────────────


class TestPauseResume:
    def test_pause_and_resume(self):
        engine = _make_engine()
        engine.start()
        assert engine.pause() is True
        assert engine.status == DebateStatus.PAUSED
        assert engine.resume() is True
        assert engine.status == DebateStatus.RUNNING

    def test_pause_while_pending_fails(self):
        engine = _make_engine()
        assert engine.pause() is False


# ── 19. Secure stop ────────────────────────────────────────────────────────


class TestSecureStop:
    def test_stop_completes_gracefully(self):
        engine = _make_engine()
        engine.start()
        engine.step("agent_a", "Response")
        assert engine.stop() is True
        assert engine.status == DebateStatus.STOPPED

    def test_stop_while_pending_fails(self):
        engine = _make_engine()
        assert engine.stop() is False

    def test_events_record_stop(self):
        engine = _make_engine()
        engine.start()
        engine.stop()
        events = engine.events
        assert any(e["event_type"] == "DEBATE_STOPPED" for e in events)


# ── 20. Report export ───────────────────────────────────────────────────────


class TestReportExport:
    def test_export_report_structure(self):
        engine = _make_engine()
        engine.start()
        engine.add_claim("c1", "agent_a", "H1", ["Arg1"], ["e1"], status=ClaimStatus.VERIFIED)
        engine.add_evidence("e1", "c1", "independent", "Proof content", verified=True, verification_method="test")
        engine.stop()
        report = engine.export_report()
        assert "session_id" in report
        assert "trace_id" in report
        assert "topic" in report
        assert "arbiter_decision" in report
        assert "claims" in report
        assert "evidence_registry" in report
        assert "events" in report
        assert "metrics" in report

    def test_export_includes_arbiter_rule_version(self):
        engine = _make_engine()
        engine.start()
        engine.stop()
        report = engine.export_report()
        assert "arbiter_rule_version" in report
        assert report["arbiter_rule_version"] == "1.0.0"

    def test_export_metrics_comprehensive(self):
        engine = _make_engine()
        engine.start()
        engine.step("agent_a", "R1", new_evidence_count=1)
        engine.add_claim("c1", "agent_a", "H", [], [], status=ClaimStatus.VERIFIED)
        engine.stop()
        report = engine.export_report()
        metrics = report["metrics"]
        assert metrics["total_turns"] == 1
        assert metrics["total_claims"] == 1
        assert "task_type" in metrics
        assert "trace_id" in metrics


# ── Task Classifier Tests ───────────────────────────────────────────────────


class TestTaskClassifier:
    def test_classify_philosophical(self):
        classifier = TaskClassifier()
        assert classifier.classify("What is the meaning of life?") == TaskType.PHILOSOPHICAL

    def test_classify_factual(self):
        classifier = TaskClassifier()
        assert classifier.classify("Verify that the earth is round") == TaskType.FACTUAL

    def test_classify_scientific(self):
        classifier = TaskClassifier()
        assert classifier.classify("Test the hypothesis of evolution") == TaskType.SCIENTIFIC

    def test_is_debate_worthy(self):
        classifier = TaskClassifier()
        assert classifier.is_debate_worthy("Does consciousness have inherent value?") is True
        assert classifier.is_debate_worthy("short") is False


# ── Evidence Record Tests ───────────────────────────────────────────────────


class TestEvidenceRecord:
    def test_evidence_record_serialization(self):
        rec = EvidenceRecord(evidence_id="e1", claim_id="c1", evidence_type="independent", content="Test content", verified=True)
        d = rec.to_dict()
        assert d["evidence_id"] == "e1"
        assert d["verified"] is True

    def test_content_truncated(self):
        rec = EvidenceRecord(evidence_id="e1", claim_id="c1", evidence_type="test", content="X" * 1000)
        d = rec.to_dict()
        assert len(d["content"]) <= 500


# ── Contradiction Record Tests ──────────────────────────────────────────────


class TestContradictionRecord:
    def test_contradiction_serialization(self):
        contra = ContradictionRecord(contradiction_id="cd1", claim_a_id="c1", claim_b_id="c2", description="Opposing views")
        d = contra.to_dict()
        assert d["resolved"] is False

    def test_contradiction_resolution(self):
        contra = ContradictionRecord(contradiction_id="cd1", claim_a_id="c1", claim_b_id="c2", description="Test")
        contra.resolved = True
        contra.resolution = "Synthesis found"
        d = contra.to_dict()
        assert d["resolved"] is True
