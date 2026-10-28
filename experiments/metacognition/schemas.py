"""Metacognitive memory schemas.

Stores run-level metadata, agent traces, decisions, and outcomes
for post-hoc analysis and cross-run comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class RunMemory:
    """Complete memory record for a single lab run."""

    run_id: str
    project: str
    status: str  # "passed", "failed", "stopped"

    # Initial conditions
    prompt: str = ""
    constraints: List[str] = field(default_factory=list)
    domain: str = ""
    classification: str = ""

    # Routing and models
    router_used: str = ""
    models_selected: List[str] = field(default_factory=list)

    # Plan and execution
    plan_proposed: str = ""
    pipeline_steps: List[str] = field(default_factory=list)

    # Agent interactions
    agent_traces: List[Dict[str, Any]] = field(default_factory=list)
    critiques: List[str] = field(default_factory=list)
    revisions: List[str] = field(default_factory=list)

    # Decisions and outcomes
    judge_decision: str = ""
    judge_reasoning: str = ""
    test_results: Dict[str, Any] = field(default_factory=dict)
    final_verdict: str = ""

    # Errors and corrections
    errors_detected: List[Dict[str, Any]] = field(default_factory=list)
    corrections_applied: List[Dict[str, Any]] = field(default_factory=list)

    # Resource metrics
    duration_seconds: float = 0.0
    tokens_used: Optional[int] = None
    iterations: int = 0

    # Timestamps
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project": self.project,
            "status": self.status,
            "prompt": self.prompt,
            "constraints": self.constraints,
            "domain": self.domain,
            "classification": self.classification,
            "router_used": self.router_used,
            "models_selected": self.models_selected,
            "plan_proposed": self.plan_proposed,
            "pipeline_steps": self.pipeline_steps,
            "agent_traces": self.agent_traces,
            "critiques": self.critiques,
            "revisions": self.revisions,
            "judge_decision": self.judge_decision,
            "judge_reasoning": self.judge_reasoning,
            "test_results": self.test_results,
            "final_verdict": self.final_verdict,
            "errors_detected": self.errors_detected,
            "corrections_applied": self.corrections_applied,
            "duration_seconds": self.duration_seconds,
            "tokens_used": self.tokens_used,
            "iterations": self.iterations,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunMemory":
        return cls(
            run_id=data["run_id"],
            project=data.get("project", ""),
            status=data.get("status", "unknown"),
            prompt=data.get("prompt", ""),
            constraints=data.get("constraints", []),
            domain=data.get("domain", ""),
            classification=data.get("classification", ""),
            router_used=data.get("router_used", ""),
            models_selected=data.get("models_selected", []),
            plan_proposed=data.get("plan_proposed", ""),
            pipeline_steps=data.get("pipeline_steps", []),
            agent_traces=data.get("agent_traces", []),
            critiques=data.get("critiques", []),
            revisions=data.get("revisions", []),
            judge_decision=data.get("judge_decision", ""),
            judge_reasoning=data.get("judge_reasoning", ""),
            test_results=data.get("test_results", {}),
            final_verdict=data.get("final_verdict", ""),
            errors_detected=data.get("errors_detected", []),
            corrections_applied=data.get("corrections_applied", []),
            duration_seconds=data.get("duration_seconds", 0.0),
            tokens_used=data.get("tokens_used"),
            iterations=data.get("iterations", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class ErrorPattern:
    """Represents a recurring error pattern across runs."""

    error_type: str
    description: str
    occurrence_count: int
    affected_runs: List[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "description": self.description,
            "occurrence_count": self.occurrence_count,
            "affected_runs": self.affected_runs,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorPattern":
        return cls(
            error_type=data["error_type"],
            description=data.get("description", ""),
            occurrence_count=data.get("occurrence_count", 0),
            affected_runs=data.get("affected_runs", []),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
            resolution=data.get("resolution"),
        )


@dataclass
class StrategyComparison:
    """Stores comparison data between different routing strategies."""

    strategy_a: str
    strategy_b: str
    tasks_compared: int = 0
    success_rate_a: float = 0.0
    success_rate_b: float = 0.0
    latency_a: float = 0.0
    latency_b: float = 0.0
    conclusion: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_a": self.strategy_a,
            "strategy_b": self.strategy_b,
            "tasks_compared": self.tasks_compared,
            "success_rate_a": self.success_rate_a,
            "success_rate_b": self.success_rate_b,
            "latency_a": self.latency_a,
            "latency_b": self.latency_b,
            "conclusion": self.conclusion,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyComparison":
        return cls(
            strategy_a=data["strategy_a"],
            strategy_b=data["strategy_b"],
            tasks_compared=data.get("tasks_compared", 0),
            success_rate_a=data.get("success_rate_a", 0.0),
            success_rate_b=data.get("success_rate_b", 0.0),
            latency_a=data.get("latency_a", 0.0),
            latency_b=data.get("latency_b", 0.0),
            conclusion=data.get("conclusion", ""),
            evidence=data.get("evidence", []),
        )
