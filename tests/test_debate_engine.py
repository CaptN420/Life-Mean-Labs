"""Tests for the deterministic debate engine."""

import pytest

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
)
from core.personas.schema import PersonaType, ProviderType


class TestClaim:
    """Tests for Claim dataclass."""

    def test_create_claim(self):
        claim = Claim(
            claim_id="c1",
            agent_id="agent_a",
            hypothesis="Life has meaning",
            arguments=["Argument 1", "Argument 2"],
            evidence_refs=["evidence_1"],
        )
        assert claim.status == ClaimStatus.UNVERIFIED
        assert claim.trace_id == ""

    def test_to_dict(self):
        claim = Claim(
            claim_id="c1",
            agent_id="agent_a",
            hypothesis="Test",
            status=ClaimStatus.VERIFIED,
            trace_id="trace_123",
        )
        data = claim.to_dict()
        assert data["claim_id"] == "c1"
        assert data["status"] == "VERIFIED"
        assert data["trace_id"] == "trace_123"


class TestStagnationDetector:
    """Tests for StagnationDetector."""

    def test_no_stagnation_initial(self):
        detector = StagnationDetector()
        from core.debate.engine import DebateTurn
        turn = DebateTurn(turn_number=1, speaker_id="agent_a")
        result = detector.check_progress(turn, new_evidence_count=2)
        assert result["is_stagnant"] is False

    def test_detect_stagnation(self):
        detector = StagnationDetector(max_consecutive_no_progress=2)
        from core.debate.engine import DebateTurn

        # First turn: no progress
        turn1 = DebateTurn(turn_number=1, speaker_id="agent_a")
        result1 = detector.check_progress(turn1, new_evidence_count=0)
        assert result1["is_stagnant"] is False

        # Second turn: still no progress -> stagnant
        turn2 = DebateTurn(turn_number=2, speaker_id="agent_b")
        result2 = detector.check_progress(turn2, new_evidence_count=0)
        assert result2["is_stagnant"] is True

    def test_reset(self):
        detector = StagnationDetector(max_consecutive_no_progress=1)
        from core.debate.engine import DebateTurn

        turn = DebateTurn(turn_number=1, speaker_id="agent_a")
        detector.check_progress(turn, new_evidence_count=0)
        assert detector._consecutive_no_progress == 1

        detector.reset()
        assert detector._consecutive_no_progress == 0


class TestDeterministicArbiter:
    """Tests for DeterministicArbiter."""

    def test_verified_decision(self):
        arbiter = DeterministicArbiter()
        claims = [
            Claim(claim_id="c1", agent_id="a", hypothesis="H1", status=ClaimStatus.VERIFIED),
            Claim(claim_id="c2", agent_id="b", hypothesis="H2", status=ClaimStatus.VERIFIED),
        ]
        decision = arbiter.arbitrate(claims, DebateSessionConfig(topic="Test"))
        assert decision == ArbiterDecision.VERIFIED

    def test_invalid_decision(self):
        arbiter = DeterministicArbiter()
        claims = [
            Claim(claim_id="c1", agent_id="a", hypothesis="H1", status=ClaimStatus.INVALID),
            Claim(claim_id="c2", agent_id="b", hypothesis="H2", status=ClaimStatus.INVALID),
            Claim(claim_id="c3", agent_id="c", hypothesis="H3", status=ClaimStatus.PARTIAL),
        ]
        decision = arbiter.arbitrate(claims, DebateSessionConfig(topic="Test"))
        assert decision == ArbiterDecision.INVALID

    def test_partial_decision(self):
        arbiter = DeterministicArbiter()
        claims = [
            Claim(claim_id="c1", agent_id="a", hypothesis="H1", status=ClaimStatus.PARTIAL),
        ]
        decision = arbiter.arbitrate(claims, DebateSessionConfig(topic="Test"))
        assert decision == ArbiterDecision.PARTIAL

    def test_unresolved_no_claims(self):
        arbiter = DeterministicArbiter()
        decision = arbiter.arbitrate([], DebateSessionConfig(topic="Test"))
        assert decision == ArbiterDecision.UNRESOLVED

    def test_justification(self):
        arbiter = DeterministicArbiter()
        justification = arbiter.get_justification(ArbiterDecision.UNRESOLVED)
        assert "Insufficient evidence" in justification


class TestDebateEngine:
    """Tests for DebateEngine."""

    def setup_method(self):
        self.config = DebateSessionConfig(
            topic="What is the meaning of life?",
            personas=["existentialist", "stoic"],
            max_turns=10,
        )
        self.personas = {
            "existentialist": type('Persona', (), {'role_id': 'existentialist'})(),
            "stoic": type('Persona', (), {'role_id': 'stoic'})(),
        }
        self.engine = DebateEngine(self.config, self.personas)

    def test_start(self):
        assert self.engine.start() is True
        assert self.engine.status == DebateStatus.RUNNING

    def test_step(self):
        self.engine.start()
        turn = self.engine.step("existentialist", "I believe life has no inherent meaning.")
        assert turn.turn_number == 1
        assert turn.speaker_id == "existentialist"

    def test_max_turns_completion(self):
        self.engine.start()
        for i in range(10):
            speaker = "existentialist" if i % 2 == 0 else "stoic"
            self.engine.step(speaker, f"Response {i}", new_evidence_count=1)
        assert self.engine.status == DebateStatus.COMPLETED

    def test_stagnation_detection(self):
        detector = StagnationDetector(max_consecutive_no_progress=2)
        self.engine._stagnation_detector = detector

        self.engine.start()
        self.engine.step("existentialist", "No progress 1", new_evidence_count=0)
        self.engine.step("stoic", "No progress 2", new_evidence_count=0)
        assert self.engine.status == DebateStatus.STOPPED

    def test_add_claim(self):
        claim = self.engine.add_claim(
            claim_id="c1",
            agent_id="existentialist",
            hypothesis="Life has no inherent meaning",
            arguments=["Existence precedes essence"],
            evidence_refs=["evidence_1"],
        )
        assert len(self.engine.claims) == 1
        assert claim.hypothesis == "Life has no inherent meaning"

    def test_arbitrate_completed(self):
        self.engine.start()
        self.engine.add_claim(
            claim_id="c1",
            agent_id="existentialist",
            hypothesis="H1",
            arguments=["Arg1"],
            evidence_refs=["e1"],
            status=ClaimStatus.VERIFIED,
        )
        self.engine.add_claim(
            claim_id="c2",
            agent_id="stoic",
            hypothesis="H2",
            arguments=["Arg2"],
            evidence_refs=["e2"],
            status=ClaimStatus.VERIFIED,
        )
        self.engine.stop()
        decision = self.engine.arbitrate()
        assert decision == ArbiterDecision.VERIFIED

    def test_get_result(self):
        self.engine.start()
        self.engine.step("existentialist", "Response 1")
        self.engine.stop()
        result = self.engine.get_result()
        assert result.session_id.startswith("debate_")
        assert result.topic == "What is the meaning of life?"
        assert result.turns_committed == 1
        assert len(result.transcript) == 1

    def test_pause_resume(self):
        self.engine.start()
        assert self.engine.pause() is True
        assert self.engine.status == DebateStatus.PAUSED
        assert self.engine.resume() is True
        assert self.engine.status == DebateStatus.RUNNING

    def test_trace_id_consistency(self):
        config = DebateSessionConfig(topic="Test", trace_id="custom_trace_123")
        engine = DebateEngine(config, {})
        assert engine.trace_id == "custom_trace_123"
