"""Metacognitive monitor for analyzing execution traces.

Detects recurring errors, compares strategies, measures agent disagreements,
and identifies configuration effectiveness across domains.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .memory import MetacognitiveMemory
from .schemas import RunMemory

logger = logging.getLogger("MetacognitiveMonitor")

# Maximum retry attempts before declaring messages missing
MAX_RETRY_ATTEMPTS = 3


class MetacognitiveMonitor:
    """Analyzes run traces to extract metacognitive insights."""

    def __init__(self, memory: MetacognitiveMemory):
        self._memory = memory

    def analyze_run(
        self, run_id: str, retry_attempts: int = MAX_RETRY_ATTEMPTS
    ) -> Optional[Dict[str, Any]]:
        """Analyze a single run and return insights.

        Retries up to MAX_RETRY_ATTEMPTS times if messages are missing.
        If tokens are insufficient, returns a fallback response indicating
        the run can be re-analyzed on a subsequent attempt.
        """
        for attempt in range(1, retry_attempts + 1):
            memory = self._memory.get_run_memory(run_id)
            if memory is None:
                if attempt < retry_attempts:
                    logger.warning(
                        "Run %s not found (attempt %d/%d), will retry...",
                        run_id,
                        attempt,
                        retry_attempts,
                    )
                    continue
                return None

            # Check for missing tokens/messages
            has_insufficient_tokens = self._check_token_sufficiency(memory)
            if has_insufficient_tokens and attempt < retry_attempts:
                logger.warning(
                    "Insufficient tokens for run %s (attempt %d/%d), will retry...",
                    run_id,
                    attempt,
                    retry_attempts,
                )
                continue

            insights = self._build_insights(run_id, memory)

            # If we exhausted retries but still have issues, mark as needing retry
            if has_insufficient_tokens and attempt == retry_attempts:
                insights["needs_retry"] = True
                insights["retry_message"] = (
                    "Insufficient tokens/messages detected. "
                    "The run can be re-analyzed on a subsequent attempt."
                )

            return insights

        return None

    def _check_token_sufficiency(self, memory: RunMemory) -> bool:
        """Check if the run has sufficient tokens for analysis."""
        # Consider tokens insufficient if:
        # 1. No tokens recorded
        # 2. Agent traces are empty (no messages)
        # 3. Duration is zero (likely failed early)
        if memory.tokens_used is None and not memory.agent_traces:
            return True
        if memory.duration_seconds == 0.0 and not memory.agent_traces:
            return True
        return False

    def _build_insights(
        self, run_id: str, memory: RunMemory
    ) -> Dict[str, Any]:
        """Build insights dict from a run's memory."""
        insights = {
            "run_id": run_id,
            "status": memory.status,
            "success": memory.status == "passed",
            "issues": [],
            "recommendations": [],
        }

        # Check for empty/phantom outputs
        for trace in memory.agent_traces:
            if trace.get("agent") == "DEVELOPER" and not trace.get("response"):
                insights["issues"].append(
                    {
                        "type": "empty_response",
                        "agent": "DEVELOPER",
                        "message": "DEVELOPER returned empty/phantom output",
                    }
                )

        # Check for repeated errors
        error_types = Counter(
            e.get("type", "unknown") for e in memory.errors_detected
        )
        for error_type, count in error_types.most_common():
            if count > 1:
                insights["issues"].append(
                    {"type": "repeated_error", "error_type": error_type, "count": count}
                )

        # Check judge reliability
        if memory.test_results and memory.final_verdict:
            test_passed = memory.test_results.get("passed", 0)
            test_total = memory.test_results.get("total", 0)
            if test_total > 0:
                test_rate = test_passed / test_total
                if memory.final_verdict == "passed" and test_rate < 0.5:
                    insights["issues"].append(
                        {
                            "type": "judge_unreliable",
                            "message": "Judge declared pass but tests mostly failed",
                        }
                    )

        # Generate recommendations
        if not insights["issues"]:
            insights["recommendations"].append("No issues detected")
        else:
            for issue in insights["issues"]:
                if issue["type"] == "empty_response":
                    insights["recommendations"].append(
                        "Check DEVELOPER prompt and model context length"
                    )
                elif issue["type"] == "repeated_error":
                    insights["recommendations"].append(
                        f"Investigate recurring error: {issue['error_type']}"
                    )
                elif issue["type"] == "judge_unreliable":
                    insights["recommendations"].append(
                        "Review Judge validation criteria"
                    )

        return insights

    def detect_recurring_errors(
        self, runs: Optional[List[RunMemory]] = None
    ) -> Dict[str, Any]:
        """Detect errors that recur across multiple runs."""
        if runs is None:
            runs = self._memory.list_all_runs()

        error_patterns: Dict[str, List[str]] = {}
        for run in runs:
            for error in run.errors_detected:
                error_type = error.get("type", "unknown")
                if error_type not in error_patterns:
                    error_patterns[error_type] = []
                error_patterns[error_type].append(run.run_id)

        recurring = {
            error_type: runs
            for error_type, runs in error_patterns.items()
            if len(runs) > 1
        }

        return {
            "recurring_errors": recurring,
            "total_runs_analyzed": len(runs),
            "unique_error_types": len(error_patterns),
        }

    def compare_strategies(
        self,
        strategy_a: str,
        strategy_b: str,
        runs_a: List[RunMemory],
        runs_b: List[RunMemory],
    ) -> Dict[str, Any]:
        """Compare two routing strategies."""
        def compute_metrics(runs: List[RunMemory]) -> Dict[str, Any]:
            if not runs:
                return {"avg_success": 0.0, "avg_duration": 0.0, "count": 0}

            total_passed = sum(
                1 for r in runs if r.status == "passed"
            )
            total_duration = sum(r.duration_seconds for r in runs)

            return {
                "avg_success": total_passed / len(runs),
                "avg_duration": total_duration / len(runs),
                "count": len(runs),
            }

        metrics_a = compute_metrics(runs_a)
        metrics_b = compute_metrics(runs_b)

        conclusion = ""
        if metrics_a["avg_success"] > metrics_b["avg_success"]:
            conclusion = f"{strategy_a} has higher success rate"
        elif metrics_b["avg_success"] > metrics_a["avg_success"]:
            conclusion = f"{strategy_b} has higher success rate"
        else:
            conclusion = "Strategies have similar success rates"

        return {
            "strategy_a": strategy_a,
            "strategy_b": strategy_b,
            "metrics_a": metrics_a,
            "metrics_b": metrics_b,
            "conclusion": conclusion,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def measure_agent_disagreement(
        self, runs: Optional[List[RunMemory]] = None
    ) -> Dict[str, Any]:
        """Measure disagreements between agents in debates."""
        if runs is None:
            runs = self._memory.list_all_runs()

        disagreements = []
        for run in runs:
            if len(run.agent_traces) < 2:
                continue

            for i in range(len(run.agent_traces) - 1):
                agent_a = run.agent_traces[i]
                agent_b = run.agent_traces[i + 1]

                # Check for conflicting outcomes
                if (agent_a.get("ok") != agent_b.get("ok")):
                    disagreements.append(
                        {
                            "run_id": run.run_id,
                            "agent_a": agent_a.get("agent"),
                            "agent_b": agent_b.get("agent"),
                            "disagreement": f"{agent_a.get('agent')}={agent_a.get('ok')}, {agent_b.get('agent')}={agent_b.get('ok')}",
                        }
                    )

        return {
            "total_disagreements": len(disagreements),
            "disagreements": disagreements[:20],  # Limit for readability
            "runs_with_disagreements": len(set(d["run_id"] for d in disagreements)),
        }

    def compare_verdicts_to_tests(
        self, runs: Optional[List[RunMemory]] = None
    ) -> Dict[str, Any]:
        """Compare Judge verdicts against actual test results."""
        if runs is None:
            runs = self._memory.list_all_runs()

        matches = 0
        mismatches = 0
        mismatch_details = []

        for run in runs:
            if not run.test_results or not run.final_verdict:
                continue

            test_passed = run.test_results.get("passed", 0)
            test_total = run.test_results.get("total", 0)

            if test_total == 0:
                continue

            actual_pass = test_passed == test_total
            declared_pass = run.final_verdict == "passed"

            if actual_pass == declared_pass:
                matches += 1
            else:
                mismatches += 1
                mismatch_details.append(
                    {
                        "run_id": run.run_id,
                        "verdict": run.final_verdict,
                        "test_passed": test_passed,
                        "test_total": test_total,
                        "actual_pass": actual_pass,
                        "declared_pass": declared_pass,
                    }
                )

        return {
            "total_compared": matches + mismatches,
            "matches": matches,
            "mismatches": mismatches,
            "accuracy": matches / (matches + mismatches) if (matches + mismatches) > 0 else 0.0,
            "mismatch_details": mismatch_details[:10],
        }

    def identify_domain_effectiveness(
        self, runs: Optional[List[RunMemory]] = None
    ) -> Dict[str, Any]:
        """Identify which configurations work best for each domain."""
        if runs is None:
            runs = self._memory.list_all_runs()

        domain_stats: Dict[str, Dict[str, int]] = {}
        for run in runs:
            domain = run.domain or "unknown"
            if domain not in domain_stats:
                domain_stats[domain] = {"passed": 0, "failed": 0, "total": 0}

            domain_stats[domain]["total"] += 1
            if run.status == "passed":
                domain_stats[domain]["passed"] += 1
            else:
                domain_stats[domain]["failed"] += 1

        result = {}
        for domain, stats in domain_stats.items():
            total = stats["total"]
            result[domain] = {
                "total_runs": total,
                "passed": stats["passed"],
                "failed": stats["failed"],
                "success_rate": stats["passed"] / total if total > 0 else 0.0,
            }

        return result

    def detect_context_drift(
        self, runs: Optional[List[RunMemory]] = None
    ) -> Dict[str, Any]:
        """Detect when runs drift from their initial prompt."""
        if runs is None:
            runs = self._memory.list_all_runs()

        drifts = []
        for run in runs:
            if not run.prompt or not run.plan_proposed:
                continue

            # Simple heuristic: check if plan addresses all constraints
            prompt_lower = run.prompt.lower()
            plan_lower = run.plan_proposed.lower()

            missing_constraints = []
            for constraint in run.constraints:
                if constraint.lower() not in plan_lower:
                    missing_constraints.append(constraint)

            if missing_constraints:
                drifts.append(
                    {
                        "run_id": run.run_id,
                        "missing_constraints": missing_constraints,
                        "drift_severity": "high" if len(missing_constraints) > 2 else "medium",
                    }
                )

        return {
            "total_runs_checked": len(runs),
            "runs_with_drift": len(drifts),
            "drift_rate": len(drifts) / len(runs) if runs else 0.0,
            "drift_details": drifts[:10],
        }

    def generate_report(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a comprehensive metacognitive report."""
        if run_id:
            analysis = self.analyze_run(run_id)
            if analysis is None:
                return {"error": f"Run {run_id} not found"}
            return {"run_analysis": analysis}

        all_runs = self._memory.list_all_runs()
        stats = self._memory.get_statistics()

        return {
            "overall_stats": stats,
            "recurring_errors": self.detect_recurring_errors(all_runs),
            "agent_disagreements": self.measure_agent_disagreement(all_runs),
            "verdict_accuracy": self.compare_verdicts_to_tests(all_runs),
            "domain_effectiveness": self.identify_domain_effectiveness(all_runs),
            "context_drift": self.detect_context_drift(all_runs),
        }
