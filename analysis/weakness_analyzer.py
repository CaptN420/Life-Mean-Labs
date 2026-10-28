"""Weakness analysis for benchmark results.

Identifies where a candidate or stable model fails so the curriculum
controller can steer generation toward meaningful weaknesses.

Design doc §7, §18, §40: weakness signals should preferentially originate from
held-out evaluation, not from the generator's own synthetic tasks.

This module does not infer benchmark provenance. Callers can supply a predicate
that selects independently evaluated results when targeting weaknesses.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from experiments.runner import ExperimentResult

logger = logging.getLogger("WeaknessAnalyzer")

Stats = Dict[str, Any]
ResultFilter = Callable[[ExperimentResult], bool]


@dataclass
class WeaknessProfile:
    """Aggregated performance profile over benchmark results."""

    total_tasks: int = 0
    total_passed: int = 0
    by_domain: Dict[str, Stats] = field(default_factory=dict)
    by_difficulty: Dict[str, Stats] = field(default_factory=dict)
    by_reasoning_type: Dict[str, Stats] = field(default_factory=dict)
    by_tool: Dict[str, Stats] = field(default_factory=dict)
    failure_reasons: Dict[str, int] = field(default_factory=dict)
    accuracy_threshold: float = 0.7

    @property
    def overall_accuracy(self) -> float:
        return self.total_passed / self.total_tasks if self.total_tasks else 0.0

    @property
    def weak_domains(self) -> List[str]:
        return [
            domain
            for domain, stats in self.by_domain.items()
            if stats["accuracy"] < self.accuracy_threshold
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
            "accuracy_threshold": self.accuracy_threshold,
        }


class WeaknessAnalyzer:
    """Aggregate benchmark outcomes by domain, difficulty, reasoning, and tool.

    A supplied result_filter can restrict results to trusted, held-out
    evaluations. Without one, all added results are analyzed; the output must
    not be interpreted as held-out performance unless the caller guarantees it.
    """

    def __init__(
        self,
        accuracy_threshold: float = 0.7,
        result_filter: Optional[ResultFilter] = None,
    ) -> None:
        if not 0.0 <= accuracy_threshold <= 1.0:
            raise ValueError("accuracy_threshold must be between 0 and 1")
        self._results: List[ExperimentResult] = []
        self._threshold = accuracy_threshold
        self._result_filter = result_filter

    def add_result(self, result: ExperimentResult) -> None:
        self._results.append(result)

    def add_results(self, results: List[ExperimentResult]) -> None:
        self._results.extend(results)

    def get_results(self) -> List[ExperimentResult]:
        return list(self._results)

    def _selected_results(self) -> List[ExperimentResult]:
        if self._result_filter is None:
            return list(self._results)
        return [result for result in self._results if self._result_filter(result)]

    @staticmethod
    def _values_for(result: ExperimentResult, key: str) -> List[str]:
        metadata = result.metadata or {}
        if key == "domain":
            value = metadata.get("domain")
        elif key == "difficulty":
            difficulty = metadata.get("difficulty")
            value = f"diff_{difficulty}" if difficulty is not None else None
        elif key == "reasoning_type":
            value = metadata.get("reasoning_type")
        elif key == "tool":
            tools = result.tools_used or []
            # Each distinct tool contributes at most once per result.
            return list(dict.fromkeys(
                tool for tool in tools if isinstance(tool, str) and tool
            ))
        else:
            return []
        return [value] if isinstance(value, str) and value else []

    def _value_for(self, result: ExperimentResult, key: str) -> Optional[str]:
        """Legacy single-value helper; use _values_for for multi-tool stats."""
        values = self._values_for(result, key)
        return values[0] if values else None

    def _dimension_stats(
        self, key: str, results: Optional[List[ExperimentResult]] = None
    ) -> Dict[str, Stats]:
        selected = self._selected_results() if results is None else results
        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "total": 0}
        )
        for result in selected:
            for value in self._values_for(result, key):
                buckets[value]["total"] += 1
                if result.is_valid:
                    buckets[value]["passed"] += 1
        return {
            value: {
                "passed": counts["passed"],
                "total": counts["total"],
                "accuracy": counts["passed"] / counts["total"],
            }
            for value, counts in buckets.items()
        }

    def _failure_reasons(
        self, results: Optional[List[ExperimentResult]] = None
    ) -> Dict[str, int]:
        selected = self._selected_results() if results is None else results
        reasons: Dict[str, int] = defaultdict(int)
        for result in selected:
            if result.is_valid:
                continue
            validation = result.validation_result
            if validation is None:
                reason = "no_validation_result"
            elif validation.error:
                reason = str(validation.error)
            elif validation.method == "no_answer":
                reason = "no_answer_computed"
            else:
                reason = "incorrect_answer"
            reasons[reason] += 1
        return dict(reasons)

    def analyze(self) -> WeaknessProfile:
        selected = self._selected_results()
        if not selected:
            logger.warning("No benchmark results selected for analysis")
            return WeaknessProfile(accuracy_threshold=self._threshold)

        profile = WeaknessProfile(
            total_tasks=len(selected),
            total_passed=sum(1 for result in selected if result.is_valid),
            by_domain=self._dimension_stats("domain", selected),
            by_difficulty=self._dimension_stats("difficulty", selected),
            by_reasoning_type=self._dimension_stats("reasoning_type", selected),
            by_tool=self._dimension_stats("tool", selected),
            failure_reasons=self._failure_reasons(selected),
            accuracy_threshold=self._threshold,
        )
        logger.info(
            "Analyzed %d results, overall accuracy %.1f%%",
            profile.total_tasks,
            profile.overall_accuracy * 100,
        )
        return profile

    def weakest_dimension(self, min_tests: int = 5) -> Dict[str, Any]:
        """Return the weakest sufficiently tested domain.

        Lower accuracy ranks first; ties favor larger samples, then names.
        Returns {} when no domain has at least min_tests observations.
        """
        if isinstance(min_tests, bool) or not isinstance(min_tests, int) or min_tests < 1:
            raise ValueError("min_tests must be a positive integer")
        profile = self.analyze()
        eligible = [
            (domain, stats)
            for domain, stats in profile.by_domain.items()
            if stats["total"] >= min_tests
        ]
        if not eligible:
            return {}
        domain, stats = min(
            eligible,
            key=lambda item: (
                item[1]["accuracy"],
                -item[1]["total"],
                item[0],
            ),
        )
        return {"domain": domain, **stats}

    def clear(self) -> None:
        """Clear in-memory results; does not delete persisted benchmarks."""
        self._results.clear()
