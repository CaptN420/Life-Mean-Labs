"""Compare V1 — deterministic analysis engine.

Turns a set of run metrics + pairwise comparability into labelled findings.
Every finding is deterministic and carries its evidence (run ids / task ids)
so it stays traceable to RAW. Findings are separated (spec §26) into:

- OBSERVATION       — a measured fact (a pass-rate difference, a shared tool)
- HYPOTHESIS        — an interpretation of an observation; NEVER presented as
                      evidence, and only emitted when the comparison is
                      actually controlled (or explicitly flagged as exploratory)
- REPAIR_CANDIDATE  — a concrete, testable fix suggestion (a failing tool, a
                      repeated no-answer)

The engine never claims causality from an uncontrolled comparison: a
HYPOTHESIS is only produced for a HIGHLY_CONTROLLED / PARTIALLY_CONTROLLED
pair, otherwise the difference is reported as a bare OBSERVATION with the
comparability level attached. Failure patterns aggregate repeated failure
reasons across runs.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional

from compare.comparability import compare_pair
from compare.models import (
    ComparabilityKind,
    ComparisonOutcome,
    FailurePattern,
    Finding,
    FindingKind,
    PairOutcome,
    RunMetrics,
)

# A comparability level loose enough that a hypothesis (interpretation) is
# defensible. Anything looser gets a plain observation, never a hypothesis.
_HYPOTHESIS_ALLOWED = {
    ComparabilityKind.HIGHLY_CONTROLLED,
    ComparabilityKind.PARTIALLY_CONTROLLED,
}


def _pct(run: RunMetrics) -> str:
    return f"{run.success_rate * 100:.1f}%"


def _observation(runs: List[RunMetrics]) -> Optional[Finding]:
    """A measured summary if more than one run has verdicts."""
    with_verdicts = [r for r in runs if r.has_verdicts]
    if len(with_verdicts) < 2:
        return None
    rows = ", ".join(f"{r.experiment_id}={_pct(r)}" for r in with_verdicts)
    return Finding(
        kind=FindingKind.OBSERVATION,
        message=f"measured success rates: {rows}",
        evidence=[f"{r.experiment_id}:{r.run_id}" for r in with_verdicts],
        runs=[r.experiment_id for r in with_verdicts],
    )


def _newline_evidence(runs: List[RunMetrics]) -> List[str]:
    """Task-id evidence for any run that has no verdicts (NOT_REACHED honor)."""
    out: List[str] = []
    for r in runs:
        if r.num_no_verdict:
            out.append(f"{r.experiment_id}:no_verdict={r.num_no_verdict}")
    return out


def _pair_findings(pair: PairOutcome, left: RunMetrics, right: RunMetrics) -> List[Finding]:
    """Findings grounded in ONE pair's comparison."""
    findings: List[Finding] = []
    if not left.has_verdicts and not right.has_verdicts:
        return findings

    # Which is higher? A measured difference.
    diff = left.success_rate - right.success_rate
    if diff != 0.0 and left.has_verdicts and right.has_verdicts:
        higher, lower = (left, right) if diff > 0 else (right, left)
        obs = Finding(
            kind=FindingKind.OBSERVATION,
            message=(f"{higher.experiment_id} ({_pct(higher)}) scored "
                     f"higher than {lower.experiment_id} ({_pct(lower)}) "
                     f"[comparability={pair.comparability}]"),
            evidence=[f"{left.experiment_id}:{left.run_id}",
                      f"{right.experiment_id}:{right.run_id}"],
            runs=[left.experiment_id, right.experiment_id],
        )
        findings.append(obs)

        # Interpretation only when the comparison is actually controlled.
        if pair.comparability in _HYPOTHESIS_ALLOWED:
            if pair.changed_variables:
                var_desc = ", ".join(pair.changed_variables)
                message = (f"difference may relate to changed variable(s): "
                           f"{var_desc} (needs replication; not a causal claim) "
                           f"[comparability={pair.comparability}]")
            else:
                message = (f"difference persists under identical recorded "
                           f"conditions — suggests seed/stochastic variance "
                           f"rather than a variable effect "
                           f"[comparability={pair.comparability}]")
            findings.append(Finding(
                kind=FindingKind.HYPOTHESIS,
                message=message,
                evidence=[f"{left.experiment_id}:{left.run_id}",
                          f"{right.experiment_id}:{right.run_id}"],
                runs=[left.experiment_id, right.experiment_id],
            ))
        elif diff != 0.0:
            findings.append(Finding(
                kind=FindingKind.OBSERVATION,
                message=(f"success-rate difference observed but comparison is "
                         f"{pair.comparability}; do NOT interpret causally"),
                evidence=[f"{left.experiment_id}:{left.run_id}",
                          f"{right.experiment_id}:{right.run_id}"],
                runs=[left.experiment_id, right.experiment_id],
            ))
    return findings


def _tool_failure_findings(runs: List[RunMetrics]) -> List[Finding]:
    """A tool that appears only on failing tasks is a REPAIR_CANDIDATE."""
    findings: List[Finding] = []
    for r in runs:
        if not r.failure_reasons:
            continue
        failing_tasks = [t for t in r.tasks if t.valid is False]
        # Tools used by at least one failing task.
        failing_tools = sorted({t for task in failing_tasks for t in task.tools_used})
        if failing_tools:
            findings.append(Finding(
                kind=FindingKind.REPAIR_CANDIDATE,
                message=(f"{r.experiment_id}: tools {', '.join(failing_tools)} "
                         f"appear on {len(failing_tasks)} failing task(s) "
                         f"(reasons: {', '.join(r.failure_reasons)})"),
                evidence=[f"{r.experiment_id}:{t.task_id}" for t in failing_tasks[:10]],
                runs=[r.experiment_id],
            ))
    return findings


def _no_verdict_findings(runs: List[RunMetrics]) -> List[Finding]:
    """A run with no verdicts is NOT_REACHED, not a measured FAIL (§25)."""
    findings: List[Finding] = []
    for r in runs:
        if r.num_no_verdict and r.num_tasks == r.num_no_verdict:
            findings.append(Finding(
                kind=FindingKind.OBSERVATION,
                message=(f"{r.experiment_id}: all {r.num_no_verdict} task(s) "
                         f"have no verification verdict (NOT_REACHED / tool "
                         f"returned no answer) — not a measured fail"),
                evidence=[f"{r.experiment_id}:{r.run_id}"],
                runs=[r.experiment_id],
            ))
    return findings


def _failure_patterns(runs: List[RunMetrics]) -> List[FailurePattern]:
    """Aggregate repeated failure reasons across runs."""
    by_reason: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"runs": [], "count": 0, "tools": set()})
    for r in runs:
        for reason, count in r.failure_reasons.items():
            entry = by_reason[reason]
            if r.experiment_id not in entry["runs"]:
                entry["runs"].append(r.experiment_id)
            entry["count"] += count
            for t in r.tasks:
                if t.valid is False and t.failure_reason == reason:
                    for tool in t.tools_used:
                        entry["tools"].add(tool)
    patterns = [
        FailurePattern(
            failure_reason=reason,
            runs=sorted(entry["runs"]),
            count=entry["count"],
            tools=sorted(entry["tools"]),
        )
        for reason, entry in sorted(by_reason.items())
    ]
    # Only surfaces persistent patterns (appears in >1 run) as interesting.
    return [p for p in patterns if len(p.runs) > 1]


class CompareEngine:
    """Deterministic comparison over a set of experiment runs."""

    def compare(self, experiment_ids: Iterable[str],
                runs: Optional[List[RunMetrics]] = None) -> ComparisonOutcome:
        """Compare a set of experiments.

        Args:
            experiment_ids: experiment ids (each must have RAW evidence) —
                used for pairwise naming and ordering.
            runs: pre-loaded RunMetrics (optional; when absent they are loaded
                from RAW). A mix of ids and pre-loaded is resolved here.
        """
        from compare.loader import load_experiments

        id_list = list(experiment_ids)
        loaded: Dict[str, RunMetrics] = {}
        if runs:
            for r in runs:
                loaded[r.experiment_id] = r
        to_load = [eid for eid in id_list if eid not in loaded]
        for r in load_experiments(to_load):
            loaded[r.experiment_id] = r

        ordered = [loaded[eid] for eid in id_list if eid in loaded]
        if not ordered:
            return ComparisonOutcome()

        pairs: List[PairOutcome] = []
        for a, b in combinations(ordered, 2):
            pairs.append(compare_pair(a, b))

        # Each pair's own findings are computed from the two runs.
        pair_findings: Dict[str, List[Finding]] = {}
        for a, b in combinations(ordered, 2):
            p = compare_pair(a, b)
            pair_findings[(a.experiment_id, b.experiment_id)] = _pair_findings(p, a, b)

        findings: List[Finding] = []
        for p in pairs:
            findings.extend(pair_findings.get((p.left, p.right)) or [])
        obs = _observation(ordered)
        if obs:
            findings.append(obs)
        findings.extend(_tool_failure_findings(ordered))
        findings.extend(_no_verdict_findings(ordered))

        return ComparisonOutcome(
            runs=ordered,
            pairs=pairs,
            findings=findings,
            failure_patterns=_failure_patterns(ordered),
        )


def build_report(experiment_ids: Iterable[str]) -> Dict[str, Any]:
    """Convenience: run a comparison and return the serializable dict."""
    return CompareEngine().compare(experiment_ids).to_dict()