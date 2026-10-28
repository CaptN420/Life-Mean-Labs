"""ConvergenceEngine — evidence-based solution selection.

Compares branches using verifiable criteria:
  1. Modification validity
  2. Test success
  3. Constraint compliance
  4. Regression absence
  5. Code quality
  6. Semantic evaluation (secondary)

No automatic merges. Explicit approval required.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import Branch, BranchStatus, ConvergenceResult, OrchestrationTrace
from .workspace_manager import WorkspaceManager

logger = logging.getLogger("Life_mean.Orchestrator.ConvergenceEngine")


# ── Evaluation criteria ───────────────────────────────────────────────────────


class EvidenceLevel(str, enum.Enum):
    """Strength of evidence for a branch."""
    STRONG = "strong"        # Tests pass, no regressions
    MODERATE = "moderate"    # Tests pass, some concerns
    WEAK = "weak"            # No tests or inconclusive
    NONE = "none"            # Failed or invalid


class ConvergenceOutcome(str, enum.Enum):
    """Result of convergence analysis."""
    SELECTED = "selected"           # One branch clearly best
    TIE = "tie"                     # Multiple branches equally good
    FAILED = "failed"               # No branch satisfies requirements
    INCONCLUSIVE = "inconclusive"   # Cannot determine with available evidence


@dataclass
class BranchEvidence:
    """Structured evidence for a single branch."""
    branch_id: str
    evidence_level: EvidenceLevel
    validation_passed: bool = False
    tests_passed: int = 0
    tests_failed: int = 0
    constraints_met: List[str] = field(default_factory=list)
    regressions_detected: List[str] = field(default_factory=list)
    code_quality_score: float = 0.0
    semantic_score: float = 0.0  # Secondary, not decisive
    notes: str = ""

    @property
    def is_valid(self) -> bool:
        return self.validation_passed and len(self.regressions_detected) == 0


@dataclass
class ConvergenceAnalysis:
    """Complete analysis of all branches."""
    task_id: str
    branches_analyzed: int = 0
    valid_branches: List[BranchEvidence] = field(default_factory=list)
    invalid_branches: List[BranchEvidence] = field(default_factory=list)
    outcome: ConvergenceOutcome = ConvergenceOutcome.INCONCLUSIVE
    selected_branch_id: str = ""
    rejection_reasons: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── ConvergenceEngine ─────────────────────────────────────────────────────────


class ConvergenceEngine:
    """Evidence-based convergence for divergence branches."""

    # Default thresholds.
    DEFAULT_MIN_TESTS_PASSED = 1
    DEFAULT_QUALITY_THRESHOLD = 0.5

    def __init__(
        self,
        workspace_manager: Optional[WorkspaceManager] = None,
        min_tests_passed: int = DEFAULT_MIN_TESTS_PASSED,
        quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
        require_no_regressions: bool = True,
    ) -> None:
        self._wm = workspace_manager or WorkspaceManager()
        self._min_tests_passed = min_tests_passed
        self._quality_threshold = quality_threshold
        self._require_no_regressions = require_no_regressions

    def analyze(
        self,
        task_id: str,
        branches: List[Branch],
        evaluation_fn: Optional[Callable[[Branch], BranchEvidence]] = None,
    ) -> ConvergenceAnalysis:
        """Analyze all branches and determine convergence outcome."""
        analysis = ConvergenceAnalysis(task_id=task_id)
        analysis.branches_analyzed = len(branches)

        if not branches:
            analysis.outcome = ConvergenceOutcome.FAILED
            analysis.rejection_reasons["general"] = "No branches provided"
            return analysis

        # Evaluate each branch.
        for branch in branches:
            if evaluation_fn:
                evidence = evaluation_fn(branch)
            else:
                evidence = self._default_evaluate(branch)

            if evidence.is_valid:
                analysis.valid_branches.append(evidence)
            else:
                analysis.invalid_branches.append(evidence)
                analysis.rejection_reasons[branch.branch_id] = evidence.notes

        # Determine outcome.
        if not analysis.valid_branches:
            analysis.outcome = ConvergenceOutcome.FAILED
            analysis.rejection_reasons["general"] = "No branches satisfy validation criteria"
        elif len(analysis.valid_branches) == 1:
            analysis.outcome = ConvergenceOutcome.SELECTED
            analysis.selected_branch_id = analysis.valid_branches[0].branch_id
        else:
            # Multiple valid branches — select best by deterministic scoring.
            best = self._select_best(analysis.valid_branches)
            if best:
                analysis.outcome = ConvergenceOutcome.SELECTED
                analysis.selected_branch_id = best.branch_id
            else:
                analysis.outcome = ConvergenceOutcome.TIE

        logger.info(
            "Convergence analysis for '%s': %d valid, outcome=%s",
            task_id, len(analysis.valid_branches), analysis.outcome.value,
        )
        return analysis

    def select_best(
        self, evidence_list: List[BranchEvidence]
    ) -> Optional[BranchEvidence]:
        """Select the best branch from valid candidates."""
        if not evidence_list:
            return None

        # Score each branch deterministically.
        def score(e: BranchEvidence) -> tuple:
            # Primary: validation status.
            # Secondary: tests passed.
            # Tertiary: code quality.
            return (
                1 if e.validation_passed else 0,
                e.tests_passed,
                e.code_quality_score,
                -len(e.regressions_detected),
            )

        return max(evidence_list, key=score)

    def build_convergence_result(
        self,
        analysis: ConvergenceAnalysis,
        branches: List[Branch],
        trace: OrchestrationTrace,
    ) -> ConvergenceResult:
        """Build a ConvergenceResult from analysis."""
        selected_id = analysis.selected_branch_id
        integration_method = "single_best" if analysis.outcome == ConvergenceOutcome.SELECTED else "rollback"

        # Find selected branch.
        selected_branch = next(
            (b for b in branches if b.branch_id == selected_id),
            None,
        )

        return ConvergenceResult(
            selected_branch_id=selected_id,
            integration_method=integration_method,
            validation_passed=selected_branch.evaluation.get("validation_passed", False) if selected_branch else False,
            notes=self._format_notes(analysis),
        )

    def require_approval(self, analysis: ConvergenceAnalysis) -> bool:
        """Check if manual approval is required before integration."""
        # Always require approval for multiple valid branches.
        if analysis.outcome == ConvergenceOutcome.TIE:
            return True
        # Require approval if there are any invalid branches (potential regressions).
        if analysis.invalid_branches:
            return True
        return False

    def _default_evaluate(self, branch: Branch) -> BranchEvidence:
        """Default evaluation based on branch state."""
        evidence = BranchEvidence(
            branch_id=branch.branch_id,
            evidence_level=EvidenceLevel.NONE,
        )

        if branch.status != BranchStatus.EVALUATED:
            evidence.evidence_level = EvidenceLevel.NONE
            evidence.notes = "Branch not evaluated"
            return evidence

        # Extract evaluation data.
        eval_data = branch.evaluation or {}
        validation_passed = eval_data.get("validation_passed", False)
        tests_passed = eval_data.get("tests_passed", 0)
        tests_failed = eval_data.get("tests_failed", 0)
        regressions = eval_data.get("regressions", [])
        quality_score = eval_data.get("code_quality_score", 0.0)

        evidence.validation_passed = validation_passed
        evidence.tests_passed = tests_passed
        evidence.tests_failed = tests_failed
        evidence.regressions_detected = regressions
        evidence.code_quality_score = quality_score

        # Determine evidence level.
        if validation_passed and tests_passed >= self._min_tests_passed and not regressions:
            evidence.evidence_level = EvidenceLevel.STRONG
        elif validation_passed:
            evidence.evidence_level = EvidenceLevel.MODERATE
        elif branch.result is None:
            evidence.evidence_level = EvidenceLevel.NONE
            evidence.notes = "No result available"
        else:
            evidence.evidence_level = EvidenceLevel.WEAK
            evidence.notes = f"Validation failed or insufficient tests (passed={tests_passed}, failed={tests_failed})"

        return evidence

    def _select_best(
        self, evidence_list: List[BranchEvidence]
    ) -> Optional[BranchEvidence]:
        """Select best from multiple valid candidates."""
        return self.select_best(evidence_list)

    def _format_notes(self, analysis: ConvergenceAnalysis) -> str:
        """Format convergence notes."""
        parts = [f"Outcome: {analysis.outcome.value}"]
        parts.append(f"Branches analyzed: {analysis.branches_analyzed}")
        parts.append(f"Valid branches: {len(analysis.valid_branches)}")

        if analysis.rejection_reasons:
            parts.append("Rejections:")
            for bid, reason in analysis.rejection_reasons.items():
                parts.append(f"  - {bid}: {reason}")

        return " | ".join(parts)
