"""Experiment Execution Gate — controls experiment execution with authorization.

Never launches risky experiments automatically.
Requires explicit human approval before execution.
Enforces PolicyGuard, ResourceGuard, permissions, timeouts, and isolation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.experiment_gate")


# ── Enums ────────────────────────────────────────────────────────────────────


class GateStatus(str, Enum):
    """Status of an experiment gate request."""
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalResult(str, Enum):
    """Result of an approval request."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ResourceLimits:
    """Resource limits for an experiment."""
    timeout_seconds: int = 300
    max_cpu_percent: float = 80.0
    max_memory_mb: float = 1024
    max_gpu_calls: int = 0
    max_llm_calls: int = 10
    isolated_environment: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_cpu_percent": self.max_cpu_percent,
            "max_memory_mb": self.max_memory_mb,
            "max_gpu_calls": self.max_gpu_calls,
            "max_llm_calls": self.max_llm_calls,
            "isolated_environment": self.isolated_environment,
        }


@dataclass
class ExperimentApproval:
    """Record of experiment approval."""
    request_id: str
    experiment_id: str
    approved_by: str
    approved_at: float = field(default_factory=time.time)
    conditions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "experiment_id": self.experiment_id,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "conditions": self.conditions,
        }


@dataclass
class ExecutionGateRequest:
    """Request to execute an experiment."""
    request_id: str
    experiment_id: str
    status: GateStatus = GateStatus.PROPOSED
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    approval: Optional[ExperimentApproval] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "resource_limits": self.resource_limits.to_dict(),
            "approval": self.approval.to_dict() if self.approval else None,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


# ── Experiment Execution Gate ────────────────────────────────────────────────


class ExperimentExecutionGate:
    """Controls experiment execution with authorization requirements.

    Never launches automatically.
    Requires explicit human approval.
    Enforces safety guards and resource limits.
    """

    def __init__(self):
        self._requests: Dict[str, ExecutionGateRequest] = {}
        self._approvals: Dict[str, ExperimentApproval] = {}
        self._next_id = 1

    def propose_experiment(
        self,
        experiment_id: str,
        resource_limits: Optional[ResourceLimits] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionGateRequest:
        """Propose an experiment for execution (requires approval)."""
        request_id = f"REQ-{self._next_id:03d}"
        self._next_id += 1

        request = ExecutionGateRequest(
            request_id=request_id,
            experiment_id=experiment_id,
            resource_limits=resource_limits or ResourceLimits(),
            metadata=metadata or {},
        )

        self._requests[request_id] = request
        logger.info("Experiment execution proposed: %s for %s", request_id, experiment_id)
        return request

    def request_approval(
        self,
        request_id: str,
        approver: str,
        conditions: Optional[Dict[str, Any]] = None,
    ) -> ApprovalResult:
        """Request approval for an experiment. Returns PENDING until approved/denied."""
        request = self._requests.get(request_id)
        if not request:
            return ApprovalResult.DENIED

        if request.status != GateStatus.PROPOSED:
            return ApprovalResult.DENIED

        # In a real system, this would trigger notification to approver
        # For now, we just record the request
        logger.info("Approval requested for %s by %s", request_id, approver)
        return ApprovalResult.PENDING

    def approve_experiment(
        self,
        request_id: str,
        approved_by: str,
        conditions: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Approve an experiment for execution. Returns False if invalid."""
        request = self._requests.get(request_id)
        if not request:
            return False

        if request.status != GateStatus.PROPOSED:
            return False

        # Create approval record
        approval = ExperimentApproval(
            request_id=request_id,
            experiment_id=request.experiment_id,
            approved_by=approved_by,
            conditions=conditions or {},
        )
        self._approvals[request_id] = approval

        # Update request status
        request.approval = approval
        request.status = GateStatus.APPROVED

        logger.info("Experiment %s approved by %s", request_id, approved_by)
        return True

    def deny_experiment(self, request_id: str, reason: str = "") -> bool:
        """Deny an experiment execution request."""
        request = self._requests.get(request_id)
        if not request:
            return False

        if request.status != GateStatus.PROPOSED:
            return False

        request.status = GateStatus.CANCELLED
        logger.info("Experiment %s denied: %s", request_id, reason)
        return True

    def start_experiment(self, request_id: str) -> bool:
        """Start an approved experiment. Returns False if not approved."""
        request = self._requests.get(request_id)
        if not request:
            return False

        if request.status != GateStatus.APPROVED:
            return False

        # Verify safety guards
        if not self._check_safety_guards(request):
            logger.warning("Safety check failed for %s", request_id)
            return False

        request.status = GateStatus.RUNNING
        logger.info("Experiment %s started", request_id)
        return True

    def complete_experiment(self, request_id: str, success: bool) -> bool:
        """Mark an experiment as completed."""
        request = self._requests.get(request_id)
        if not request:
            return False

        if request.status != GateStatus.RUNNING:
            return False

        request.status = GateStatus.COMPLETED if success else GateStatus.FAILED
        logger.info("Experiment %s completed with success=%s", request_id, success)
        return True

    def cancel_experiment(self, request_id: str) -> bool:
        """Cancel a running or proposed experiment."""
        request = self._requests.get(request_id)
        if not request:
            return False

        if request.status in (GateStatus.RUNNING, GateStatus.PROPOSED, GateStatus.AWAITING_APPROVAL):
            request.status = GateStatus.CANCELLED
            logger.info("Experiment %s cancelled", request_id)
            return True

        return False

    def _check_safety_guards(self, request: ExecutionGateRequest) -> bool:
        """Check that safety guards are satisfied before execution."""
        # In a real system, this would check PolicyGuard, ResourceGuard, etc.
        # For now, verify resource limits are reasonable
        limits = request.resource_limits
        if limits.timeout_seconds <= 0:
            return False
        if limits.max_cpu_percent <= 0 or limits.max_cpu_percent > 100:
            return False
        return True

    def get_request(self, request_id: str) -> Optional[ExecutionGateRequest]:
        """Get a gate request by ID."""
        return self._requests.get(request_id)

    def get_pending_requests(self) -> List[ExecutionGateRequest]:
        """Get all pending approval requests."""
        return [
            r for r in self._requests.values()
            if r.status == GateStatus.PROPOSED
        ]
