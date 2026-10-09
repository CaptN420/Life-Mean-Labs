"""Compare V1 — typed data model (no I/O, no analysis logic).

Holds the dataclasses that describe one run's evidence, one pairwise
comparison, and the labelled findings. Deterministic-only: no LLM, no
causality claims. ``FindingKind`` separates OBSERVATION / HYPOTHESIS /
REPAIR_CANDIDATE so the engine never presents an interpretation as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── finding kinds (spec §26: separate OBSERVATION / HYPOTHESIS / REPAIR) ──
FINDING_KINDS = ("OBSERVATION", "HYPOTHESIS", "REPAIR_CANDIDATE")


class FindingKind:
    """Canonical finding kinds. An OBSERVATION is a measured fact; a HYPOTHESIS
    is an interpretation that must not be presented as evidence; a
    REPAIR_CANDIDATE is a concrete, testable fix suggestion."""

    OBSERVATION = "OBSERVATION"
    HYPOTHESIS = "HYPOTHESIS"
    REPAIR_CANDIDATE = "REPAIR_CANDIDATE"


# ── comparability levels (spec §26) ────────────────────────────────────────
COMPARABILITY_LEVELS = (
    "HIGHLY_CONTROLLED",
    "PARTIALLY_CONTROLLED",
    "EXPLORATORY",
    "NOT_DIRECTLY_COMPARABLE",
)


class ComparabilityKind:
    HIGHLY_CONTROLLED = "HIGHLY_CONTROLLED"
    PARTIALLY_CONTROLLED = "PARTIALLY_CONTROLLED"
    EXPLORATORY = "EXPLORATORY"
    NOT_DIRECTLY_COMPARABLE = "NOT_DIRECTLY_COMPARABLE"


@dataclass
class TaskRecord:
    """One RAW task line, reduced to the fields Compare needs.

    ``valid`` is the deterministic validation verdict (True/False/None when
    the RAW line carries no validation result). ``failure_reason`` is a
    coarse, deterministic category derived from the validation result.
    """

    task_id: str
    run_id: str
    experiment_id: str
    domain: str = ""
    difficulty: Optional[int] = None
    valid: Optional[bool] = None
    score: float = 0.0
    tools_used: List[str] = field(default_factory=list)
    workers_used: List[str] = field(default_factory=list)
    failure_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "valid": self.valid,
            "score": self.score,
            "tools_used": list(self.tools_used),
            "workers_used": list(self.workers_used),
            "failure_reason": self.failure_reason,
        }


@dataclass
class RunMetrics:
    """Aggregated, deterministic metrics for ONE experiment/run.

    ``condition`` is the immutable config snapshot (the independent
    variables). ``tasks`` is the per-task evidence. Everything else is
    derived deterministically from those two.
    """

    experiment_id: str
    run_id: str = ""
    condition: Dict[str, Any] = field(default_factory=dict)
    tasks: List[TaskRecord] = field(default_factory=list)

    # ── derived (computed by loader) ──────────────────────────────────────
    num_tasks: int = 0
    num_passed: int = 0
    num_failed: int = 0
    num_no_verdict: int = 0
    success_rate: float = 0.0
    avg_score: float = 0.0
    by_domain: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_difficulty: Dict[str, Dict[str, float]] = field(default_factory=dict)
    tools_used: List[str] = field(default_factory=list)
    workers_used: List[str] = field(default_factory=list)
    failure_reasons: Dict[str, int] = field(default_factory=dict)

    @property
    def has_verdicts(self) -> bool:
        return self.num_tasks > 0 and (self.num_passed + self.num_failed) > 0

    def _tool_counts(self) -> Dict[str, int]:
        """How many tasks each tool appears on (passes + failures)."""
        counts: Dict[str, int] = {}
        for t in self.tasks:
            for tool in t.tools_used:
                counts[tool] = counts.get(tool, 0) + 1
        return dict(sorted(counts.items()))

    def _worker_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for t in self.tasks:
            for w in t.workers_used:
                counts[w] = counts.get(w, 0) + 1
        return dict(sorted(counts.items()))

    def detail(self, max_task_samples: int = 6) -> Dict[str, Any]:
        """Verbose serialization for the run-detail view (pre-comparison).

        Includes the compact summary plus task samples (top failures, some
        passes) so a researcher can inspect an experiment precisely BEFORE
        deciding to compare it. Never emits full prompt/answer content beyond a
        truncated sample — detail stays bounded.
        """
        failing = [t for t in self.tasks if t.valid is False]
        passing = [t for t in self.tasks if t.valid is True]
        no_verdict = [t for t in self.tasks if t.valid is None]

        def sample(tasks, n):
            return [
                {"task_id": t.task_id, "run_id": t.run_id, "domain": t.domain,
                 "difficulty": t.difficulty, "tools": list(t.tools_used),
                 "score": t.score, "failure_reason": t.failure_reason}
                for t in tasks[:n]
            ]

        return {
            **self.to_dict(),
            "tasks": {
                "total": self.num_tasks,
                "no_verdict_count": self.num_no_verdict,
                "failing_sample": sample(failing, max_task_samples),
                "passing_sample": sample(passing, max_task_samples),
                "no_verdict_sample": sample(no_verdict, max_task_samples),
            },
            "tool_counts": self._tool_counts(),
            "worker_counts": self._worker_counts(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "condition": dict(self.condition),
            "num_tasks": self.num_tasks,
            "num_passed": self.num_passed,
            "num_failed": self.num_failed,
            "num_no_verdict": self.num_no_verdict,
            "success_rate": self.success_rate,
            "avg_score": self.avg_score,
            "by_domain": self.by_domain,
            "by_difficulty": self.by_difficulty,
            "tools_used": list(self.tools_used),
            "workers_used": list(self.workers_used),
            "failure_reasons": dict(self.failure_reasons),
        }


@dataclass
class PairOutcome:
    """Result of comparing two runs: comparability + the variables that are
    common vs changed between their conditions."""

    left: str
    right: str
    comparability: str = ComparabilityKind.NOT_DIRECTLY_COMPARABLE
    common_variables: Dict[str, Any] = field(default_factory=dict)
    changed_variables: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "comparability": self.comparability,
            "common_variables": dict(self.common_variables),
            "changed_variables": dict(self.changed_variables),
            "reason": self.reason,
        }


@dataclass
class Finding:
    """A labelled, deterministic finding. ``kind`` is one of FINDING_KINDS.
    ``evidence`` names the runs/tasks the finding is grounded in so it stays
    traceable to RAW."""

    kind: str
    message: str
    evidence: List[str] = field(default_factory=list)
    runs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "evidence": list(self.evidence),
            "runs": list(self.runs),
        }


@dataclass
class FailurePattern:
    """A repeated failure signature across runs (deterministic)."""

    failure_reason: str
    runs: List[str] = field(default_factory=list)
    count: int = 0
    tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_reason": self.failure_reason,
            "runs": list(self.runs),
            "count": self.count,
            "tools": list(self.tools),
        }


@dataclass
class ComparisonOutcome:
    """Full comparison report for a set of runs."""

    runs: List[RunMetrics] = field(default_factory=list)
    pairs: List[PairOutcome] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    failure_patterns: List[FailurePattern] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        """Cross-run aggregate: size, best/worst, shared tools, top failures."""
        if not self.runs:
            return {}
        with_verdicts = [r for r in self.runs if r.has_verdicts]
        n = len(with_verdicts)
        best = max(with_verdicts, key=lambda r: r.success_rate) if n else None
        worst = min(with_verdicts, key=lambda r: r.success_rate) if n else None
        all_tools = sorted({t for r in self.runs for t in r.tools_used})
        fail_total: Dict[str, int] = {}
        for r in self.runs:
            for reason, cnt in r.failure_reasons.items():
                fail_total[reason] = fail_total.get(reason, 0) + cnt
        top_failures = sorted(fail_total.items(), key=lambda kv: kv[1], reverse=True)[:6]
        total_tasks = sum(r.num_tasks for r in self.runs)
        total_passed = sum(r.num_passed for r in self.runs)
        return {
            "num_runs": len(self.runs),
            "num_with_verdicts": n,
            "total_tasks": total_tasks,
            "total_passed": total_passed,
            "overall_pass_rate": (total_passed / total_tasks) if total_tasks else 0.0,
            "best_run": {"experiment_id": best.experiment_id,
                         "success_rate": best.success_rate} if best else None,
            "worst_run": {"experiment_id": worst.experiment_id,
                          "success_rate": worst.success_rate} if worst else None,
            "shared_tools": all_tools,
            "top_failure_reasons": [{"reason": r, "count": c}
                                    for r, c in top_failures],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary(),
            "runs": [r.to_dict() for r in self.runs],
            "pairs": [p.to_dict() for p in self.pairs],
            "findings": [f.to_dict() for f in self.findings],
            "failure_patterns": [fp.to_dict() for fp in self.failure_patterns],
        }