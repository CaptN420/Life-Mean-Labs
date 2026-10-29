"""Tests for robust persistence (SQLite) and smart investigation triggers."""

import pytest
import sqlite3
import time
from pathlib import Path
from core.debate.persistence import (
    PersistenceEngine,
    DBExperience,
    ImmutabilityError,
    enforce_immutable_experience,
)
from core.debate.evidence_impact import (
    EvidenceImpactAnalyzer,
    EvidenceChangeType,
    ImpactSeverity,
    InvestigationTrigger,
    ReinvestigationStatus,
    ReinvestigationRequest,
)
from core.debate.experience_registry import (
    ExperienceRegistry,
    ExperienceRecord,
    ExperienceType,
    ExperienceStatus,
)
from core.debate.engine import ProvenanceGraph, EvidenceRecord, Claim, ClaimStatus


# ── Persistence Tests ────────────────────────────────────────────────────────


class TestPersistenceEngine:
    """Test SQLite-backed persistence."""

    def test_initialize_schema(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        # Verify tables exist
        conn = sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "experiences" in table_names
        assert "schema_migrations" in table_names
        conn.close()

    def test_create_experience(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        record = {
            "experience_id": "EXP-0001",
            "session_id": "SESSION-001",
            "question": "Does life have meaning?",
            "hypotheses": ["Life has inherent meaning"],
            "claims": [{"claim_id": "c1", "status": "VERIFIED"}],
            "evidence_ids": ["e1"],
            "contradiction_ids": [],
            "conclusions": ["meaning_exists"],
            "decision": "VERIFIED",
            "rule_version": "1.0.0",
            "created_at": time.time(),
            "status": "COMPLETED",
            "experience_type": "ORIGINAL",
        }

        exp_id = engine.create_experience(record)
        assert exp_id == "EXP-0001"

        # Verify retrieval
        retrieved = engine.get_experience("EXP-0001")
        assert retrieved is not None
        assert retrieved["question"] == "Does life have meaning?"
        assert retrieved["decision"] == "VERIFIED"

    def test_get_by_session(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        engine.create_experience({
            "experience_id": "EXP-0001",
            "session_id": "SESSION-A",
            "question": "Q1",
            "created_at": time.time(),
        })
        engine.create_experience({
            "experience_id": "EXP-0002",
            "session_id": "SESSION-A",
            "question": "Q2",
            "created_at": time.time(),
        })
        engine.create_experience({
            "experience_id": "EXP-0003",
            "session_id": "SESSION-B",
            "question": "Q3",
            "created_at": time.time(),
        })

        results = engine.get_by_session("SESSION-A")
        assert len(results) == 2
        assert all(r["session_id"] == "SESSION-A" for r in results)

    def test_search_by_question(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        engine.create_experience({
            "experience_id": "EXP-0001",
            "session_id": "S1",
            "question": "Does life have inherent meaning?",
            "created_at": time.time(),
        })
        engine.create_experience({
            "experience_id": "EXP-0002",
            "session_id": "S2",
            "question": "What is consciousness?",
            "created_at": time.time(),
        })

        results = engine.search_by_question("meaning")
        assert len(results) == 1
        assert results[0]["experience_id"] == "EXP-0001"

    def test_get_derived_experiences(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        engine.create_experience({
            "experience_id": "EXP-0001",
            "session_id": "S1",
            "question": "Original",
            "created_at": time.time(),
        })
        engine.create_experience({
            "experience_id": "EXP-0002",
            "session_id": "S2",
            "question": "Derived 1",
            "parent_experience_id": "EXP-0001",
            "created_at": time.time(),
        })
        engine.create_experience({
            "experience_id": "EXP-0003",
            "session_id": "S3",
            "question": "Derived 2",
            "parent_experience_id": "EXP-0001",
            "created_at": time.time(),
        })

        derived = engine.get_derived_experiences("EXP-0001")
        assert len(derived) == 2
        assert derived[0]["experience_id"] in ["EXP-0002", "EXP-0003"]

    def test_get_statistics(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        engine.create_experience({
            "experience_id": "EXP-0001",
            "session_id": "S1",
            "question": "Q1",
            "decision": "VERIFIED",
            "status": "COMPLETED",
            "experience_type": "ORIGINAL",
            "created_at": time.time(),
        })
        engine.create_experience({
            "experience_id": "EXP-0002",
            "session_id": "S2",
            "question": "Q2",
            "decision": "PARTIAL",
            "status": "COMPLETED",
            "experience_type": "DEEP_INVESTIGATION",
            "created_at": time.time(),
        })

        stats = engine.get_statistics()
        assert stats["total_experiences"] == 2
        assert stats["by_decision"]["VERIFIED"] == 1
        assert stats["by_decision"]["PARTIAL"] == 1
        assert stats["by_type"]["ORIGINAL"] == 1
        assert stats["by_type"]["DEEP_INVESTIGATION"] == 1

    def test_foreign_key_constraint(self, tmp_path):
        """Test that foreign key constraints are enforced."""
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        # Try to create a derived experience with non-existent parent
        # This should fail due to foreign key constraint
        conn = engine.connection
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO experiences (
                    experience_id, session_id, question, created_at,
                    parent_experience_id, status, experience_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("EXP-9999", "S1", "Invalid", time.time(), "NONEXISTENT", "COMPLETED", "DEEP_INVESTIGATION"),
            )
            conn.commit()


# ── Smart Trigger Tests ─────────────────────────────────────────────────────


class TestInvestigationTrigger:
    """Test smart investigation triggers."""

    def test_check_reinvestigation_needed(self):
        registry = ExperienceRegistry()
        analyzer = EvidenceImpactAnalyzer()

        # Create some past experiences
        registry.create_experience("S1", "Does life have inherent meaning?")
        registry.create_experience("S2", "What is consciousness?")

        trigger = InvestigationTrigger()
        provenance_graph = ProvenanceGraph()

        # New evidence about meaning
        request = trigger.check_reinvestigation_needed(
            new_evidence_id="e_new",
            new_evidence_content="New proof that life has inherent meaning through existential commitment",
            registry=registry,
            analyzer=analyzer,
            provenance_graph=provenance_graph,
        )

        # Should find affected experience
        assert request is not None
        assert request.new_evidence_id == "e_new"
        assert len(request.affected_experience_ids) > 0
        assert request.status == ReinvestigationStatus.PENDING

    def test_no_reinvestigation_when_no_match(self):
        registry = ExperienceRegistry()
        analyzer = EvidenceImpactAnalyzer()

        # Create experiences unrelated to new evidence
        registry.create_experience("S1", "What is the meaning of life?")
        registry.create_experience("S2", "Is consciousness real?")

        trigger = InvestigationTrigger()
        provenance_graph = ProvenanceGraph()

        # New evidence about something completely different
        request = trigger.check_reinvestigation_needed(
            new_evidence_id="e_new",
            new_evidence_content="New proof about quantum mechanics and particle physics",
            registry=registry,
            analyzer=analyzer,
            provenance_graph=provenance_graph,
        )

        # Should not find affected experiences (no keyword match)
        assert request is None

    def test_authorize_request(self):
        trigger = InvestigationTrigger()
        request = ReinvestigationRequest(
            request_id="REQ-001",
            timestamp=time.time(),
            new_evidence_id="e_new",
            affected_experience_ids=["EXP-0001"],
            severity=ImpactSeverity.MEDIUM,
            reason="Test reason",
        )
        trigger._pending_requests["REQ-001"] = request

        result = trigger.authorize_request("REQ-001", "admin")
        assert result is True
        assert request.status == ReinvestigationStatus.AUTHORIZED
        assert request.authorized_by == "admin"

    def test_deny_request(self):
        trigger = InvestigationTrigger()
        request = ReinvestigationRequest(
            request_id="REQ-002",
            timestamp=time.time(),
            new_evidence_id="e_new",
            affected_experience_ids=["EXP-0001"],
            severity=ImpactSeverity.LOW,
            reason="Test reason",
        )
        trigger._pending_requests["REQ-002"] = request

        result = trigger.deny_request("REQ-002", "Insufficient evidence")
        assert result is True
        assert request.status == ReinvestigationStatus.DENIED

    def test_get_pending_requests(self):
        trigger = InvestigationTrigger()
        trigger._pending_requests["REQ-001"] = ReinvestigationRequest(
            request_id="REQ-001",
            timestamp=time.time(),
            new_evidence_id="e_new",
            affected_experience_ids=["EXP-0001"],
            severity=ImpactSeverity.MEDIUM,
            reason="Test",
        )
        trigger._pending_requests["REQ-002"] = ReinvestigationRequest(
            request_id="REQ-002",
            timestamp=time.time(),
            new_evidence_id="e_new2",
            affected_experience_ids=["EXP-0002"],
            severity=ImpactSeverity.HIGH,
            reason="Test 2",
        )

        pending = trigger.get_pending_requests()
        assert len(pending) == 2

    def test_request_not_found(self):
        trigger = InvestigationTrigger()
        result = trigger.authorize_request("REQ-NONEXISTENT", "admin")
        assert result is False

    def test_double_authorization_prevented(self):
        trigger = InvestigationTrigger()
        request = ReinvestigationRequest(
            request_id="REQ-003",
            timestamp=time.time(),
            new_evidence_id="e_new",
            affected_experience_ids=["EXP-0001"],
            severity=ImpactSeverity.MEDIUM,
            reason="Test",
        )
        trigger._pending_requests["REQ-003"] = request

        # First authorization
        result1 = trigger.authorize_request("REQ-003", "admin")
        assert result1 is True
        assert request.status == ReinvestigationStatus.AUTHORIZED

        # Second authorization should fail
        result2 = trigger.authorize_request("REQ-003", "admin2")
        assert result2 is False


# ── Integration Tests ────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for persistence and triggers."""

    def test_full_persistence_workflow(self, tmp_path):
        """Test complete workflow with SQLite persistence."""
        db_path = str(tmp_path / "experiences.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        # Create experiences
        exp1 = {
            "experience_id": "EXP-0001",
            "session_id": "SESSION-001",
            "question": "Does life have inherent meaning?",
            "hypotheses": ["Life has inherent meaning"],
            "claims": [{"claim_id": "c1", "status": "VERIFIED"}],
            "evidence_ids": ["e1"],
            "contradiction_ids": [],
            "conclusions": ["meaning_exists"],
            "decision": "VERIFIED",
            "rule_version": "1.0.0",
            "created_at": time.time(),
            "status": "COMPLETED",
            "experience_type": "ORIGINAL",
        }
        engine.create_experience(exp1)

        # Create derived experience
        exp2 = {
            "experience_id": "EXP-0002",
            "session_id": "SESSION-002",
            "question": "Follow-up: What is consciousness?",
            "hypotheses": ["Consciousness is emergent"],
            "claims": [{"claim_id": "c1", "status": "PARTIAL"}],
            "evidence_ids": ["e2"],
            "contradiction_ids": ["contra_1"],
            "conclusions": ["consciousness_emergent"],
            "decision": "PARTIAL",
            "rule_version": "1.0.0",
            "created_at": time.time() + 1,
            "status": "COMPLETED",
            "experience_type": "DEEP_INVESTIGATION",
            "parent_experience_id": "EXP-0001",
        }
        engine.create_experience(exp2)

        # Verify retrieval
        retrieved = engine.get_experience("EXP-0001")
        assert retrieved is not None
        assert retrieved["question"] == "Does life have inherent meaning?"

        # Verify derived relationship
        derived = engine.get_derived_experiences("EXP-0001")
        assert len(derived) == 1
        assert derived[0]["experience_id"] == "EXP-0002"

        # Verify statistics
        stats = engine.get_statistics()
        assert stats["total_experiences"] == 2

    def test_smart_trigger_with_persistence(self, tmp_path):
        """Test smart trigger integrated with persistence."""
        db_path = str(tmp_path / "experiences.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        # Create experiences via persistence engine
        engine.create_experience({
            "experience_id": "EXP-0001",
            "session_id": "S1",
            "question": "Does life have inherent meaning?",
            "hypotheses": ["Life has inherent meaning through existential commitment"],
            "decision": "VERIFIED",
            "created_at": time.time(),
            "status": "COMPLETED",
        })

        # Create in-memory registry for trigger
        registry = ExperienceRegistry()
        registry.create_experience("S1", "Does life have inherent meaning?")

        analyzer = EvidenceImpactAnalyzer()
        trigger = InvestigationTrigger()
        provenance_graph = ProvenanceGraph()

        # Check if reinvestigation is needed
        request = trigger.check_reinvestigation_needed(
            new_evidence_id="e_new",
            new_evidence_content="New proof that life has inherent meaning through existential commitment",
            registry=registry,
            analyzer=analyzer,
            provenance_graph=provenance_graph,
        )

        assert request is not None
        assert request.status == ReinvestigationStatus.PENDING

        # Authorize
        authorized = trigger.authorize_request(request.request_id, "researcher")
        assert authorized is True
        assert request.status == ReinvestigationStatus.AUTHORIZED


# ── Immutability Tests ───────────────────────────────────────────────────────


class TestImmutability:
    """Test immutability enforcement."""

    def test_enforce_immutable(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        engine.create_experience({
            "experience_id": "EXP-0001",
            "session_id": "S1",
            "question": "Q1",
            "created_at": time.time(),
        })

        # Should succeed for existing experience
        result = enforce_immutable_experience(engine.connection, "EXP-0001")
        assert result is True

    def test_enforce_nonexistent_raises(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = PersistenceEngine(db_path)
        engine.initialize()

        with pytest.raises(ValueError):
            enforce_immutable_experience(engine.connection, "NONEXISTENT")
