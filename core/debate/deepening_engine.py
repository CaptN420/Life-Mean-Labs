"""Experiment Deepening Engine — proposes and manages follow-up investigations.

For each experience, determines:
- Which hypotheses remain open
- Which evidence is insufficient
- Which contradictions are unresolved
- What new verifications would be useful
- What similar experiences exist
- Estimated cost vs information gain

Proposes actions without auto-executing them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.deepening_engine")


# ── Enums ────────────────────────────────────────────────────────────────────


class DeepeningAction(str, Enum):
    """Recommended action for deepening an investigation."""
    REPLAY_EXISTING_EXPERIENCE = "REPLAY_EXISTING_EXPERIENCE"
    VERIFY_EXISTING_EVIDENCE = "VERIFY_EXISTING_EVIDENCE"
    COMPARE_RELATED_EXPERIENCES = "COMPARE_RELATED_EXPERIENCES"
    INVESTIGATE_CONTRADICTION = "INVESTIGATE_CONTRADICTION"
    REQUEST_ADDITIONAL_EVIDENCE = "REQUEST_ADDITIONAL_EVIDENCE"
    CREATE_FOLLOWUP_EXPERIMENT = "CREATE_FOLLOWUP_EXPERIMENT"
    STOP_NO_INFORMATION_GAIN = "STOP_NO_INFORMATION_GAIN"


class InformationGain(str, Enum):
    """Expected information gain from an action."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class DeepeningRecommendation:
    """A recommendation for how to deepen an investigation."""

    action: DeepeningAction
    priority: int  # 1 = highest priority
    rationale: str
    estimated_cost: str  # "low", "medium", "high"
    expected_gain: InformationGain
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "priority": self.priority,
            "rationale": self.rationale,
            "estimated_cost": self.estimated_cost,
            "expected_gain": self.expected_gain.value,
            "metadata": self.metadata,
        }


@dataclass
class InvestigationStatus:
    """Current status of an investigation."""

    experience_id: str
    open_hypotheses: List[str] = field(default_factory=list)
    insufficient_evidence: List[str] = field(default_factory=list)
    unresolved_contradictions: List[str] = field(default_factory=list)
    recommendations: List[DeepeningRecommendation] = field(default_factory=list)
    is_stagnant: bool = False
    stagnation_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "open_hypotheses": self.open_hypotheses,
            "insufficient_evidence": self.insufficient_evidence,
            "unresolved_contradictions": self.unresolved_contradictions,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "is_stagnant": self.is_stagnant,
            "stagnation_reason": self.stagnation_reason,
        }


# ── Experiment Deepening Engine ──────────────────────────────────────────────


class ExperimentDeepeningEngine:
    """Analyzes experiences and proposes deepening actions."""

    def __init__(self, experience_registry=None):
        self._registry = experience_registry
        self._analysis_cache: Dict[str, InvestigationStatus] = {}

    def analyze_experience(
        self,
        experience_id: str,
        claims: Optional[List[Dict[str, Any]]] = None,
        evidence_ids: Optional[List[str]] = None,
        contradiction_ids: Optional[List[str]] = None,
        decision: str = "UNRESOLVED",
    ) -> InvestigationStatus:
        """Analyze an experience and determine what deepening is needed."""
        status = InvestigationStatus(experience_id=experience_id)

        # Analyze claims
        if claims:
            for claim in claims:
                if claim.get("status") == "UNVERIFIED":
                    status.open_hypotheses.append(claim.get("claim_id", ""))
                elif claim.get("status") == "PARTIAL":
                    status.open_hypotheses.append(claim.get("claim_id", ""))

        # Analyze evidence sufficiency
        if evidence_ids:
            # If no evidence, all hypotheses are open
            if len(evidence_ids) == 0:
                status.insufficient_evidence = [f"no_evidence_for_{h}" for h in status.open_hypotheses]
            else:
                # Check for evidence gaps
                for hid in status.open_hypotheses:
                    if not any(f"evidence_for_{hid}" in eid for eid in evidence_ids):
                        status.insufficient_evidence.append(f"no_evidence_for_{hid}")

        # Analyze contradictions
        if contradiction_ids:
            status.unresolved_contradictions = list(contradiction_ids)

        # Generate recommendations based on analysis
        self._generate_recommendations(status, decision, len(evidence_ids or []))

        self._analysis_cache[experience_id] = status
        return status

    def _generate_recommendations(self, status: InvestigationStatus, decision: str, evidence_count: int) -> None:
        """Generate recommendations based on the analysis."""
        priority = 1

        # If unresolved, recommend replay or new investigation
        if decision == "UNRESOLVED":
            if evidence_count == 0:
                status.recommendations.append(DeepeningRecommendation(
                    action=DeepeningAction.REQUEST_ADDITIONAL_EVIDENCE,
                    priority=priority,
                    rationale="No evidence available — need to gather data",
                    estimated_cost="high",
                    expected_gain=InformationGain.HIGH,
                ))
                priority += 1

            if status.unresolved_contradictions:
                status.recommendations.append(DeepeningRecommendation(
                    action=DeepeningAction.INVESTIGATE_CONTRADICTION,
                    priority=priority,
                    rationale=f"{len(status.unresolved_contradictions)} unresolved contradictions",
                    estimated_cost="medium",
                    expected_gain=InformationGain.HIGH,
                ))
                priority += 1

            status.recommendations.append(DeepeningRecommendation(
                action=DeepeningAction.CREATE_FOLLOWUP_EXPERIMENT,
                priority=priority,
                rationale="Original investigation did not reach a conclusion",
                estimated_cost="medium",
                expected_gain=InformationGain.MEDIUM,
            ))

        # If there are open hypotheses
        elif status.open_hypotheses:
            status.recommendations.append(DeepeningRecommendation(
                action=DeepeningAction.VERIFY_EXISTING_EVIDENCE,
                priority=priority,
                rationale=f"{len(status.open_hypotheses)} open hypotheses need verification",
                estimated_cost="low",
                expected_gain=InformationGain.MEDIUM,
            ))
            priority += 1

            status.recommendations.append(DeepeningRecommendation(
                action=DeepeningAction.CREATE_FOLLOWUP_EXPERIMENT,
                priority=priority,
                rationale="New evidence may resolve open hypotheses",
                estimated_cost="medium",
                expected_gain=InformationGain.HIGH,
            ))

        # If there are unresolved contradictions
        if status.unresolved_contradictions and not any(
            r.action == DeepeningAction.INVESTIGATE_CONTRADICTION for r in status.recommendations
        ):
            status.recommendations.append(DeepeningRecommendation(
                action=DeepeningAction.INVESTIGATE_CONTRADICTION,
                priority=priority,
                rationale="Unresolved contradictions need investigation",
                estimated_cost="medium",
                expected_gain=InformationGain.HIGH,
            ))

        # If no recommendations and everything looks resolved
        if not status.recommendations:
            status.recommendations.append(DeepeningRecommendation(
                action=DeepeningAction.STOP_NO_INFORMATION_GAIN,
                priority=1,
                rationale="All hypotheses verified, no contradictions unresolved",
                estimated_cost="none",
                expected_gain=InformationGain.NONE,
            ))

    def check_stagnation(self, experience_id: str) -> bool:
        """Check if an investigation has stagnated."""
        status = self._analysis_cache.get(experience_id)
        if not status:
            return False

        # Stagnation indicators
        if len(status.recommendations) == 0:
            status.is_stagnant = True
            status.stagnation_reason = "No recommendations generated"
            return True

        last_rec = status.recommendations[-1] if status.recommendations else None
        if last_rec and last_rec.action == DeepeningAction.STOP_NO_INFORMATION_GAIN:
            status.is_stagnant = True
            status.stagnation_reason = "No information gain expected"
            return True

        return False

    def get_recommendations(self, experience_id: str) -> List[DeepeningRecommendation]:
        """Get recommendations for an experience."""
        status = self._analysis_cache.get(experience_id)
        if not status:
            return []
        return status.recommendations

    def compare_experiences(
        self,
        exp1_id: str,
        exp2_id: str,
    ) -> Dict[str, Any]:
        """Compare two experiences and identify differences."""
        # This would typically query the registry
        # For now, return a template structure
        return {
            "experience_1": exp1_id,
            "experience_2": exp2_id,
            "common_hypotheses": [],
            "divergent_conclusions": [],
            "evidence_overlap": 0.0,
            "recommendation": "COMPARE_RELATED_EXPERIENCES",
        }
