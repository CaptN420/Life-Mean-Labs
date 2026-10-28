"""Tests for LIFE_MEAN safety layer."""
from __future__ import annotations

import pytest
import time

from core.safety.loop_detector import LoopDetector, LoopEvent, LoopSeverity
from core.safety.policy_guard import PolicyGuard, PolicyViolationSeverity
from core.safety.resource_guard import ResourceGuard, ResourceExceeded
from core.safety.incident_manager import IncidentManager, IncidentSeverity, IncidentStatus


# ── Loop Detector Tests ───────────────────────────────────────────────────────

class TestLoopDetector:
    """Test loop detection."""

    def test_no_loop_initial(self):
        """Test no loop on first call."""
        detector = LoopDetector()
        result = detector.record_call("task-001", "worker1", {"result": 42})
        assert result is None

    def test_detect_repeated_calls(self):
        """Test detection of repeated identical calls."""
        detector = LoopDetector(max_attempts=3)

        # Record 3 identical calls
        for i in range(3):
            detector.record_call("task-001", "worker1", {"result": 42})

        # Should detect loop
        result = detector.record_call("task-001", "worker1", {"result": 42})
        assert result is not None
        assert result.severity == LoopSeverity.WARNING

    def test_progress_detected(self):
        """Test that progress prevents loop detection."""
        detector = LoopDetector(max_attempts=5)

        # Record calls with changing results
        for i in range(3):
            result = detector.record_call("task-001", "worker1", {"result": i})

        # Check progress manually - should show progress
        progress = detector.check_progress("task-001", {"result": 2}, [{"result": 0}, {"result": 1}])
        assert progress is True

    def test_rapid_calls_detected(self):
        """Test detection of rapid repeated calls."""
        detector = LoopDetector(max_attempts=5)

        # Record 3 calls in rapid succession (< 100ms)
        for i in range(3):
            detector.record_call("task-001", "worker1", {"result": 42})

        result = detector._detect_loop("task-001")
        # Should detect some issue (either WARNING or ERROR)
        assert result is not None
        assert result.severity in (LoopSeverity.WARNING, LoopSeverity.ERROR)

    def test_reset_task(self):
        """Test resetting task tracking."""
        detector = LoopDetector()
        detector.record_call("task-001", "worker1", {"result": 42})
        detector.reset_task("task-001")

        # Should not detect loop after reset
        result = detector._detect_loop("task-001")
        assert result is None


# ── Policy Guard Tests ────────────────────────────────────────────────────────

class TestPolicyGuard:
    """Test policy enforcement."""

    def test_forbidden_operation(self):
        """Test that forbidden operations are blocked."""
        guard = PolicyGuard()
        result = guard.check_operation("disable_validator", "test_component")
        assert result is False

    def test_allowed_operation(self):
        """Test that allowed operations pass."""
        guard = PolicyGuard()
        result = guard.check_operation("normal_operation", "test_component")
        assert result is True

    def test_resource_limit_check(self):
        """Test resource limit checking."""
        guard = PolicyGuard()
        # Within limits
        assert guard.check_resource_limit("cpu_time", 100.0, 10000.0, "test")
        # Exceeded hard limit
        assert not guard.check_resource_limit("cpu_time", 15000.0, 10000.0, "test")

    def test_validation_modification_check(self):
        """Test validation modification checks."""
        guard = PolicyGuard()
        # Forbidden modification
        assert guard.check_validation_modification("test", "disable_validator") is False
        # Allowed modification
        assert guard.check_validation_modification("test", "enhance_validation") is True

    def test_violation_recording(self):
        """Test that violations are recorded."""
        guard = PolicyGuard()
        guard.check_operation("disable_validator", "test_component")
        violations = guard.get_violations()
        assert len(violations) > 0
        assert violations[0].violation_type.startswith("forbidden_operation:")


# ── Resource Guard Tests ──────────────────────────────────────────────────────

class TestResourceGuard:
    """Test resource monitoring."""

    def test_within_limits(self):
        """Test no event when within limits."""
        guard = ResourceGuard()
        result = guard.check_limit("cpu_time", 100.0, "test_component")
        assert result is None

    def test_soft_limit_warning(self):
        """Test warning at soft limit."""
        guard = ResourceGuard()
        result = guard.check_limit("cpu_time", 5000.0, "test_component")
        assert result is not None
        assert result.severity == "WARNING"

    def test_hard_limit_critical(self):
        """Test critical at hard limit."""
        guard = ResourceGuard()
        result = guard.check_limit("cpu_time", 10000.0, "test_component")
        assert result is not None
        assert result.severity == "CRITICAL"

    def test_update_usage(self):
        """Test updating resource usage."""
        guard = ResourceGuard()
        guard.update_usage("tokens", 5000)
        stats = guard.get_stats()
        assert stats["current_usage"]["tokens"] == 5000.0


# ── Incident Manager Tests ────────────────────────────────────────────────────

class TestIncidentManager:
    """Test incident management."""

    def test_create_incident(self):
        """Test creating an incident."""
        manager = IncidentManager()
        incident = manager.create_incident(
            event_type="LOOP_DETECTED",
            severity=IncidentSeverity.WARNING,
            component="adaptive_router",
            worker="computational_worker",
            task_id="task-001",
        )
        assert incident.event_type == "LOOP_DETECTED"
        assert incident.status == IncidentStatus.OPEN

    def test_resolve_incident(self):
        """Test resolving an incident."""
        manager = IncidentManager()
        incident = manager.create_incident(
            event_type="TEST",
            severity=IncidentSeverity.INFO,
            component="test",
        )
        result = manager.resolve_incident(incident.trace_id)
        assert result is True
        assert incident.status == IncidentStatus.RESOLVED

    def test_get_open_incidents(self):
        """Test getting open incidents."""
        manager = IncidentManager()
        manager.create_incident("LOOP", IncidentSeverity.WARNING, "comp1")
        manager.create_incident("ERROR", IncidentSeverity.ERROR, "comp2")
        manager.resolve_incident(manager.get_open_incidents()[0].trace_id)

        open_incidents = manager.get_open_incidents()
        assert len(open_incidents) == 1

    def test_get_statistics(self):
        """Test getting incident statistics."""
        manager = IncidentManager()
        manager.create_incident("LOOP", IncidentSeverity.WARNING, "comp")
        manager.create_incident("ERROR", IncidentSeverity.ERROR, "comp")

        stats = manager.get_statistics()
        assert stats["total"] == 2
        assert stats["by_severity"]["WARNING"] == 1
        assert stats["by_severity"]["ERROR"] == 1


# ── Run Tests ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
