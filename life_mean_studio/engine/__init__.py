"""
Engine layer — Contracts and interfaces for Life_mean Studio.

This module defines the contracts that an independent motor must implement.
It does NOT import or duplicate CodeLabEngine, EventLogger, or compression modules.

The launcher and dashboard are clients of these contracts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import uuid
from datetime import datetime


@dataclass
class SessionMetadata:
    """Metadata for a studio session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: Optional[str] = None
    workflow_id: Optional[str] = None
    status: str = "idle"  # idle, running, completed, failed, cancelled
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMetadata":
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())),
            run_id=data.get("run_id"),
            workflow_id=data.get("workflow_id"),
            status=data.get("status", "idle"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class StudioEvent:
    """Common event format for Life_mean Studio."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    event_type: str = ""  # AGENT_STARTED, TOOL_CALL_REQUESTED, etc.
    status: str = "unknown"
    correlation_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "event_type": self.event_type,
            "status": self.status,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudioEvent":
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.utcnow(),
            session_id=data.get("session_id"),
            run_id=data.get("run_id"),
            agent_id=data.get("agent_id"),
            event_type=data.get("event_type", ""),
            status=data.get("status", "unknown"),
            correlation_id=data.get("correlation_id"),
            payload=data.get("payload", {}),
        )


# Event types supported by Studio
EVENT_TYPES = {
    "TASK_CREATED": "Task creation initiated",
    "WORKFLOW_LOADED": "Workflow configuration loaded",
    "MODEL_CONNECTED": "LLM model connection established",
    "AGENT_STARTED": "Agent execution started",
    "AGENT_MESSAGE": "Agent message emitted",
    "TOOL_CALL_REQUESTED": "Tool call requested",
    "TOOL_CALL_APPROVED": "Tool call approved",
    "TOOL_CALL_DENIED": "Tool call denied",
    "TOOL_CALL_COMPLETED": "Tool call completed",
    "COMPRESSION_STARTED": "Context compression started",
    "COMPRESSION_COMPLETED": "Context compression completed",
    "PATCH_PROPOSED": "Code patch proposed",
    "APPROVAL_REQUIRED": "Human approval required",
    "TEST_STARTED": "Test execution started",
    "TEST_COMPLETED": "Test execution completed",
    "AGENT_FINISHED": "Agent execution finished",
    "RUN_COMPLETED": "Run completed successfully",
    "RUN_FAILED": "Run failed with error",
    "RUN_CANCELLED": "Run cancelled by user",
}


class MotorContract:
    """
    Contract that any motor implementation must satisfy.
    
    The launcher and dashboard interact with motors through this interface.
    This allows swapping motor implementations without changing clients.
    """
    
    async def start_session(self, workflow_id: str) -> SessionMetadata:
        """Start a new session with the given workflow."""
        raise NotImplementedError
    
    async def stop_session(self, session_id: str) -> bool:
        """Stop an active session."""
        raise NotImplementedError
    
    async def get_session_status(self, session_id: str) -> SessionMetadata:
        """Get current session status."""
        raise NotImplementedError
    
    async def emit_event(self, event: StudioEvent) -> bool:
        """Emit a structured event."""
        raise NotImplementedError
    
    async def get_events(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[StudioEvent]:
        """Retrieve events with optional filtering."""
        raise NotImplementedError
