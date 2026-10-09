"""Weakness analysis for benchmark results.

Identifies where a candidate or stable model fails so the curriculum
controller can steer generation toward meaningful weaknesses.

Design doc §7, §18, §40: weakness signals should preferentially originate from
held-out evaluation, not from the generator's own synthetic tasks.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from experiments.runner import ExperimentResult

logger = logging.getLogger("WeaknessAnalyzer")


@dataclass
class WeaknessProfile:
    """Aggregated weakness profile over benchmark results.

    Reports per-dimension accuracy so weak areas can be targeted.
    """

    total_tasks: int = 0
    total_passed: int = 0
    by_domain: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_difficulty: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_reasoning_type: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_tool: Dict[str, Dict[str, float]] = field(default_factory=dict)
    failure_reasons: Dict[str, int] = field(default_factory=dict)

    @property
    def overall_accuracy(self) -> float:
        """Overall pass rate across all tasks."""
        if self.total_tasks == 0:
            return 0.0
        return self.total_passed / self.total_tasks

    @property
    def weak_domains(self) -> List[str]:
        """Domains scoring below the accuracy threshold."""
        return [
            d for d, stats in self.by_domain.items()
            if stats["accuracy"] < 0.7
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "total_passed": self.total_passed,
            "overall_accuracy": self.overall_accuracy,
            "by_domain": self.by_domain,
            "by_difficulty": self.by_difficulty,
            "by_reasoning_type": self.by_reasoning_type,
            "by_tool": self.by_tool,
            "failure_reasons": self.failure_reasons,
            "weak_domains": self.weak_domains,
        }


class WeaknessAnalyzer:
    """Analyze benchmark results to identify weaknesses.

    Consumes ExperimentResult objects (from experiments.runner) and builds a
    WeaknessProfile broken down by domain, difficulty, reasoning type, and tool.
    """

    def __init__(self, accuracy_threshold: float = 0.7):
        """Initialize the analyzer.

        Args:
            accuracy_threshold: Accuracy below this marks a dimension as weak.
        """
        self._results: List[ExperimentResult] = []
        self._threshold = accuracy_threshold

    def add_result(self, result: ExperimentResult) -> None:
        """Add a benchmark result for analysis."""
        self._results.append(result)

    def add_results(self, results: List[ExperimentResult]) -> None:
        """Add multiple benchmark results."""
        self._results.extend(results)

    def get_results(self) -> List[ExperimentResult]:
        """Return the results being analyzed."""
        return list(self._results)

    def _dimension_stats(
        self, key: str
    ) -> Dict[str, Dict[str, float]]:
        """Accumulate pass counts per value of a dimension.

        Returns:
            {value: {"passed": int, "total": int, "accuracy": float}}
        """
        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "total": 0}
        )
        for r in self._results:
            value = self._value_for(r, key)
            if not value:
                continue
            buckets[value]["total"] += 1
            if r.is_valid:
                buckets[value]["passed"] += 1

        out: Dict[str, Dict[str, float]] = {}
        for value, counts in buckets.items():
            total = counts["total"]
            out[value] = {
                "passed": counts["passed"],
                "total": total,
                "accuracy": (counts["passed"] / total) if total else 0.0,
            }
        return out

    def _value_for(self, result: ExperimentResult, key: str) -> Optional[str]:
        """Extract a dimension value from a result."""
        if key == "domain":
            return result.metadata.get("domain")
        if key == "difficulty":
            diff = result.metadata.get("difficulty")
            return f"diff_{diff}" if diff is not None else None
        if key == "reasoning_type":
            return result.metadata.get("reasoning_type")
        if key == "tool":
            tools = result.tools_used or []
            return tools[0] if tools else None
        return None

    def _failure_reasons(self) -> Dict[str, int]:
        """Count failure reasons across results."""
        reasons: Dict[str, int] = defaultdict(int)
        for r in self._results:
            if r.is_valid:
                continue
            vr = r.validation_result
            if vr is None:
                reasons["no_validation_result"] += 1
            elif vr.error:
                reasons[vr.error] += 1
            elif vr.method == "no_answer":
                reasons["no_answer_computed"] += 1
            else:
                reasons["incorrect_answer"] += 1
        return dict(reasons)

    def analyze(self) -> WeaknessProfile:
        """Analyze collected results and return a weakness profile.

        Returns:
            WeaknessProfile with per-dimension accuracy
        """
        if not self._results:
            logger.warning("No results to analyze")
            return WeaknessProfile()

        profile = WeaknessProfile(
            total_tasks=len(self._results),
            total_passed=sum(1 for r in self._results if r.is_valid),
            by_domain=self._dimension_stats("domain"),
            by_difficulty=self._dimension_stats("difficulty"),
            by_reasoning_type=self._dimension_stats("reasoning_type"),
            by_tool=self._dimension_stats("tool"),
            failure_reasons=self._failure_reasons(),
        )
        logger.info(
            "Analyzed %d results, overall accuracy %.1f%%",
            profile.total_tasks,
            profile.overall_accuracy * 100,
        )
        return profile

    def weakest_dimension(self) -> Dict[str, Any]:
        """Return the single weakest domain for targeted generation.

        Returns:
            {"domain": str, "accuracy": float, "passed": int, "total": int}
        """
        profile = self.analyze()
        if not profile.by_domain:
            return {}
        domain, stats = min(
            profile.by_domain.items(), key=lambda kv: kv[1]["accuracy"]
        )
        return {"domain": domain, **stats}

    def clear(self) -> None:
        """Reset the analyzer."""
        self._results = []