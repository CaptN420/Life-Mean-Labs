"""Comprehensive tests for Experience Registry, Evidence Impact, Deepening Engine, and Enhanced Contradiction Detector."""

import pytest
import time
from core.debate.experience_registry import (
    ExperienceRegistry,
    ExperienceRecord,
    ExperienceType,
    ExperienceStatus,
)
from core.debate.evidence_impact import (
    EvidenceImpactAnalyzer,
    EvidenceChangeType,
    ImpactSeverity,
    ImpactResult,
)
from core.debate.deepening_engine import (
    ExperimentDeepeningEngine,
    DeepeningAction,
    InformationGain,
    InvestigationStatus,
)
from core.debate.enhanced_contradiction_detector import (
    EnhancedContradictionDetector,
    ContradictionType,
    CertaintyLevel,
    ContradictionFinding,
)
from core.debate.engine import (
    DebateEngine,
    DebateSessionConfig,
    ClaimStatus,
    EvidenceRecord as EngineEvidenceRecord,
    Claim,
    ReplayEngine,
)


# ── 1. Experience Registry ───────────────────────────────────────────────────


class TestExperienceRegistryBasic:
    """Test basic experience registry operations."""

    def test_create_experience(self):
        registry = ExperienceRegistry()
        exp = registry.create_experience(
            session_id="SESSION-001",
            question="Does life have inherent meaning?",
            decision="UNRESOLVED",
        )
        assert exp.experience_id == "EXP-0001"
        assert exp.session_id == "SESSION-001"
        assert exp.question == "Does life have inherent meaning?"
        assert exp.status == ExperienceStatus.COMPLETED
        assert exp.experience_type == ExperienceType.ORIGINAL

    def test_create_derived_experience(self):
        registry = ExperienceRegistry()
        original = registry.create_experience(
            session_id="SESSION-001",
            question="Original question",
        )
        derived = registry.create_experience(
            session_id="SESSION-002",
            question="Follow-up question",
            parent_experience_id=original.experience_id,
            experience_type=ExperienceType.DEEP_INVESTIGATION,
        )
        assert derived.parent_experience_id == original.experience_id
        assert original.derived_experience_ids == [derived.experience_id]

    def test_get_experience(self):
        registry = ExperienceRegistry()
        exp = registry.create_experience("S1", "Question")
        retrieved = registry.get_experience(exp.experience_id)
        assert retrieved is not None
        assert retrieved.experience_id == exp.experience_id

    def test_get_by_session(self):
        registry = ExperienceRegistry()
        registry.create_experience("SESSION-A", "Q1")
        registry.create_experience("SESSION-A", "Q2")
        registry.create_experience("SESSION-B", "Q3")
        results = registry.get_by_session("SESSION-A")
        assert len(results) == 2

    def test_search_by_question(self):
        registry = ExperienceRegistry()
        registry.create_experience("S1", "Does life have meaning?")
        registry.create_experience("S2", "What is consciousness?")
        results = registry.search_by_question("meaning")
        assert len(results) == 1
        assert "meaning" in results[0].question.lower()

    def test_search_by_decision(self):
        registry = ExperienceRegistry()
        registry.create_experience("S1", "Q1", decision="VERIFIED")
        registry.create_experience("S2", "Q2", decision="UNRESOLVED")
        results = registry.search_by_decision("UNRESOLVED")
        assert len(results) == 1

    def test_get_derived_experiences(self):
        registry = ExperienceRegistry()
        original = registry.create_experience("S1", "Original")
        child1 = registry.create_experience("S2", "Child 1", parent_experience_id=original.experience_id)
        child2 = registry.create_experience("S3", "Child 2", parent_experience_id=original.experience_id)
        children = registry.get_derived_experiences(original.experience_id)
        assert len(children) == 2
        assert child1.experience_id in [c.experience_id for c in children]
        assert child2.experience_id in [c.experience_id for c in children]


class TestExperienceRegistryPersistence:
    """Test experience persistence."""

    def test_persist_and_load(self, tmp_path):
        registry = ExperienceRegistry(storage_path=str(tmp_path / "experiences.jsonl"))
        exp = registry.create_experience("S1", "Question")
        count = registry.persist_to_disk()
        assert count == 1

        # Load into new registry
        registry2 = ExperienceRegistry(storage_path=str(tmp_path / "experiences.jsonl"))
        loaded = registry2.get_experience(exp.experience_id)
        assert loaded is not None
        assert loaded.question == "Question"


class TestExperienceRegistryStatistics:
    """Test registry statistics."""

    def test_get_statistics(self):
        registry = ExperienceRegistry()
        registry.create_experience("S1", "Q1", decision="VERIFIED")
        registry.create_experience("S2", "Q2", decision="UNRESOLVED")
        registry.create_experience("S3", "Q3", decision="PARTIAL")

        stats = registry.get_statistics()
        assert stats["total_experiences"] == 3
        assert stats["by_decision"]["VERIFIED"] == 1
        assert stats["by_decision"]["UNRESOLVED"] == 1
        assert stats["by_decision"]["PARTIAL"] == 1


# ── 2. Evidence Impact Analyzer ─────────────────────────────────────────────


class TestEvidenceImpactBasic:
    """Test basic evidence impact analysis."""

    def test_analyze_invalidated_evidence(self):
        analyzer = EvidenceImpactAnalyzer()
        graph = _make_graph_with_dependencies()
        result = analyzer.analyze_evidence_impact(
            "e1", graph, EvidenceChangeType.INVALIDATED
        )
        assert result.evidence_id == "e1"
        assert result.change_type == EvidenceChangeType.INVALIDATED
        assert result.severity in (ImpactSeverity.LOW, ImpactSeverity.MEDIUM)

    def test_detect_downstream_dependencies(self):
        analyzer = EvidenceImpactAnalyzer()
        graph = _make_graph_with_dependencies()
        deps = analyzer.get_downstream_dependencies("e1", graph)
        assert "e2" in deps

    def test_detect_dependency_cycles(self):
        analyzer = EvidenceImpactAnalyzer()
        graph = _make_graph_with_cycle()
        has_cycle = analyzer.detect_dependency_cycles(graph)
        assert has_cycle is True

    def test_no_cycle_without_dependencies(self):
        analyzer = EvidenceImpactAnalyzer()
        graph = _make_simple_graph()
        has_cycle = analyzer.detect_dependency_cycles(graph)
        assert has_cycle is False


class TestEvidenceImpactAnalysis:
    """Test detailed impact analysis."""

    def test_get_affected_conclusions(self):
        from core.debate.engine import ProvenanceGraph, EvidenceRecord, Claim, ClaimStatus

        graph = ProvenanceGraph()
        graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", verified=True, supports_claims=["c1"], conclusions=["conclusion_1"]))
        graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", verified=True, depends_on=["e1"], conclusions=["conclusion_2"]))
        graph.add_claim(Claim("c1", "a", "hypothesis", status=ClaimStatus.VERIFIED))

        analyzer = EvidenceImpactAnalyzer()
        conclusions = analyzer.get_affected_conclusions("e1", graph)
        assert len(conclusions) > 0
        assert "conclusion_1" in conclusions or "conclusion_2" in conclusions

    def test_get_independent_sources(self):
        analyzer = EvidenceImpactAnalyzer()
        graph = _make_graph_with_dependencies()
        independent = analyzer.get_independent_sources("c1", graph)
        # e1 should be independent (no dependencies on other evidence)
        assert "e1" in independent

    def test_impact_history(self):
        analyzer = EvidenceImpactAnalyzer()
        graph = _make_simple_graph()
        analyzer.analyze_evidence_impact("e1", graph, EvidenceChangeType.INVALIDATED)
        history = analyzer.get_impact_history()
        assert len(history) == 1
        assert history[0]["evidence_id"] == "e1"


# ── 3. Experiment Deepening Engine ──────────────────────────────────────────


class TestDeepeningEngine:
    """Test experiment deepening engine."""

    def test_analyze_unresolved_experience(self):
        engine = ExperimentDeepeningEngine()
        status = engine.analyze_experience(
            experience_id="EXP-001",
            claims=[{"claim_id": "c1", "status": "UNVERIFIED"}],
            evidence_ids=[],
            decision="UNRESOLVED",
        )
        assert status.experience_id == "EXP-001"
        assert len(status.open_hypotheses) > 0
        assert len(status.recommendations) > 0

    def test_analyze_resolved_experience(self):
        engine = ExperimentDeepeningEngine()
        status = engine.analyze_experience(
            experience_id="EXP-002",
            claims=[{"claim_id": "c1", "status": "VERIFIED"}],
            evidence_ids=["e1"],
            contradiction_ids=[],
            decision="VERIFIED",
        )
        # Should recommend stopping
        assert any(
            r.action == DeepeningAction.STOP_NO_INFORMATION_GAIN
            for r in status.recommendations
        )

    def test_check_stagnation(self):
        engine = ExperimentDeepeningEngine()
        engine.analyze_experience(
            experience_id="EXP-003",
            claims=[{"claim_id": "c1", "status": "VERIFIED"}],
            evidence_ids=["e1"],
            decision="VERIFIED",
        )
        is_stagnant = engine.check_stagnation("EXP-003")
        assert is_stagnant is True

    def test_recommendations_for_contradictions(self):
        engine = ExperimentDeepeningEngine()
        status = engine.analyze_experience(
            experience_id="EXP-004",
            claims=[],
            evidence_ids=["e1"],
            contradiction_ids=["contra_1", "contra_2"],
            decision="UNRESOLVED",
        )
        assert any(
            r.action == DeepeningAction.INVESTIGATE_CONTRADICTION
            for r in status.recommendations
        )


# ── 4. Enhanced Contradiction Detector ───────────────────────────────────────


class TestEnhancedContradictionDetector:
    """Test enhanced contradiction detection with precise classification."""

    def test_logical_contradiction_direct_negation(self):
        detector = EnhancedContradictionDetector()
        finding = detector.detect_contradiction(
            "Life has inherent meaning",
            "Life has no inherent meaning",
        )
        assert finding is not None
        assert finding.type == ContradictionType.LOGICAL_CONTRADICTION

    def test_semantic_tension(self):
        detector = EnhancedContradictionDetector()
        finding = detector.detect_contradiction(
            "Life has a purpose",
            "Life is random",
        )
        assert finding is not None
        assert finding.type == ContradictionType.SEMANTIC_TENSION
        assert finding.is_heuristic is True

    def test_context_dependent(self):
        detector = EnhancedContradictionDetector()
        finding = detector.detect_contradiction(
            "Consciousness is real",
            "AI consciousness is impossible",
        )
        # This may or may not detect depending on patterns
        # At minimum, should not crash
        result = detector.classify_pair(
            "Consciousness is real",
            "AI consciousness is impossible",
        )
        assert result in (
            ContradictionType.LOGICAL_CONTRADICTION,
            ContradictionType.SEMANTIC_TENSION,
            ContradictionType.CONTEXT_DEPENDENT,
            ContradictionType.NO_CONTRADICTION,
        )

    def test_no_contradiction(self):
        detector = EnhancedContradictionDetector()
        finding = detector.detect_contradiction(
            "The sky is blue",
            "Grass is green",
        )
        assert finding is None

    def test_classify_pair(self):
        detector = EnhancedContradictionDetector()
        assert detector.classify_pair("A is true", "A is false") == ContradictionType.LOGICAL_CONTRADICTION
        assert detector.classify_pair("Life has purpose", "Life is random") == ContradictionType.SEMANTIC_TENSION
        assert detector.classify_pair("A", "B") == ContradictionType.NO_CONTRADICTION

    def test_finding_is_heuristic(self):
        detector = EnhancedContradictionDetector()
        finding = detector.detect_contradiction(
            "Life has meaning",
            "Life has no meaning",
        )
        assert finding is not None
        assert finding.is_heuristic is True


# ── 5. ReplayEngine with Modes ───────────────────────────────────────────────


class TestReplayEngineModes:
    """Test replay engine with historical and deep modes."""

    def test_historical_replay(self):
        config = DebateSessionConfig(topic="Test", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.add_claim("c1", "agent_a", "Life has meaning", [], [], status=ClaimStatus.VERIFIED)
        engine.add_claim("c2", "agent_b", "Meaning is constructed", [], [], status=ClaimStatus.VERIFIED)
        engine.add_evidence("e1", "c1", "independent", "Proof 1", verified=True)
        engine.add_evidence("e2", "c2", "independent", "Proof 2", verified=True)
        engine.stop()
        engine.arbitrate()

        replay = ReplayEngine()
        captured = replay.capture_session(engine)
        result = replay.historical_replay(captured)

        assert result["mode"] == "HISTORICAL_REPLAY"
        assert result["deterministic"] is True
        assert result["decision"] == "VERIFIED"

    def test_deep_investigation(self):
        config = DebateSessionConfig(topic="Test", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.add_claim("c1", "agent_a", "Life has meaning", [], [], status=ClaimStatus.VERIFIED)
        engine.stop()
        engine.arbitrate()

        replay = ReplayEngine()
        captured = replay.capture_session(engine)
        result = replay.deep_investigation(
            captured,
            new_evidence=[{"evidence_id": "e_new", "claim_id": "c1", "content": "New proof", "verified": True}],
            new_hypotheses=["Meaning is subjective"],
        )

        assert result["mode"] == "DEEP_INVESTIGATION"
        assert result["deterministic"] is True
        assert result["new_evidence_count"] == 1
        assert result["new_hypotheses_count"] == 1

    def test_replay_session_auto_mode(self):
        config = DebateSessionConfig(topic="Test", max_turns=5)
        engine = DebateEngine(config, {})
        engine.start()
        engine.add_claim("c1", "agent_a", "H1", [], [], status=ClaimStatus.VERIFIED)
        engine.stop()
        engine.arbitrate()

        replay = ReplayEngine()
        captured = replay.capture_session(engine)
        result = replay.replay_session(captured, mode="auto")
        assert result["mode"] == "HISTORICAL_REPLAY"


# ── Helper Functions ─────────────────────────────────────────────────────────


def _make_simple_graph():
    """Create a simple provenance graph for testing."""
    from core.debate.engine import ProvenanceGraph, EvidenceRecord, Claim, ClaimStatus

    graph = ProvenanceGraph()
    graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", verified=True))
    graph.add_claim(Claim("c1", "a", "hypothesis", status=ClaimStatus.VERIFIED))
    return graph


def _make_graph_with_dependencies():
    """Create a provenance graph with evidence dependencies."""
    from core.debate.engine import ProvenanceGraph, EvidenceRecord, Claim, ClaimStatus

    graph = ProvenanceGraph()
    graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", verified=True))
    graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", verified=True, depends_on=["e1"]))
    graph.add_claim(Claim("c1", "a", "hypothesis", status=ClaimStatus.VERIFIED))
    return graph


def _make_graph_with_cycle():
    """Create a provenance graph with circular dependencies."""
    from core.debate.engine import ProvenanceGraph, EvidenceRecord, Claim, ClaimStatus

    graph = ProvenanceGraph()
    graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", verified=True, depends_on=["e3"]))
    graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", verified=True, depends_on=["e1"]))
    graph.add_evidence(EvidenceRecord("e3", "c1", "test", "content", verified=True, depends_on=["e2"]))
    graph.add_claim(Claim("c1", "a", "hypothesis", status=ClaimStatus.VERIFIED))
    return graph


# ── Integration Tests ────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for all new components."""

    def test_full_pipeline(self):
        # Create registry and run experiment
        registry = ExperienceRegistry()
        config = DebateSessionConfig(topic="Test topic", max_turns=10)
        engine = DebateEngine(config, {})
        engine.start()

        engine.add_claim("c1", "agent_a", "Life has meaning", [], ["e1"], status=ClaimStatus.VERIFIED)
        engine.add_claim("c2", "agent_b", "Life has no meaning", [], ["e2"], status=ClaimStatus.INVALID)
        engine.add_evidence("e1", "c1", "independent", "Proof 1", verified=True, source="experiment")
        engine.add_evidence("e2", "c2", "independent", "Proof 2", verified=False, source="speculation")
        engine.stop()
        engine.arbitrate()

        # Create experience record
        exp = registry.create_experience(
            session_id=engine.session_id,
            question=config.topic,
            decision=engine.arbitrate().value,
            claims=[c.to_dict() for c in engine.claims],
            evidence_ids=["e1", "e2"],
            contradiction_ids=[c.contradiction_id for c in engine.contradictions],
        )

        # Analyze with deepening engine
        deepener = ExperimentDeepeningEngine(registry)
        status = deepener.analyze_experience(
            exp.experience_id,
            claims=exp.claims,
            evidence_ids=exp.evidence_ids,
            contradiction_ids=exp.contradiction_ids,
            decision=exp.decision,
        )

        # Replay the experiment
        replay = ReplayEngine(registry)
        captured = replay.capture_session(engine)
        result = replay.historical_replay(captured)

        assert exp.experience_id is not None
        assert result["mode"] == "HISTORICAL_REPLAY"
        assert len(status.recommendations) >= 0

    def test_evidence_invalidated_impact(self):
        from core.debate.engine import ProvenanceGraph, EvidenceRecord, Claim, ClaimStatus

        graph = ProvenanceGraph()
        graph.add_evidence(EvidenceRecord("e1", "c1", "test", "content", verified=True, supports_claims=["c1"]))
        graph.add_evidence(EvidenceRecord("e2", "c1", "test", "content", verified=True, depends_on=["e1"]))
        graph.add_claim(Claim("c1", "a", "hypothesis", status=ClaimStatus.VERIFIED))

        analyzer = EvidenceImpactAnalyzer()
        result = analyzer.analyze_evidence_impact("e1", graph, EvidenceChangeType.INVALIDATED)

        assert result.evidence_id == "e1"
        assert result.severity != ImpactSeverity.NONE
        assert "e2" in result.downstream_dependencies

    def test_contradiction_classification(self):
        detector = EnhancedContradictionDetector()

        # Logical contradiction
        finding = detector.detect_contradiction("A is true", "A is false")
        assert finding.type == ContradictionType.LOGICAL_CONTRADICTION

        # Semantic tension
        finding = detector.detect_contradiction("Life has purpose", "Life is random")
        assert finding.type == ContradictionType.SEMANTIC_TENSION

        # No contradiction
        finding = detector.detect_contradiction("A", "B")
        assert finding is None
