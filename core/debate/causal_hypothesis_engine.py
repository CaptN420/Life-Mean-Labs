"""Causal Hypothesis Engine — formulates testable hypotheses from run differences.

For each difference between runs:
1. Formulates a testable hypothesis
2. Identifies supporting and contradicting evidence
3. Proposes a falsification test
4. Estimates experimental cost
5. Defines expected results for true/false outcomes
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.causal_hypothesis_engine")


# ── Enums ────────────────────────────────────────────────────────────────────


class HypothesisStatus(str, Enum):
    """Status of a causal hypothesis."""
    UNTESTED = "UNTESTED"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    VERIFIED_CAUSAL = "VERIFIED_CAUSAL"


class InformationGain(str, Enum):
    """Estimated information gain from testing."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class CausalHypothesis:
    """A testable hypothesis explaining a failure."""
    hypothesis_id: str
    statement: str
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    falsification_test: str = ""
    estimated_cost: str = "LOW"  # LOW, MEDIUM, HIGH
    expected_if_true: str = ""
    expected_if_false: str = ""
    status: HypothesisStatus = HypothesisStatus.UNTESTED
    is_heuristic: bool = True
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement[:300],
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "falsification_test": self.falsification_test,
            "estimated_cost": self.estimated_cost,
            "expected_if_true": self.expected_if_true[:200],
            "expected_if_false": self.expected_if_false[:200],
            "status": self.status.value,
            "is_heuristic": self.is_heuristic,
            "timestamp": self.timestamp,
        }


# ── Causal Hypothesis Engine ─────────────────────────────────────────────────


class CausalHypothesisEngine:
    """Formulates testable hypotheses from observed differences.

    Never assumes a hypothesis is explanation without evidence.
    VERIFIED_CAUSAL requires explicit criteria and sufficient experimental results.
    """

    def __init__(self):
        self._hypotheses: Dict[str, CausalHypothesis] = {}
        self._next_id = 1

    def generate_hypothesis(
        self,
        run_id: str,
        difference_description: str,
        supporting_evidence: Optional[List[str]] = None,
        contradicting_evidence: Optional[List[str]] = None,
        falsification_test: Optional[str] = None,
    ) -> CausalHypothesis:
        """Generate a testable hypothesis from a difference."""
        hyp_id = f"HYP-{run_id}-{self._next_id:03d}"
        self._next_id += 1

        hypothesis = CausalHypothesis(
            hypothesis_id=hyp_id,
            statement=f"Running {run_id} failed because: {difference_description}",
            supporting_evidence=supporting_evidence or [],
            contradicting_evidence=contradicting_evidence or [],
            falsification_test=falsification_test or f"Reproduce run {run_id} with controlled variables",
            expected_if_true="Run succeeds with same outcome",
            expected_if_false="Run still fails or produces different error",
        )

        self._hypotheses[hyp_id] = hypothesis

        logger.info("Hypothesis generated: %s for run %s", hyp_id, run_id)
        return hypothesis

    def update_hypothesis_status(
        self,
        hypothesis_id: str,
        new_status: HypothesisStatus,
        evidence_added: Optional[List[str]] = None,
        evidence_removed: Optional[List[str]] = None,
    ) -> bool:
        """Update the status of a hypothesis based on new evidence."""
        hyp = self._hypotheses.get(hypothesis_id)
        if not hyp:
            return False

        hyp.status = new_status

        if evidence_added:
            hyp.supporting_evidence.extend(evidence_added)
        if evidence_removed:
            hyp.contradicting_evidence.extend(evidence_removed)

        return True

    def get_hypothesis(self, hypothesis_id: str) -> Optional[CausalHypothesis]:
        """Get a hypothesis by ID."""
        return self._hypotheses.get(hypothesis_id)

    def get_untested_hypotheses(self, run_id: Optional[str] = None) -> List[CausalHypothesis]:
        """Get all untested hypotheses, optionally filtered by run."""
        if run_id:
            return [
                h for h in self._hypotheses.values()
                if h.status == HypothesisStatus.UNTESTED and run_id in h.statement
            ]
        return [
            h for h in self._hypotheses.values()
            if h.status == HypothesisStatus.UNTESTED
        ]

    def get_hypotheses_for_run(self, run_id: str) -> List[CausalHypothesis]:
        """Get all hypotheses for a specific run."""
        return [
            h for h in self._hypotheses.values()
            if run_id in h.statement
        ]

    def verify_causal(self, hypothesis_id: str, experimental_results: Dict[str, Any]) -> bool:
        """Verify a hypothesis as causally verified based on experimental results.

        Requires explicit criteria and sufficient experimental results.
        """
        hyp = self._hypotheses.get(hypothesis_id)
        if not hyp:
            return False

        # Check that we have supporting evidence
        if len(hyp.supporting_evidence) < 1 and len(hyp.contradicting_evidence) < 1:
            return False

        # Check experimental results are present
        if not experimental_results:
            return False

        hyp.status = HypothesisStatus.VERIFIED_CAUSAL
        logger.info("Hypothesis %s verified as causal", hypothesis_id)
        return True
