"""Comprehensive tests for Contradiction Engine v2, Evidence Provenance Graph, and Deterministic Replay."""

import pytest
from core.debate.engine import (
    ContradictionDetector,
    ProvenanceGraph,
    ReplayEngine,
    DebateEngine,
    DebateSessionConfig,
    ClaimStatus,
    ArbiterDecision,
    EvidenceRecord,
    Claim,
)


# ── 1. Contradiction Engine v2 ───────────────────────────────────────────────


class TestContradictionDetectorNegation:
    """Test negation pattern detection."""

    def test_direct_negation_meaning(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Life has inherent meaning",
            "Life has no inherent meaning",
        )
        assert result is not None
        assert result["type"] == "negation"
        assert "inherent meaning" in result["pattern"]

    def test_direct_negation_true_false(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "The hypothesis is true",
            "The hypothesis is false",
        )
        assert result is not None
        assert result["type"] == "negation"

    def test_direct_negation_exists(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Consciousness exists",
            "Consciousness does not exist",
        )
        assert result is not None
        assert result["type"] == "negation"

    def test_direct_negation_is_not(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Free will is real",
            "Free will is not real",
        )
        assert result is not None
        assert result["type"] == "negation"


class TestContradictionDetectorSynonym:
    """Test synonym-based (paraphrased) contradiction detection."""

    def test_synonym_meaning_purpose(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Life has significance",
            "Life has no purpose",
        )
        assert result is not None
        assert result["type"] == "equivalent_proposition"
        assert "meaning" in result["pattern"]

    def test_synonym_existence_reality(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Moral values have reality",
            "Moral values have no being",
        )
        assert result is not None
        assert result["type"] == "equivalent_proposition"

    def test_synonym_consciousness_awareness(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "AI can have awareness",
            "AI cannot have sentience",
        )
        # This may return 'negation' due to 'cannot' pattern, which is acceptable
        assert result is not None
        assert result["type"] in ("equivalent_proposition", "negation")


class TestContradictionDetectorContextual:
    """Test contextual contradiction detection."""

    def test_contextual_purpose_random(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Life has a purpose",
            "Life is random",
        )
        assert result is not None
        assert result["type"] == "contextual"

    def test_contextual_designed_accidental(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "The universe was designed",
            "The universe is accidental",
        )
        assert result is not None
        assert result["type"] == "contextual"

    def test_contextual_determined_free(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "All events are determined",
            "Human action is free",
        )
        assert result is not None
        assert result["type"] == "contextual"


class TestContradictionDetectorNoContradiction:
    """Test cases where no contradiction should be detected."""

    def test_complementary_statements(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Life is good",
            "Happiness is valuable",
        )
        assert result is None

    def test_same_perspective(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "Meaning is important",
            "Purpose matters",
        )
        assert result is None

    def test_unrelated_topics(self):
        detector = ContradictionDetector()
        result = detector.detect_contradiction(
            "The sky is blue",
            "Gravity exists",
        )
        assert result is None


class TestContradictionDetectorBatch:
    """Test batch contradiction detection."""

    def test_batch_detects_all_pairs(self):
        detector = ContradictionDetector()
        claims = [
            Claim(claim_id="c1", agent_id="a", hypothesis="Life has meaning"),
            Claim(claim_id="c2", agent_id="b", hypothesis="Life has no meaning"),
            Claim(claim_id="c3", agent_id="a", hypothesis="Meaning is constructed"),
        ]
        results = detector.batch_detect(claims)
        assert len(results) >= 1
        assert any(r["claim_a_id"] == "c1" and r["claim_b_id"] == "c2" for r in results)


# ── 2. Evidence Provenance Graph ────────────────────────────────────────────


class TestProvenanceGraphBasic:
    """Test basic provenance graph operations."""

    def test_add_evidence_and_retrieve(self):
        graph = ProvenanceGraph()
        rec = EvidenceRecord(
            evidence_id="e1",
            claim_id="c1",
            evidence_type="independent",
            content="Test content",
            verified=True,
            source="experiment_1",
        )
        graph.add_evidence(rec)
        chain = graph.get_evidence_chain("e1")
        assert chain["evidence_id"] == "e1"
        assert chain["source"] == "experiment_1"
        assert chain["verified"] is True

    def test_add_claim_and_retrieve(self):
        graph = ProvenanceGraph()
        claim = Claim(claim_id="c1", agent_id="a", hypothesis="Test hypothesis")
        graph.add_claim(claim)
        support = graph.get_claim_support("c1")
        assert support["claim_id"] == "c1"
        assert support["hypothesis"] == "Test hypothesis"

    def test_get_graph_summary(self):
        graph = ProvenanceGraph()
        graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", verified=True, source="src1"))
        graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", verified=False, source="src2"))
        graph.add_claim(Claim("c1", "a", "hypothesis"))
        summary = graph.get_graph_summary()
        assert summary["total_evidence"] == 2
        assert summary["total_claims"] == 1
        assert summary["verified_evidence"] == 1


class TestProvenanceGraphRelationships:
    """Test relationship tracking in provenance graph."""

    def test_evidence_supports_claim(self):
        graph = ProvenanceGraph()
        rec = EvidenceRecord(
            evidence_id="e1",
            claim_id="c1",
            evidence_type="independent",
            content="Test",
            verified=True,
            supports_claims=["c1"],
        )
        graph.add_evidence(rec)
        chain = graph.get_evidence_chain("e1")
        assert "c1" in chain["supports_claims"]

    def test_evidence_depends_on_another(self):
        graph = ProvenanceGraph()
        graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", depends_on=[]))
        graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", depends_on=["e1"]))
        chain = graph.get_evidence_chain("e2")
        assert "e1" in chain["depends_on"]

    def test_related_evidence_detected(self):
        graph = ProvenanceGraph()
        graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content"))
        graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", depends_on=["e1"]))
        chain = graph.get_evidence_chain("e1")
        assert "e2" in chain["related_evidence"]

    def test_conclusions_tracked(self):
        graph = ProvenanceGraph()
        rec = EvidenceRecord(
            evidence_id="e1",
            claim_id="c1",
            evidence_type="independent",
            content="Test",
            conclusions=["conclusion_1", "conclusion_2"],
        )
        graph.add_evidence(rec)
        chain = graph.get_evidence_chain("e1")
        assert chain["conclusions"] == ["conclusion_1", "conclusion_2"]


class TestProvenanceGraphSummary:
    """Test provenance graph summary functionality."""

    def test_summary_by_source(self):
        graph = ProvenanceGraph()
        graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", source="experiment"))
        graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", source="experiment"))
        graph.add_evidence(EvidenceRecord("e3", "c2", "test", "content", source="literature"))
        summary = graph.get_graph_summary()
        assert summary["evidence_by_source"]["experiment"] == 2
        assert summary["evidence_by_source"]["literature"] == 1


# ── 3. Deterministic Replay ─────────────────────────────────────────────────


class TestReplayEngineBasic:
    """Test basic replay functionality."""

    def test_capture_and_replay(self):
        config = DebateSessionConfig(topic="Test topic", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.add_claim("c1", "agent_a", "Life has meaning", ["Arg1"], ["e1"], status=ClaimStatus.VERIFIED)
        engine.add_claim("c2", "agent_b", "Meaning is constructed", ["Arg2"], ["e2"], status=ClaimStatus.VERIFIED)
        engine.add_evidence("e1", "c1", "independent", "Proof 1", verified=True, verification_method="deduction")
        engine.add_evidence("e2", "c2", "independent", "Proof 2", verified=True, verification_method="observation")
        engine.stop()

        original_decision = engine.arbitrate()
        replay_result = engine.replay_session()

        assert replay_result["deterministic"] is True
        assert replay_result["original_decision"] == "multiple_verified_claims"
        assert replay_result["replayed_decision"] == "VERIFIED"

    def test_replay_preserves_contradictions(self):
        config = DebateSessionConfig(topic="Test topic", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.add_claim("c1", "agent_a", "Life has meaning", [], [])
        engine.add_claim("c2", "agent_b", "Life has no meaning", [], [])
        engine.stop()

        original_contra_count = len(engine.contradictions)
        # Run arbiter to populate applied_rules
        engine.arbitrate()
        replay_result = engine.replay_session()

        assert original_contra_count > 0
        # Replay should be deterministic in terms of rules applied
        assert replay_result["replayed_decision"] == "UNRESOLVED"

    def test_replay_with_no_claims(self):
        config = DebateSessionConfig(topic="Test topic", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.stop()

        replay_result = engine.replay_session()
        # Replay should produce UNRESOLVED since no claims
        assert replay_result["replayed_decision"] == "UNRESOLVED"


class TestReplayEngineEdgeCases:
    """Test edge cases for replay functionality."""

    def test_replay_with_stagnation(self):
        config = DebateSessionConfig(topic="Test topic", max_turns=20)
        engine = DebateEngine(config, {})
        engine.start()
        # Add turns with new evidence to avoid stagnation
        for i in range(3):
            engine.step("agent_a", f"Argument {i}", new_evidence_count=1)
        # Now add turns without new evidence to trigger stagnation
        for i in range(3):
            if engine.status.value == "running":
                engine.step("agent_a", "Same argument", new_evidence_count=0)

        # Replay should preserve the decision
        replay_result = engine.replay_session()
        assert replay_result["replayed_decision"] in ("UNRESOLVED", "PARTIAL")

    def test_replay_with_invalid_evidence(self):
        config = DebateSessionConfig(topic="Test topic", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.add_claim("c1", "agent_a", "Claim A", [], ["bad_evidence"], status=ClaimStatus.INVALID)
        engine.add_claim("c2", "agent_b", "Claim B", [], ["also_bad"], status=ClaimStatus.INVALID)
        engine.stop()

        original_decision = engine.arbitrate()
        replay_result = engine.replay_session()

        assert replay_result["deterministic"] is True
        assert replay_result["replayed_decision"] == "INVALID"


class TestReplayEngineHistory:
    """Test replay history tracking."""

    def test_replay_history_accumulates(self):
        replay = ReplayEngine()

        config1 = DebateSessionConfig(topic="Topic 1", max_turns=5)
        engine1 = DebateEngine(config1, {})
        engine1.start()
        engine1.add_claim("c1", "agent_a", "H1", [], [], status=ClaimStatus.VERIFIED)
        engine1.stop()
        engine1.arbitrate()

        config2 = DebateSessionConfig(topic="Topic 2", max_turns=5)
        engine2 = DebateEngine(config2, {})
        engine2.start()
        engine2.add_claim("c1", "agent_a", "H2", [], [], status=ClaimStatus.PARTIAL)
        engine2.stop()
        engine2.arbitrate()

        replay.capture_session(engine1)
        replay.replay_session(replay.capture_session(engine1))
        replay.capture_session(engine2)
        replay.replay_session(replay.capture_session(engine2))

        assert len(replay.replay_history) == 2


# ── Integration Tests ────────────────────────────────────────────────────────


class TestIntegrationContradictionProvenanceReplay:
    """Test integration of all three enhancements."""

    def test_full_pipeline(self):
        # Create engine with enhanced features
        config = DebateSessionConfig(topic="Does life have inherent meaning?", max_turns=10)
        engine = DebateEngine(config, {})
        engine.start()

        # Add claims that will trigger contradiction detection
        engine.add_claim(
            "c1", "agent_a",
            "Life has inherent meaning through existential commitment",
            ["Existential commitment provides framework"],
            ["e1"],
            status=ClaimStatus.VERIFIED,
        )
        engine.add_claim(
            "c2", "agent_b",
            "Life has no inherent meaning and is socially constructed",
            ["Cross-cultural variation"],
            ["e2"],
            status=ClaimStatus.VERIFIED,
        )

        # Add evidence with provenance
        engine.add_evidence(
            "e1", "c1", "independent",
            "Logical proof of meaning through commitment",
            verified=True,
            verification_method="deduction",
            source="philosophy_paper_1",
            supports_claims=["c1"],
            conclusions=["meaning_exists"],
        )
        engine.add_evidence(
            "e2", "c2", "independent",
            "Empirical observation of cultural variation",
            verified=True,
            verification_method="observation",
            source="anthropology_study_1",
            supports_claims=["c2"],
            depends_on=["e1"],
        )

        engine.stop()

        # Verify contradiction detected
        assert len(engine.contradictions) > 0

        # Verify provenance graph populated
        graph = engine.provenance_graph
        summary = graph.get_graph_summary()
        assert summary["total_evidence"] == 2
        assert summary["verified_evidence"] == 2

        # Verify evidence chain
        chain = graph.get_evidence_chain("e1")
        assert chain["source"] == "philosophy_paper_1"
        assert "e2" in chain["related_evidence"]

        # Run arbiter and replay
        original_decision = engine.arbitrate()
        replay_result = engine.replay_session()

        assert replay_result["replayed_decision"] == "VERIFIED"

    def test_report_includes_all_enhancements(self):
        config = DebateSessionConfig(topic="Test", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.add_claim("c1", "agent_a", "H1", [], [], status=ClaimStatus.VERIFIED)
        engine.add_evidence("e1", "c1", "independent", "Test", verified=True, source="src1")
        engine.stop()

        report = engine.export_report()

        # Check provenance fields are present in evidence
        assert len(report["evidence_registry"]) > 0
        evidence = report["evidence_registry"][0]
        assert "source" in evidence
        assert "supports_claims" in evidence
        assert "depends_on" in evidence
        assert "conclusions" in evidence

        # Check contradictions and rule version
        assert "contradictions" in report
        assert "arbiter_rule_version" in report
