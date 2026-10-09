"""Adaptive curriculum controller.

Steers task generation toward measured weaknesses, while protecting against
feedback loops (design doc §18, §40).

Key protections (§18.2):
- Weakness signals originate from held-out evaluation, not the generator's own
  tasks.
- Generation rate per domain is capped to prevent runaway.
- Curriculum adjustments require explicit approval (human-review gate) before
  being applied to a production run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from analysis.weakness_analyzer import WeaknessAnalyzer, WeaknessProfile
from experiments.generation.schemas import GeneratedTask

logger = logging.getLogger("CurriculumController")

VALID_DOMAINS = {"math", "physics", "chemistry", "coding", "logic"}


@dataclass
class GenerationWeights:
    """Per-domain generation weights derived from a weakness profile.

    Weak domains get higher weight (target more generation there), but capped
    so no single domain can dominate.
    """

    weights: Dict[str, float] = field(default_factory=dict)
    source: str = "uniform"  # uniform, weakness_driven
    approved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weights": dict(self.weights),
            "source": self.source,
            "approved": self.approved,
        }

    @classmethod
    def uniform(cls, domains: List[str]) -> "GenerationWeights":
        """Uniform weights across all domains (baseline, no targeting)."""
        weights = {d: 1.0 / len(domains) for d in domains} if domains else {}
        return cls(weights=weights, source="uniform")


@dataclass
class CurriculumAction:
    """A planned curriculum adjustment awaiting approval."""

    domain: str
    reason: str
    current_accuracy: float
    new_weight: float
    budget_allocated: int
    approved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "reason": self.reason,
            "current_accuracy": self.current_accuracy,
            "new_weight": self.new_weight,
            "budget_allocated": self.budget_allocated,
            "approved": self.approved,
        }


class CurriculumController:
    """Generate targeted tasks based on measured weaknesses.

    Flow:
        1. analyze_weaknesses(held_out_results) -> WeaknessProfile
        2. plan_generation(profile) -> GenerationWeights (unapproved)
        3. approve() -> weights become active
        4. generate_targeted_tasks(weights) -> tasks biased to weak domains
    """

    def __init__(
        self,
        task_generator: Optional[Any] = None,
        seed: int = 42,
        accuracy_threshold: float = 0.7,
        max_rate_per_domain: float = 0.5,
        approval_required: bool = True,
    ):
        """Initialize the curriculum controller.

        Args:
            task_generator: TaskGenerator instance (created if None)
            seed: Random seed for reproducibility
            accuracy_threshold: Accuracy below this marks a domain weak
            max_rate_per_domain: Max fraction of generation budget per domain
            approval_required: Require explicit approve() before applying weights
        """
        if task_generator is None:
            from experiments.generation.task_generator import TaskGenerator

            task_generator = TaskGenerator(seed=seed)
        self.generator = task_generator
        self.analyzer = WeaknessAnalyzer(accuracy_threshold=accuracy_threshold)
        self._threshold = accuracy_threshold
        self._max_rate = max_rate_per_domain
        self._approval_required = approval_required
        self._active_weights: Optional[GenerationWeights] = None
        self._pending: List[CurriculumAction] = []
        self._generation_caps: Dict[str, int] = {}
        self._seed = seed

    # ---- Step 1: analyze --------------------------------------------------

    def analyze_weaknesses(self, results: List[Any]) -> WeaknessProfile:
        """Analyze held-out benchmark results for weaknesses.

        IMPORTANT (§18.2): feed held-out evaluation results here, NOT the
        generator's own synthetic tasks, to avoid self-confirming feedback.

        Args:
            results: List of ExperimentResult from held-out evaluation

        Returns:
            WeaknessProfile
        """
        self.analyzer.clear()
        self.analyzer.add_results(results)
        return self.analyzer.analyze()

    # ---- Step 2: plan -----------------------------------------------------

    def plan_generation(self, profile: WeaknessProfile) -> GenerationWeights:
        """Compute generation weights from a weakness profile.

        Weak domains receive higher weight, capped by max_rate_per_domain.
        Returned weights are NOT active until approved.

        Args:
            profile: WeaknessProfile from analyze_weaknesses

        Returns:
            GenerationWeights with source="weakness_driven"
        """
        domains = sorted(VALID_DOMAINS)
        if profile.total_tasks == 0:
            weights = GenerationWeights.uniform(domains)
            logger.info("No weakness data; using uniform weights")
            return weights

        accuracy = {d: profile.by_domain[d]["accuracy"] for d in domains if d in profile.by_domain}
        # Domains with no data get a neutral accuracy (assume average).
        avg = profile.overall_accuracy
        for d in domains:
            accuracy.setdefault(d, avg)

        # Inverse accuracy -> weak (low accuracy) gets high score.
        raw: Dict[str, float] = {}
        for d in domains:
            raw[d] = 1.0 - accuracy[d] + 1e-6  # avoid zero weights

        total_raw = sum(raw.values())
        candidate = {d: raw[d] / total_raw for d in domains}

        # Cap to prevent runaway on one domain.
        capped = self._apply_caps(candidate)

        self._active_weights = GenerationWeights(
            weights=capped,
            source="weakness_driven",
            approved=not self._approval_required,
        )
        self._build_pending_actions(profile, capped)
        logger.info(
            "Planned weakness-driven weights (approved=%s): %s",
            self._active_weights.approved,
            {k: round(v, 3) for k, v in capped.items()},
        )
        return self._active_weights

    def _apply_caps(self, candidate: Dict[str, float]) -> Dict[str, float]:
        """Clamp per-domain weights to max_rate_per_domain, re-normalize."""
        capped = dict(candidate)
        # Iteratively shave domains above the cap and redistribute (simple pass).
        changed = True
        while changed:
            changed = False
            over = [d for d, w in capped.items() if w > self._max_rate]
            if not over:
                break
            surplus = sum(capped[d] - self._max_rate for d in over)
            for d in over:
                capped[d] = self._max_rate
            # Redistribute surplus to domains under the cap.
            under = [d for d, w in capped.items() if w < self._max_rate]
            if under:
                share = surplus / len(under)
                for d in under:
                    capped[d] += share
                    changed = True
        # Final renormalize.
        total = sum(capped.values())
        if total > 0:
            capped = {d: w / total for d, w in capped.items()}
        return capped

    def _build_pending_actions(
        self, profile: WeaknessProfile, weights: Dict[str, float]
    ) -> None:
        """Build a pending action list for review/approval."""
        self._pending = []
        weak_domains = profile.weak_domains
        for d in VALID_DOMAINS:
            if d not in profile.by_domain:
                continue
            acc = profile.by_domain[d]["accuracy"]
            reasons = []
            if d in weak_domains:
                reasons.append(f"accuracy {acc:.0%} below threshold {self._threshold:.0%}")
            # Prioritize domains that flipped from weak baseline most.
            self._pending.append(
                CurriculumAction(
                    domain=d,
                    reason="; ".join(reasons) or "not flagged weak",
                    current_accuracy=acc,
                    new_weight=weights[d],
                    budget_allocated=0,
                )
            )
        self._pending.sort(key=lambda a: a.current_accuracy)  # weakest first

    # ---- Step 3: approve ---------------------------------------------------

    def approve(self) -> GenerationWeights:
        """Approve pending curriculum adjustments.

        Returns:
            The active (approved) generation weights
        """
        if self._active_weights is None:
            raise ValueError("No pending plan; call plan_generation first")
        self._active_weights.approved = True
        for action in self._pending:
            action.approved = True
        logger.info("Curriculum plan approved")
        return self._active_weights

    @property
    def pending_actions(self) -> List[CurriculumAction]:
        """List of planned adjustments awaiting approval."""
        return list(self._pending)

    # ---- Step 4: generate ---------------------------------------------------

    def generate_targeted_tasks(
        self,
        weights: Optional[GenerationWeights] = None,
        count: int = 100,
        difficulty_range: tuple = (1, 5),
    ) -> List[GeneratedTask]:
        """Generate tasks biased toward weak domains.

        Args:
            weights: Approved weights; defaults to active weights
            count: Total number of tasks to generate
            difficulty_range: Difficulty range for tasks

        Returns:
            List of GeneratedTask, distributed by domain weight

        Raises:
            ValueError: if weights are required but not approved
        """
        w = weights or self._active_weights
        if w is None:
            # No plan yet -> fall back to uniform.
            w = GenerationWeights.uniform(sorted(VALID_DOMAINS))
        if self._approval_required and not w.approved:
            # Don't hard-error; log a warning and raise to keep the gate explicit.
            raise ValueError(
                "GenerationWeights are not approved. Call approve() first "
                "(human-review gate, design doc §18.2)."
            )

        # Distribute count across domains by weight.
        tasks: List[GeneratedTask] = []
        min_diff, max_diff = difficulty_range
        for domain, weight in w.weights.items():
            n = int(round(count * weight))
            if n <= 0:
                continue
            # Respect the generation cap per domain.
            cap = self._generation_caps.get(domain)
            if cap is not None:
                n = min(n, cap)
            for _ in range(n):
                difficulty = self.generator._rng.randint(min_diff, max_diff)
                tasks.append(
                    self.generator.generate(
                        domain=domain,
                        difficulty=difficulty,
                    )
                )
        return tasks

    # ---- Protection helpers ------------------------------------------------

    def set_domain_cap(self, domain: str, max_tasks: int) -> None:
        """Cap how many tasks may be generated for a domain (§18.2)."""
        self._generation_caps[domain] = max_tasks

    @property
    def active_weights(self) -> Optional[GenerationWeights]:
        """Currently active generation weights."""
        return self._active_weights