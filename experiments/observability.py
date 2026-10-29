"""Autopilot observability — deterministic debate trace and live transcript.

Provides structured observability for experiments running through AutoPilot:
- Experiment configuration snapshot (deterministic parameters)
- Active agent state tracking
- Live debate transcript with timestamps
- Deterministic decision trace (why each transition happened)
- Experiment progress metrics

This module REUSES existing architecture — it does not create a parallel system.
"""

from __future__ import annotations

import enum
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("experiments.observability")


# ── Enums ────────────────────────────────────────────────────────────────────


class AgentStatus(str, enum.Enum):
    """Lifecycle status of a debate agent."""
    WAITING = "Waiting"
    SELECTED = "Selected"
    RUNNING = "Running"
    RESPONDING = "Responding"
    ANALYZING = "Analyzing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    STOPPED = "Stopped"


class EventKind(str, enum.Enum):
    """Type of observability event."""
    AGENT_SELECTED = "agent_selected"
    TURN_STARTED = "turn_started"
    TURN_COMPLETED = "turn_completed"
    RULE_APPLIED = "rule_applied"
    TRANSITION = "transition"
    ERROR = "error"
    STOP_REQUESTED = "stop_requested"
    EXPERIMENT_STARTED = "experiment_started"
    EXPERIMENT_COMPLETED = "experiment_completed"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class AgentRecord:
    """State of a single agent during an experiment."""
    agent_id: str
    persona: str = ""
    role: str = ""
    model: str = ""
    provider: str = ""
    status: str = "Waiting"
    current_round: int = 0
    current_step: str = ""
    last_action: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "persona": self.persona,
            "role": self.role,
            "model": self.model,
            "provider": self.provider,
            "status": self.status,
            "current_round": self.current_round,
            "current_step": self.current_step,
            "last_action": self.last_action,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": (self.end_time or time.time()) - (self.start_time or time.time()) if self.start_time else 0,
            "errors": self.errors[-5:],
        }


@dataclass
class DebateEvent:
    """A single event in the debate transcript."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    kind: str = EventKind.TURN_COMPLETED.value
    agent_id: str = ""
    round_num: int = 0
    timestamp: float = field(default_factory=time.time)
    response: str = ""
    rule_applied: str = ""
    rule_version: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "agent_id": self.agent_id,
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "response": self.response[:500] if self.response else "",
            "rule_applied": self.rule_applied,
            "rule_version": self.rule_version,
            "evidence": self.evidence,
            "error": self.error,
        }


@dataclass
class DeterministicTrace:
    """Record of a deterministic decision."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    rule_name: str = ""
    rule_version: str = ""
    input_snapshot: Dict[str, Any] = field(default_factory=dict)
    output_snapshot: Dict[str, Any] = field(default_factory=dict)
    agent_affected: str = ""
    state_before: Dict[str, Any] = field(default_factory=dict)
    state_after: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "rule_name": self.rule_name,
            "rule_version": self.rule_version,
            "input_snapshot": self.input_snapshot,
            "output_snapshot": self.output_snapshot,
            "agent_affected": self.agent_affected,
            "state_before": self.state_before,
            "state_after": self.state_after,
        }


@dataclass
class ExperimentProgress:
    """Current progress of an experiment."""
    experiment_id: str = ""
    status: str = "CREATED"
    current_round: int = 0
    total_rounds: int = 0
    current_step: str = ""
    active_agent: str = ""
    tasks_completed: int = 0
    tasks_total: int = 0
    elapsed_seconds: float = 0.0
    tokens_consumed: int = 0
    errors: List[str] = field(default_factory=list)
    retries: int = 0
    synthesis_status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "status": self.status,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "current_step": self.current_step,
            "active_agent": self.active_agent,
            "tasks_completed": self.tasks_completed,
            "tasks_total": self.tasks_total,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "tokens_consumed": self.tokens_consumed,
            "errors": self.errors[-10:],
            "retries": self.retries,
            "synthesis_status": self.synthesis_status,
        }


# ── Observability Controller ─────────────────────────────────────────────────


class AutopilotObservability:
    """Tracks experiment state for observability UI panels.

    This is a lightweight observer — it does NOT drive execution. It records
    what actually happened so the UI can display real data.
    """

    def __init__(self):
        self._agents: Dict[str, AgentRecord] = {}
        self._events: List[DebateEvent] = []
        self._traces: List[DeterministicTrace] = []
        self._progress: Optional[ExperimentProgress] = None
        self._config_snapshot: Dict[str, Any] = {}
        self._prompt_snapshot: str = ""
        self._lock = __import__("threading").Lock()

    def start_experiment(
        self,
        experiment_id: str,
        config: Dict[str, Any],
        prompt: str = "",
        agents: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Record experiment start with configuration snapshot."""
        with self._lock:
            self._progress = ExperimentProgress(
                experiment_id=experiment_id,
                status="RUNNING",
                tasks_total=config.get("num_tasks", 0),
            )
            self._config_snapshot = config
            self._prompt_snapshot = prompt
            self._events.clear()
            self._traces.clear()
            self._agents.clear()

            # Initialize agent records if provided
            if agents:
                for i, agent_cfg in enumerate(agents):
                    agent_id = agent_cfg.get("agent_id", f"agent_{i+1}")
                    self._agents[agent_id] = AgentRecord(
                        agent_id=agent_id,
                        persona=agent_cfg.get("persona", ""),
                        role=agent_cfg.get("role", ""),
                        model=agent_cfg.get("model", ""),
                        provider=agent_cfg.get("provider", "local"),
                        status=AgentStatus.WAITING.value,
                    )

            # Record experiment started event
            self._events.append(DebateEvent(
                kind=EventKind.EXPERIMENT_STARTED.value,
                timestamp=time.time(),
            ))

        logger.info(f"Observability: experiment {experiment_id} started")

    def update_agent_status(self, agent_id: str, status: str, **kwargs) -> None:
        """Update an agent's status."""
        with self._lock:
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                agent.status = status
                if status == AgentStatus.RUNNING.value and not agent.start_time:
                    agent.start_time = time.time()
                for k, v in kwargs.items():
                    if hasattr(agent, k):
                        setattr(agent, k, v)

    def record_turn(self, agent_id: str, round_num: int, response: str, rule: str = "") -> None:
        """Record a completed turn."""
        with self._lock:
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                agent.current_round = round_num
                agent.last_action = f"Round {round_num}: {response[:50]}..."
                agent.status = AgentStatus.COMPLETED.value

            self._events.append(DebateEvent(
                kind=EventKind.TURN_COMPLETED.value,
                agent_id=agent_id,
                round_num=round_num,
                response=response,
                rule_applied=rule,
                timestamp=time.time(),
            ))

    def record_rule_application(self, rule_name: str, rule_version: str, input_data: Dict, output_data: Dict, agent_id: str = "") -> None:
        """Record a deterministic rule application."""
        with self._lock:
            trace = DeterministicTrace(
                rule_name=rule_name,
                rule_version=rule_version,
                input_snapshot=input_data,
                output_snapshot=output_data,
                agent_affected=agent_id,
            )
            self._traces.append(trace)
            self._events.append(DebateEvent(
                kind=EventKind.RULE_APPLIED.value,
                agent_id=agent_id,
                rule_applied=rule_name,
                rule_version=rule_version,
                evidence=[{"type": "rule", "name": rule_name, "version": rule_version}],
                timestamp=time.time(),
            ))

    def record_transition(self, from_state: Dict, to_state: Dict, rule: str, agent_id: str = "") -> None:
        """Record a state transition."""
        with self._lock:
            trace = DeterministicTrace(
                rule_name=rule,
                input_snapshot={"state": from_state},
                output_snapshot={"state": to_state},
                agent_affected=agent_id,
            )
            self._traces.append(trace)
            self._events.append(DebateEvent(
                kind=EventKind.TRANSITION.value,
                agent_id=agent_id,
                rule_applied=rule,
                evidence=[{"type": "transition", "from": from_state, "to": to_state}],
                timestamp=time.time(),
            ))

    def record_error(self, error: str, agent_id: str = "") -> None:
        """Record an error."""
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].errors.append(error)
                self._agents[agent_id].status = AgentStatus.FAILED.value
            self._events.append(DebateEvent(
                kind=EventKind.ERROR.value,
                agent_id=agent_id,
                error=error,
                timestamp=time.time(),
            ))

    def update_progress(self, **kwargs) -> None:
        """Update experiment progress metrics."""
        with self._lock:
            if self._progress:
                for k, v in kwargs.items():
                    if hasattr(self._progress, k):
                        setattr(self._progress, k, v)
                # elapsed_seconds is computed on read, not stored

    def complete_experiment(self, status: str = "COMPLETED") -> None:
        """Mark experiment as complete."""
        with self._lock:
            if self._progress:
                self._progress.status = status
                self._progress.end_time = time.time()
            self._events.append(DebateEvent(
                kind=EventKind.EXPERIMENT_COMPLETED.value,
                timestamp=time.time(),
            ))

    def get_config(self) -> Dict[str, Any]:
        """Get configuration snapshot."""
        with self._lock:
            return dict(self._config_snapshot)

    def get_prompt(self) -> str:
        """Get experiment prompt."""
        with self._lock:
            return self._prompt_snapshot

    def get_agents(self) -> Dict[str, AgentRecord]:
        """Get agent records."""
        with self._lock:
            return dict(self._agents)

    def get_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent events."""
        with self._lock:
            return [e.to_dict() for e in self._events[-limit:]]

    def get_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get deterministic traces."""
        with self._lock:
            return [t.to_dict() for t in self._traces[-limit:]]

    def get_progress(self) -> Optional[Dict[str, Any]]:
        """Get current progress."""
        with self._lock:
            if self._progress:
                return self._progress.to_dict()
            return None

    def export_manifest(self) -> Dict[str, Any]:
        """Export complete experiment manifest for reproducibility."""
        with self._lock:
            return {
                "experiment_id": self._progress.experiment_id if self._progress else "",
                "prompt": self._prompt_snapshot,
                "config": self._config_snapshot,
                "agents": {aid: arec.to_dict() for aid, arec in self._agents.items()},
                "events": [e.to_dict() for e in self._events],
                "traces": [t.to_dict() for t in self._traces],
                "progress": self._progress.to_dict() if self._progress else None,
                "exported_at": time.time(),
            }
