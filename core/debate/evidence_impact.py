"""Evidence Impact Analyzer — trace consequences of evidence changes.

Extends ProvenanceGraph to analyze what happens when evidence is:
- Modified
- Refuted
- Invalidated
- Removed

Detects dependency cycles and prevents artificial inflation of evidence strength.

Smart Triggers:
When new evidence arrives, analyzes which past experiences would be affected
and emits EXPERIENCE_REINVESTIGATION_SUGGESTED events (awaiting authorization).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("core.debate.evidence_impact")


# ── Enums ────────────────────────────────────────────────────────────────────


class ImpactSeverity(str, Enum):
    """Severity of evidence impact."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceChangeType(str, Enum):
    """Type of change to evidence."""
    INVALIDATED = "INVALIDATED"
    REFUTED = "REFUTED"
    MODIFIED = "MODIFIED"
    REMOVED = "REMOVED"
    ADDED = "ADDED"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ImpactResult:
    """Result of an evidence impact analysis."""

    evidence_id: str
    change_type: EvidenceChangeType
    severity: ImpactSeverity
    affected_claims: List[str] = field(default_factory=list)
    affected_conclusions: List[str] = field(default_factory=list)
    downstream_dependencies: List[str] = field(default_factory=list)
    transitive_effects: List[str] = field(default_factory=list)
    revalidation_required: bool = False
    cycle_detected: bool = False
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "affected_claims": self.affected_claims,
            "affected_conclusions": self.affected_conclusions,
            "downstream_dependencies": self.downstream_dependencies,
            "transitive_effects": self.transitive_effects,
            "revalidation_required": self.revalidation_required,
            "cycle_detected": self.cycle_detected,
            "description": self.description,
        }


# ── Evidence Impact Analyzer ─────────────────────────────────────────────────


class EvidenceImpactAnalyzer:
    """Analyzes the impact of evidence changes on the provenance graph.

    When evidence is invalidated or refuted, traces through dependencies
    to identify all affected claims and conclusions.
    """

    def __init__(self):
        self._impact_history: List[Dict[str, Any]] = []

    def analyze_evidence_impact(
        self,
        evidence_id: str,
        provenance_graph,  # ProvenanceGraph instance
        change_type: EvidenceChangeType = EvidenceChangeType.INVALIDATED,
    ) -> ImpactResult:
        """Analyze the impact of changing an evidence item."""
        result = ImpactResult(
            evidence_id=evidence_id,
            change_type=change_type,
            severity=ImpactSeverity.NONE,
        )

        # Check if evidence exists
        if not provenance_graph.get_evidence_chain(evidence_id):
            result.description = f"Evidence {evidence_id} not found in graph"
            return result

        # Get the evidence record to understand its relationships
        chain = provenance_graph.get_evidence_chain(evidence_id)

        # Collect directly affected claims
        result.affected_claims = list(chain.get("supports_claims", []))

        # Collect downstream dependencies (evidence that depends on this one)
        result.downstream_dependencies = self.get_downstream_dependencies(
            evidence_id, provenance_graph
        )

        # Check for cycles
        result.cycle_detected = self.detect_dependency_cycles(provenance_graph)

        # Trace transitive effects
        if result.downstream_dependencies:
            result.transitive_effects = self._trace_transitive_effects(
                evidence_id, provenance_graph
            )

        # Calculate severity
        total_affected = len(result.affected_claims) + len(result.downstream_dependencies)
        if result.cycle_detected:
            result.severity = ImpactSeverity.CRITICAL
            result.description = f"Circular dependency detected involving {evidence_id}"
        elif total_affected >= 5:
            result.severity = ImpactSeverity.HIGH
            result.description = f"High impact: {total_affected} items affected"
        elif total_affected >= 2:
            result.severity = ImpactSeverity.MEDIUM
            result.description = f"Medium impact: {total_affected} items affected"
        elif total_affected > 0:
            result.severity = ImpactSeverity.LOW
            result.description = f"Low impact: {total_affected} items affected"
        else:
            result.severity = ImpactSeverity.NONE
            result.description = "No downstream dependencies found"

        # Determine if revalidation is needed
        result.revalidation_required = (
            result.severity in (ImpactSeverity.HIGH, ImpactSeverity.CRITICAL) or
            result.cycle_detected
        )

        # Log the impact
        self._impact_history.append(result.to_dict())

        logger.info(
            "Impact analysis for %s: severity=%s, affected_claims=%d, downstream=%d",
            evidence_id, result.severity.value, len(result.affected_claims),
            len(result.downstream_dependencies),
        )

        return result

    def get_downstream_dependencies(self, evidence_id: str, provenance_graph) -> List[str]:
        """Get all evidence that directly depends on the given evidence."""
        deps = []
        for eid, record in provenance_graph._evidence.items():
            if evidence_id in record.depends_on and eid != evidence_id:
                deps.append(eid)
        return deps

    def detect_dependency_cycles(self, provenance_graph) -> bool:
        """Detect circular dependencies in the evidence graph."""
        visited = set()
        rec_stack = set()

        def dfs(eid: str) -> bool:
            visited.add(eid)
            rec_stack.add(eid)

            record = provenance_graph._evidence.get(eid)
            if record:
                for dep in record.depends_on:
                    if dep not in visited:
                        if dfs(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(eid)
            return False

        for eid in provenance_graph._evidence:
            if eid not in visited:
                if dfs(eid):
                    return True

        return False

    def get_independent_sources(self, claim_id: str, provenance_graph) -> List[str]:
        """Get evidence sources that are independent (not dependent on each other)."""
        supporting = []
        for eid, record in provenance_graph._evidence.items():
            if claim_id in record.supports_claims or record.claim_id == claim_id:
                supporting.append(eid)

        # Filter out evidence that depends on other supporting evidence
        independent = []
        for eid in supporting:
            record = provenance_graph._evidence.get(eid)
            if record and not any(dep in supporting for dep in record.depends_on):
                independent.append(eid)

        return independent

    def get_affected_conclusions(self, evidence_id: str, provenance_graph) -> List[str]:
        """Get all conclusions affected by an evidence change."""
        conclusions = []

        # Get the evidence record
        record = provenance_graph._evidence.get(evidence_id)
        if not record:
            return conclusions

        # Collect direct conclusions
        conclusions.extend(record.conclusions)

        # Trace through downstream dependencies
        for dep_id in self.get_downstream_dependencies(evidence_id, provenance_graph):
            dep_record = provenance_graph._evidence.get(dep_id)
            if dep_record:
                conclusions.extend(dep_record.conclusions)

        return list(set(conclusions))

    def _trace_transitive_effects(self, evidence_id: str, provenance_graph) -> List[str]:
        """Trace all transitive effects of an evidence change."""
        visited = set()
        effects = []

        def traverse(eid: str) -> None:
            if eid in visited:
                return
            visited.add(eid)

            record = provenance_graph._evidence.get(eid)
            if not record:
                return

            # Add conclusions from this evidence
            effects.extend(record.conclusions)

            # Recurse through dependents
            for dep_id in self.get_downstream_dependencies(eid, provenance_graph):
                traverse(dep_id)

        traverse(evidence_id)
        return list(set(effects))

    def get_impact_history(self) -> List[Dict[str, Any]]:
        """Get the history of impact analyses."""
        return list(self._impact_history)

    def clear_history(self) -> int:
        """Clear impact analysis history. Returns count cleared."""
        count = len(self._impact_history)
        self._impact_history.clear()
        return count


# ── Smart Investigation Triggers ─────────────────────────────────────────────


class ReinvestigationStatus(str, Enum):
    """Status of a reinvestigation request."""
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


@dataclass
class ReinvestigationRequest:
    """Request to reinvestigate past experiences based on new evidence."""

    request_id: str
    timestamp: float
    new_evidence_id: str
    affected_experience_ids: List[str]
    severity: ImpactSeverity
    reason: str
    status: ReinvestigationStatus = ReinvestigationStatus.PENDING
    authorized_by: Optional[str] = None
    authorization_timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "new_evidence_id": self.new_evidence_id,
            "affected_experience_ids": self.affected_experience_ids,
            "severity": self.severity.value,
            "reason": self.reason,
            "status": self.status.value,
            "authorized_by": self.authorized_by,
            "authorization_timestamp": self.authorization_timestamp,
        }


class InvestigationTrigger:
    """Smart trigger for investigation suggestions.

    When new evidence arrives, analyzes which past experiences would be affected
    and emits EXPERIENCE_REINVESTIGATION_SUGGESTED events.

    Waits for authorization before launching any investigation.
    Does NOT auto-execute follow-up experiments.
    """

    def __init__(self):
        self._pending_requests: Dict[str, ReinvestigationRequest] = {}
        self._authorization_log: List[Dict[str, Any]] = []

    def check_reinvestigation_needed(
        self,
        new_evidence_id: str,
        new_evidence_content: str,
        registry,  # ExperienceRegistry instance
        analyzer: EvidenceImpactAnalyzer,
        provenance_graph,
    ) -> Optional[ReinvestigationRequest]:
        """Check if new evidence triggers reinvestigation of past experiences.

        Args:
            new_evidence_id: ID of the new evidence
            new_evidence_content: Content/text of the new evidence
            registry: ExperienceRegistry instance
            analyzer: EvidenceImpactAnalyzer instance
            provenance_graph: ProvenanceGraph instance

        Returns:
            ReinvestigationRequest if reinvestigation is suggested, None otherwise.
        """
        # Search for past experiences that might be affected
        affected_experiences = self._find_affected_experiences(
            new_evidence_content, registry
        )

        if not affected_experiences:
            return None

        # Analyze impact on each affected experience
        total_severity = ImpactSeverity.NONE
        for exp in affected_experiences:
            for ev_id in exp.get("evidence_ids", []):
                impact = analyzer.analyze_evidence_impact(
                    ev_id, provenance_graph, EvidenceChangeType.ADDED
                )
                if impact.severity.value > total_severity.value:
                    total_severity = impact.severity

        # Create request (PENDING - awaiting authorization)
        request_id = f"REQ-{int(time.time())}"
        request = ReinvestigationRequest(
            request_id=request_id,
            timestamp=time.time(),
            new_evidence_id=new_evidence_id,
            affected_experience_ids=[e["experience_id"] for e in affected_experiences],
            severity=total_severity,
            reason=f"New evidence '{new_evidence_id}' may affect {len(affected_experiences)} past experience(s)",
        )

        self._pending_requests[request_id] = request
        logger.info(
            "Reinvestigation request %s created: %d experiences affected, severity=%s",
            request_id, len(affected_experiences), total_severity.value,
        )

        return request

    def authorize_request(self, request_id: str, authorized_by: str) -> bool:
        """Authorize a pending reinvestigation request.

        Args:
            request_id: The request ID to authorize
            authorized_by: Who authorized it

        Returns:
            True if authorized, False if not found or already decided.
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return False

        if request.status != ReinvestigationStatus.PENDING:
            return False

        request.status = ReinvestigationStatus.AUTHORIZED
        request.authorized_by = authorized_by
        request.authorization_timestamp = time.time()

        self._authorization_log.append({
            "request_id": request_id,
            "action": "AUTHORIZED",
            "authorized_by": authorized_by,
            "timestamp": time.time(),
        })

        logger.info("Reinvestigation request %s authorized by %s", request_id, authorized_by)
        return True

    def deny_request(self, request_id: str, reason: str = "") -> bool:
        """Deny a pending reinvestigation request.

        Args:
            request_id: The request ID to deny
            reason: Reason for denial

        Returns:
            True if denied, False if not found or already decided.
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return False

        if request.status != ReinvestigationStatus.PENDING:
            return False

        request.status = ReinvestigationStatus.DENIED
        request.reason = reason

        self._authorization_log.append({
            "request_id": request_id,
            "action": "DENIED",
            "reason": reason,
            "timestamp": time.time(),
        })

        logger.info("Reinvestigation request %s denied: %s", request_id, reason)
        return True

    def get_pending_requests(self) -> List[ReinvestigationRequest]:
        """Get all pending reinvestigation requests."""
        return [
            req for req in self._pending_requests.values()
            if req.status == ReinvestigationStatus.PENDING
        ]

    def get_request(self, request_id: str) -> Optional[ReinvestigationRequest]:
        """Get a specific request by ID."""
        return self._pending_requests.get(request_id)

    def _find_affected_experiences(
        self, new_evidence_content: str, registry
    ) -> List[Dict[str, Any]]:
        """Find past experiences that might be affected by new evidence.

        Uses keyword matching on experience questions and hypotheses.
        """
        keywords = self._extract_keywords(new_evidence_content)
        if not keywords:
            return []

        all_experiences = registry.get_all()
        affected = []

        for exp in all_experiences:
            # Check question and hypotheses for keyword matches
            content_to_search = f"{exp.question} {' '.join(exp.hypotheses)}".lower()
            if any(kw in content_to_search for kw in keywords):
                affected.append(exp.to_dict())

        return affected

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract relevant keywords from evidence content."""
        # Simple keyword extraction - could be enhanced with NLP
        words = text.lower().split()
        # Filter common stop words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "being", "have", "has", "had", "do", "does", "did", "will",
                      "would", "shall", "should", "may", "might", "must", "can",
                      "could", "of", "in", "to", "for", "with", "on", "at", "by",
                      "from", "as", "into", "through", "during", "before", "after"}
        return [w for w in words if len(w) > 2 and w not in stop_words]
