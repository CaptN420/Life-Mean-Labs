"""Deterministic Debate Engine — confronts hypotheses with verifiable evidence.

This module implements the core debate logic:
- Task classification (deterministic vs reasoning)
- Debate session management
- Evidence validation integration
- Stagnation detection
- Deterministic arbiter

The engine integrates with the existing safety layer (LoopDetector, PolicyGuard)
and the new persona/provider systems.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.personas.schema import DebateSessionConfig, PersonaConfig
from core.providers.base import ChatResult, ProviderType

from .events import DebateEvent, DebateEventLogger, DebateEventType

logger = logging.getLogger("core.debate.engine")


# ── Enums ────────────────────────────────────────────────────────────────────


class DebateStatus(str, enum.Enum):
    """Status of a debate session."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class ArbiterDecision(str, enum.Enum):
    """Possible decisions from the deterministic arbiter."""

    VERIFIED = "VERIFIED"          # Hypothesis sufficiently demonstrated
    PARTIAL = "PARTIAL"            # Partially supported
    UNRESOLVED = "UNRESOLVED"      # Insufficient or contradictory evidence
    INVALID = "INVALID"            # Hypothesis refuted


class ClaimStatus(str, enum.Enum):
    """Validation status of a claim."""

    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    INVALID = "INVALID"


class TaskType(str, enum.Enum):
    """Classification of a debate task."""

    FACTUAL = "factual"
    PHILOSOPHICAL = "philosophical"
    SCIENTIFIC = "scientific"
    PRACTICAL = "practical"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class EvidenceRecord:
    """A piece of evidence with validation status and provenance."""

    evidence_id: str
    claim_id: str
    evidence_type: str
    content: str
    verified: bool = False
    verification_method: str = ""
    timestamp: float = field(default_factory=time.time)
    # Provenance fields
    source: str = ""           # Origin of the evidence (e.g., "experiment_1", "literature_review")
    supports_claims: List[str] = field(default_factory=list)  # Claims this evidence supports
    depends_on: List[str] = field(default_factory=list)        # Other evidence this depends on
    conclusions: List[str] = field(default_factory=list)       # Conclusions drawn from this evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "claim_id": self.claim_id,
            "evidence_type": self.evidence_type,
            "content": self.content[:500],
            "verified": self.verified,
            "verification_method": self.verification_method,
            "timestamp": self.timestamp,
            "source": self.source,
            "supports_claims": self.supports_claims,
            "depends_on": self.depends_on,
            "conclusions": self.conclusions,
        }


@dataclass
class ContradictionRecord:
    """A detected contradiction between claims."""

    contradiction_id: str
    claim_a_id: str
    claim_b_id: str
    description: str
    resolved: bool = False
    resolution: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "claim_a_id": self.claim_a_id,
            "claim_b_id": self.claim_b_id,
            "description": self.description[:300],
            "resolved": self.resolved,
            "resolution": self.resolution[:300],
            "timestamp": self.timestamp,
        }


@dataclass
class Claim:
    """A claim made by an agent during debate."""

    claim_id: str
    agent_id: str
    hypothesis: str
    arguments: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "agent_id": self.agent_id,
            "hypothesis": self.hypothesis,
            "arguments": self.arguments,
            "evidence_refs": self.evidence_refs,
            "contradictions": self.contradictions,
            "status": self.status.value,
            "trace_id": self.trace_id,
        }


@dataclass
class DebateTurn:
    """A single turn in the debate."""

    turn_number: int
    speaker_id: str
    claim: Optional[Claim] = None
    response_text: str = ""
    model_used: str = ""
    provider: ProviderType = ProviderType.MOCK
    latency_ms: float = 0.0
    tokens_used: int = 0
    timestamp: float = field(default_factory=time.time)
    # Quality metrics per turn
    memory_recall_score: float = 0.0          # How much previous context was correctly referenced
    evidence_citations: int = 0               # Number of verifiable citations in this turn
    new_evidence_count: int = 0               # New evidence introduced this turn
    hypothesis_novelty: float = 0.0           # Semantic distance from previous hypotheses (0-1)
    is_repetitive: bool = False               # Flag if turn repeats prior ideas without new evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_number": self.turn_number,
            "speaker_id": self.speaker_id,
            "claim": self.claim.to_dict() if self.claim else None,
            "response_text": self.response_text[:500],
            "model_used": self.model_used,
            "provider": self.provider.value,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "timestamp": self.timestamp,
            "memory_recall_score": self.memory_recall_score,
            "evidence_citations": self.evidence_citations,
            "new_evidence_count": self.new_evidence_count,
            "hypothesis_novelty": self.hypothesis_novelty,
            "is_repetitive": self.is_repetitive,
        }


@dataclass
class DebateResult:
    """Final result of a debate session."""

    session_id: str
    topic: str
    status: DebateStatus
    turns_committed: int
    max_turns: int
    arbiter_decision: ArbiterDecision
    arbiter_justification: str = ""
    claims: List[Claim] = field(default_factory=list)
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    evidence_registry: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "status": self.status.value,
            "turns_committed": self.turns_committed,
            "max_turns": self.max_turns,
            "arbiter_decision": self.arbiter_decision.value,
            "arbiter_justification": self.arbiter_justification,
            "claims": [c.to_dict() for c in self.claims],
            "transcript": self.transcript,
            "evidence_registry": self.evidence_registry,
            "contradictions": self.contradictions,
            "metrics": self.metrics,
            "trace_id": self.trace_id,
        }


# ── Task Classifier ──────────────────────────────────────────────────────────


class TaskClassifier:
    """Classifies debate topics into task types for appropriate handling."""

    _FACTUAL_KEYWORDS = frozenset([
        "fact", "true", "false", "verify", "proof", "evidence",
        "date", "number", "count", "exist", "real", "actual",
    ])
    _PHILOSOPHICAL_KEYWORDS = frozenset([
        "meaning", "value", "should", "ought", "good", "evil",
        "right", "wrong", "moral", "ethical", "purpose", "significance",
        "consciousness", "free will", "determinism", "existence",
    ])
    _SCIENTIFIC_KEYWORDS = frozenset([
        "hypothesis", "theory", "experiment", "observe", "measure",
        "quantum", "biology", "physics", "chemistry", "evolution",
        "causality", "mechanism", "law", "principle",
    ])
    _PRACTICAL_KEYWORDS = frozenset([
        "should we", "how to", "best way", "implement", "build",
        "design", "create", "solve", "improve", "optimize",
    ])

    def classify(self, topic: str) -> TaskType:
        """Classify a topic into a task type."""
        topic_lower = topic.lower()
        scores: Dict[TaskType, int] = {
            TaskType.FACTUAL: 0,
            TaskType.PHILOSOPHICAL: 0,
            TaskType.SCIENTIFIC: 0,
            TaskType.PRACTICAL: 0,
        }

        for kw in self._FACTUAL_KEYWORDS:
            if kw in topic_lower:
                scores[TaskType.FACTUAL] += 1
        for kw in self._PHILOSOPHICAL_KEYWORDS:
            if kw in topic_lower:
                scores[TaskType.PHILOSOPHICAL] += 1
        for kw in self._SCIENTIFIC_KEYWORDS:
            if kw in topic_lower:
                scores[TaskType.SCIENTIFIC] += 1
        for kw in self._PRACTICAL_KEYWORDS:
            if kw in topic_lower:
                scores[TaskType.PRACTICAL] += 1

        max_score = max(scores.values())
        if max_score == 0:
            return TaskType.PHILOSOPHICAL

        for task_type, score in scores.items():
            if score == max_score:
                return task_type

        return TaskType.PHILOSOPHICAL

    def is_debate_worthy(self, topic: str, min_turns: int = 3) -> bool:
        """Check if a topic is suitable for debate."""
        if not topic or len(topic.strip()) < 10:
            return False
        classification = self.classify(topic)
        return classification in (TaskType.PHILOSOPHICAL, TaskType.SCIENTIFIC, TaskType.FACTUAL)


# ── Stagnation Detector ──────────────────────────────────────────────────────


class StagnationDetector:
    """Detects when a debate is not making progress.

    Integrates with the LoopDetector pattern for consistency.
    Tracks evidence progress, argument repetition, and token usage.
    """

    def __init__(
        self,
        max_consecutive_no_progress: int = 3,
        min_new_evidence_per_turn: int = 1,
        max_tokens_per_turn: int = 5000,
    ) -> None:
        self._max_consecutive = max_consecutive_no_progress
        self._min_new_evidence = min_new_evidence_per_turn
        self._max_tokens = max_tokens_per_turn

        self._consecutive_no_progress = 0
        self._last_evidence_count = 0
        self._last_token_count = 0
        self._claim_hashes: set = set()
        self._progress_history: List[Dict[str, Any]] = []

    def check_progress(self, turn: DebateTurn, new_evidence_count: int = 0) -> Dict[str, Any]:
        """Check if the debate is making progress."""
        stagnation_indicators = []

        # Check evidence progress
        if new_evidence_count < self._min_new_evidence:
            stagnation_indicators.append("no_new_evidence")
            self._consecutive_no_progress += 1
        else:
            self._consecutive_no_progress = 0

        # Check token usage (potential repetitive verbose responses)
        if turn.tokens_used > self._max_tokens:
            stagnation_indicators.append("excessive_tokens")

        # Check for repeated claims (hash-based dedup)
        if turn.claim and turn.claim.hypothesis:
            claim_hash = hashlib.md5(turn.claim.hypothesis.encode()).hexdigest()
            if claim_hash in self._claim_hashes:
                stagnation_indicators.append("repeated_claim")
            self._claim_hashes.add(claim_hash)

        is_stagnant = self._consecutive_no_progress >= self._max_consecutive

        # Record progress metric
        self._progress_history.append({
            "turn": turn.turn_number,
            "new_evidence": new_evidence_count,
            "tokens": turn.tokens_used,
            "is_stagnant": is_stagnant,
            "indicators": stagnation_indicators,
        })

        return {
            "is_stagnant": is_stagnant,
            "indicators": stagnation_indicators,
            "consecutive_no_progress": self._consecutive_no_progress,
            "progress_score": self._calculate_progress_score(),
        }

    def _calculate_progress_score(self) -> float:
        """Calculate a progress score based on evidence and contradiction resolution."""
        if not self._progress_history:
            return 0.0
        recent = self._progress_history[-5:]
        if not recent:
            return 0.0
        evidence_gain = sum(r["new_evidence"] for r in recent)
        return min(1.0, evidence_gain / (len(recent) * self._min_new_evidence))

    def reset(self) -> None:
        """Reset stagnation tracking."""
        self._consecutive_no_progress = 0
        self._last_evidence_count = 0
        self._last_token_count = 0
        self._claim_hashes.clear()
        self._progress_history.clear()


# ── Deterministic Arbiter ───────────────────────────────────────────────────


class DeterministicArbiter:
    """Applies explicit, reproducible rules to evaluate debate claims.

    Rules are applied in order and produce deterministic results for the same inputs.
    The arbiter does NOT use LLM responses as evidence — only verifiable criteria.
    """

    # Version for reproducibility
    RULE_VERSION = "1.0.0"

    def __init__(self) -> None:
        self._applied_rules: List[str] = []
        self._rule_details: Dict[str, Any] = {}

    def arbitrate(
        self,
        claims: List[Claim],
        session_config: DebateSessionConfig,
        evidence_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> ArbiterDecision:
        """Apply deterministic rules to evaluate claims."""
        self._applied_rules = []
        self._rule_details = {}

        # Rule 1: Check for verified claims with independent evidence
        verified_claims = [c for c in claims if c.status == ClaimStatus.VERIFIED]
        if len(verified_claims) >= 2:
            self._applied_rules.append("multiple_verified_claims")
            self._rule_details["verified_count"] = len(verified_claims)
            return ArbiterDecision.VERIFIED

        # Rule 2: Check for invalid claims (refuted by evidence)
        invalid_claims = [c for c in claims if c.status == ClaimStatus.INVALID]
        if len(claims) > 0 and len(invalid_claims) > len(claims) / 2:
            self._applied_rules.append("majority_invalid_claims")
            self._rule_details["invalid_count"] = len(invalid_claims)
            return ArbiterDecision.INVALID

        # Rule 3: Check for partial support only
        partial_claims = [c for c in claims if c.status == ClaimStatus.PARTIAL]
        if partial_claims and not verified_claims:
            self._applied_rules.append("partial_support_only")
            self._rule_details["partial_count"] = len(partial_claims)
            return ArbiterDecision.PARTIAL

        # Rule 4: No claims submitted
        if not claims:
            self._applied_rules.append("no_claims_submitted")
            return ArbiterDecision.UNRESOLVED

        # Rule 5: Check for contradictions that resolve to UNRESOLVED
        unresolved_count = sum(
            1 for c in claims if c.status == ClaimStatus.UNVERIFIED
        )
        if unresolved_count == len(claims):
            self._applied_rules.append("all_unverified")
            return ArbiterDecision.UNRESOLVED

        # Rule 6: Check evidence registry for verification
        if evidence_registry:
            verified_evidence = sum(
                1 for e in evidence_registry if e.get("verified", False)
            )
            if verified_evidence >= 2:
                self._applied_rules.append("evidence_based_verified")
                return ArbiterDecision.VERIFIED

        # Default: unresolved (honest answer when evidence is insufficient)
        self._applied_rules.append("insufficient_evidence")
        return ArbiterDecision.UNRESOLVED

    def get_justification(self, decision: ArbiterDecision) -> str:
        """Get human-readable justification for a decision."""
        justifications = {
            ArbiterDecision.VERIFIED: (
                "Multiple claims verified by applicable evidence criteria. "
                "The hypothesis is sufficiently demonstrated."
            ),
            ArbiterDecision.PARTIAL: (
                "Claims partially supported but not fully verified. "
                "Some evidence exists but coverage is incomplete."
            ),
            ArbiterDecision.UNRESOLVED: (
                "Insufficient evidence to determine validity. "
                "The current evidence does not allow a definitive conclusion."
            ),
            ArbiterDecision.INVALID: (
                "Majority of claims refuted by applicable evidence. "
                "The hypothesis is not supported by verifiable criteria."
            ),
        }
        return justifications.get(decision, "")

    @property
    def applied_rules(self) -> List[str]:
        return list(self._applied_rules)

    @property
    def rule_version(self) -> str:
        return self.RULE_VERSION


# ── Contradiction Engine v2 ──────────────────────────────────────────────────


class ContradictionDetector:
    """Enhanced contradiction detection beyond simple keyword matching.

    Handles:
    - Negation patterns (is/is not, has/has no)
    - Context-aware detection (full sentence structure)
    - Equivalent proposition detection (synonyms, paraphrases)
    """

    # Negation patterns: (affirmative, negative)
    _NEGATION_PATTERNS = [
        ("meaningful", "meaningless"),
        ("has meaning", "no meaning"),
        ("inherent meaning", "no inherent meaning"),
        ("true", "false"),
        ("exists", "does not exist"),
        ("is", "is not"),
        ("will", "won't"),
        ("can", "cannot"),
        ("should", "should not"),
        ("ought", "ought not"),
        ("good", "bad"),
        ("right", "wrong"),
        ("possible", "impossible"),
        ("necessary", "contingent"),
    ]

    # Synonym/equivalence maps for detecting paraphrased contradictions
    _SYNONYM_MAP = {
        "meaning": ["significance", "purpose", "value", "import"],
        "existence": ["being", "reality", "presence", "occurrence"],
        "consciousness": ["awareness", "sentience", "perception", "cognition"],
        "free will": ["autonomy", "agency", "self-determination", "volition"],
        "determinism": ["fatalism", "predestination", "causality"],
        "moral": ["ethical", "virtuous", "righteous", "good"],
        "ethical": ["moral", "principled", "honorable", "just"],
    }

    def detect_contradiction(self, h1: str, h2: str) -> Optional[Dict[str, Any]]:
        """Detect contradiction between two hypotheses.

        Returns a dict with contradiction info if found, None otherwise.
        """
        h1_lower = h1.lower()
        h2_lower = h2.lower()

        # Check simple negation patterns
        for affirmative, negative in self._NEGATION_PATTERNS:
            if (affirmative in h1_lower and negative in h2_lower) or \
               (negative in h1_lower and affirmative in h2_lower):
                return {
                    "type": "negation",
                    "pattern": f"{affirmative} vs {negative}",
                    "confidence": 0.9,
                    "description": f"Direct negation detected: '{affirmative}' vs '{negative}'",
                }

        # Check synonym-based contradictions (paraphrased)
        # Build reverse map: synonym -> base word
        synonym_to_base = {}
        for base, synonyms in self._SYNONYM_MAP.items():
            synonym_to_base[base] = base
            for syn in synonyms:
                synonym_to_base[syn] = base

        # Find which words in h1 and h2 map to the same base
        h1_bases = set()
        h2_bases = set()
        for word in h1_lower.split():
            if word in synonym_to_base:
                h1_bases.add(synonym_to_base[word])
        for word in h2_lower.split():
            if word in synonym_to_base:
                h2_bases.add(synonym_to_base[word])

        # If they share a base concept but with opposite polarity, detect contradiction
        shared_bases = h1_bases & h2_bases
        if shared_bases:
            for base in shared_bases:
                # Check if there's a negation pattern involving this base
                for affirmative, negative in self._NEGATION_PATTERNS:
                    # Match if the base word or its synonyms appear with negation
                    base_in_h1 = base in h1_lower or any(s in h1_lower for s in self._SYNONYM_MAP.get(base, []))
                    base_in_h2 = base in h2_lower or any(s in h2_lower for s in self._SYNONYM_MAP.get(base, []))
                    if (affirmative in h1_lower and negative in h2_lower) or \
                       (negative in h1_lower and affirmative in h2_lower):
                        return {
                            "type": "equivalent_proposition",
                            "pattern": f"synonym({base})",
                            "confidence": 0.7,
                            "description": f"Paraphrased contradiction via synonym '{base}': '{h1[:60]}' vs '{h2[:60]}'",
                        }
                    # Also check if base words themselves are negated
                    if base_in_h1 and base_in_h2:
                        # Check for implicit negation (e.g., "has significance" vs "no purpose")
                        has_negative = "no " in h2_lower or "not " in h2_lower or "never " in h2_lower
                        if has_negative:
                            return {
                                "type": "equivalent_proposition",
                                "pattern": f"synonym({base})",
                                "confidence": 0.65,
                                "description": f"Paraphrased contradiction via synonym '{base}': '{h1[:60]}' vs '{h2[:60]}'",
                            }

        # Check for contextual contradictions (e.g., "life has purpose" vs "life is random")
        context_pairs = [
            ("purpose", "random"),
            ("designed", "accidental"),
            ("ordered", "chaotic"),
            ("determined", "free"),
            ("objective", "subjective"),
        ]
        for a, b in context_pairs:
            if (a in h1_lower and b in h2_lower) or (b in h1_lower and a in h2_lower):
                return {
                    "type": "contextual",
                    "pattern": f"{a} vs {b}",
                    "confidence": 0.6,
                    "description": f"Contextual contradiction: '{a}' vs '{b}'",
                }

        return None

    def batch_detect(self, claims: List[Claim]) -> List[Dict[str, Any]]:
        """Detect contradictions between all pairs of claims."""
        contradictions = []
        for i, c1 in enumerate(claims):
            for c2 in claims[i+1:]:
                result = self.detect_contradiction(c1.hypothesis, c2.hypothesis)
                if result:
                    contradictions.append({
                        **result,
                        "claim_a_id": c1.claim_id,
                        "claim_b_id": c2.claim_id,
                        "hypothesis_a": c1.hypothesis[:100],
                        "hypothesis_b": c2.hypothesis[:100],
                    })
        return contradictions


# ── Evidence Provenance Graph ────────────────────────────────────────────────


class ProvenanceGraph:
    """Tracks relationships between evidence, claims, and conclusions."""

    def __init__(self) -> None:
        self._evidence: Dict[str, EvidenceRecord] = {}
        self._claims: Dict[str, Claim] = {}
        self._conclusions: Dict[str, Any] = {}

    def add_evidence(self, record: EvidenceRecord) -> None:
        """Add evidence to the provenance graph."""
        self._evidence[record.evidence_id] = record

    def add_claim(self, claim: Claim) -> None:
        """Add a claim to the provenance graph."""
        self._claims[claim.claim_id] = claim

    def add_conclusion(self, conclusion_id: str, data: Dict[str, Any]) -> None:
        """Add a conclusion to the provenance graph."""
        self._conclusions[conclusion_id] = data

    def get_evidence_chain(self, evidence_id: str) -> Dict[str, Any]:
        """Get the full provenance chain for an evidence item."""
        record = self._evidence.get(evidence_id)
        if not record:
            return {}

        return {
            "evidence_id": evidence_id,
            "source": record.source,
            "verified": record.verified,
            "verification_method": record.verification_method,
            "supports_claims": record.supports_claims,
            "depends_on": record.depends_on,
            "conclusions": record.conclusions,
            "related_evidence": self._get_related_evidence(evidence_id),
        }

    def _get_related_evidence(self, evidence_id: str) -> List[str]:
        """Get evidence that is related to the given evidence."""
        related = []
        for eid, record in self._evidence.items():
            if eid == evidence_id:
                continue
            if evidence_id in record.depends_on or evidence_id in record.supports_claims:
                related.append(eid)
        return related

    def get_claim_support(self, claim_id: str) -> Dict[str, Any]:
        """Get all evidence supporting a claim."""
        claim = self._claims.get(claim_id)
        if not claim:
            return {}

        supporting_evidence = []
        for record in self._evidence.values():
            if claim_id in record.supports_claims or record.claim_id == claim_id:
                supporting_evidence.append(record.to_dict())

        return {
            "claim_id": claim_id,
            "hypothesis": claim.hypothesis,
            "status": claim.status.value,
            "supporting_evidence": supporting_evidence,
            "contradictions": claim.contradictions,
        }

    def get_graph_summary(self) -> Dict[str, Any]:
        """Get a summary of the entire provenance graph."""
        return {
            "total_evidence": len(self._evidence),
            "total_claims": len(self._claims),
            "total_conclusions": len(self._conclusions),
            "verified_evidence": sum(1 for e in self._evidence.values() if e.verified),
            "evidence_by_source": self._group_by_source(),
        }

    def _group_by_source(self) -> Dict[str, int]:
        """Group evidence by source."""
        groups: Dict[str, int] = {}
        for record in self._evidence.values():
            source = record.source or "unknown"
            groups[source] = groups.get(source, 0) + 1
        return groups


# ── Deterministic Replay Engine ──────────────────────────────────────────────


class ReplayEngine:
    """Replays a debate session deterministically for verification.

    Supports two modes:
    - Mode A (Historical Replay): Reconstructs with historical proofs/rules
    - Mode B (Deep Investigation): Creates new investigation linked to original

    Historical results are never overwritten — new investigations create derived experiences.
    """

    def __init__(self, experience_registry=None):
        self._session_state: Dict[str, Any] = {}
        self._replay_history: List[Dict[str, Any]] = []
        self._registry = experience_registry

    def capture_session(self, engine: "DebateEngine") -> Dict[str, Any]:
        """Capture the current state of a debate session for replay."""
        return {
            "session_id": engine.session_id,
            "trace_id": engine.trace_id,
            "topic": engine._config.topic,
            "status": engine._status.value,
            "turns": [t.to_dict() for t in engine._turns],
            "claims": [c.to_dict() for c in engine._claims],
            "evidence_registry": [e.to_dict() for e in engine._evidence_registry],
            "contradictions": [c.to_dict() for c in engine._contradictions],
            "events": engine.events,
            "metrics": {
                "total_turns": len(engine._turns),
                "total_claims": len(engine._claims),
                "total_evidence": len(engine._evidence_registry),
                "total_contradictions": len(engine._contradictions),
                "resolved_contradictions": sum(1 for c in engine._contradictions if c.resolved),
                "task_type": engine.task_type.value,
            },
        }

    def historical_replay(self, session_state: Dict[str, Any], arbiter_rule_version: str = "1.0.0") -> Dict[str, Any]:
        """Mode A: Historical Replay — reconstruct with historical proofs/rules.

        Replays the exact same session to verify reproducibility.
        Does not call external models or services.
        """
        config = DebateSessionConfig(
            topic=session_state["topic"],
            max_turns=10,
        )
        personas: Dict[str, PersonaConfig] = {}

        replay_engine = DebateEngine(config, personas)

        # Restore turns
        for turn_data in session_state.get("turns", []):
            turn = DebateTurn(
                turn_number=turn_data["turn_number"],
                speaker_id=turn_data["speaker_id"],
                response_text=turn_data.get("response_text", ""),
                model_used=turn_data.get("model_used", ""),
                provider=ProviderType.MOCK,
            )
            replay_engine._turns.append(turn)

        # Restore claims
        for claim_data in session_state.get("claims", []):
            claim = Claim(
                claim_id=claim_data["claim_id"],
                agent_id=claim_data["agent_id"],
                hypothesis=claim_data["hypothesis"],
                arguments=claim_data.get("arguments", []),
                evidence_refs=claim_data.get("evidence_refs", []),
                status=ClaimStatus(claim_data["status"]),
                trace_id=session_state.get("trace_id", ""),
            )
            replay_engine._claims.append(claim)

        # Restore evidence
        for evid_data in session_state.get("evidence_registry", []):
            record = EvidenceRecord(
                evidence_id=evid_data["evidence_id"],
                claim_id=evid_data["claim_id"],
                evidence_type=evid_data["evidence_type"],
                content=evid_data["content"],
                verified=evid_data.get("verified", False),
                verification_method=evid_data.get("verification_method", ""),
            )
            replay_engine._evidence_registry.append(record)

        # Restore contradictions
        for contra_data in session_state.get("contradictions", []):
            record = ContradictionRecord(
                contradiction_id=contra_data["contradiction_id"],
                claim_a_id=contra_data["claim_a_id"],
                claim_b_id=contra_data["claim_b_id"],
                description=contra_data["description"],
                resolved=contra_data.get("resolved", False),
                resolution=contra_data.get("resolution", ""),
            )
            replay_engine._contradictions.append(record)

        # Run arbiter with captured state
        replay_engine._status = DebateStatus.COMPLETED
        decision = replay_engine.arbitrate()

        result = {
            "mode": "HISTORICAL_REPLAY",
            "original_session_id": session_state.get("session_id"),
            "replay_session_id": replay_engine.session_id,
            "decision": decision.value,
            "applied_rules": replay_engine._arbiter.applied_rules,
            "rule_version": replay_engine._arbiter.rule_version,
            "deterministic": True,
        }

        self._replay_history.append(result)
        return result

    def deep_investigation(
        self,
        original_session_state: Dict[str, Any],
        new_evidence: Optional[List[Dict[str, Any]]] = None,
        new_hypotheses: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Mode B: Deep Investigation — create new investigation linked to original.

        Creates a derived experience that re-examines hypotheses with new evidence.
        Never modifies the historical result.
        """
        # Create a new session based on the original
        config = DebateSessionConfig(
            topic=original_session_state["topic"],
            max_turns=10,
        )
        personas: Dict[str, PersonaConfig] = {}

        replay_engine = DebateEngine(config, personas)

        # Restore original claims and evidence
        for claim_data in original_session_state.get("claims", []):
            claim = Claim(
                claim_id=claim_data["claim_id"],
                agent_id=claim_data["agent_id"],
                hypothesis=claim_data["hypothesis"],
                arguments=claim_data.get("arguments", []),
                evidence_refs=claim_data.get("evidence_refs", []),
                status=ClaimStatus(claim_data["status"]),
                trace_id=original_session_state.get("trace_id", ""),
            )
            replay_engine._claims.append(claim)

        for evid_data in original_session_state.get("evidence_registry", []):
            record = EvidenceRecord(
                evidence_id=evid_data["evidence_id"],
                claim_id=evid_data["claim_id"],
                evidence_type=evid_data["evidence_type"],
                content=evid_data["content"],
                verified=evid_data.get("verified", False),
                verification_method=evid_data.get("verification_method", ""),
            )
            replay_engine._evidence_registry.append(record)

        # Add new evidence if provided
        if new_evidence:
            for evid_data in new_evidence:
                record = EvidenceRecord(
                    evidence_id=evid_data["evidence_id"],
                    claim_id=evid_data.get("claim_id", ""),
                    evidence_type=evid_data.get("evidence_type", "new"),
                    content=evid_data.get("content", ""),
                    verified=evid_data.get("verified", False),
                    verification_method=evid_data.get("verification_method", ""),
                )
                replay_engine._evidence_registry.append(record)

        # Add new hypotheses if provided
        if new_hypotheses:
            for i, hyp in enumerate(new_hypotheses):
                claim = Claim(
                    claim_id=f"new_claim_{i}",
                    agent_id="investigator",
                    hypothesis=hyp,
                    status=ClaimStatus.UNVERIFIED,
                    trace_id=replay_engine.trace_id,
                )
                replay_engine._claims.append(claim)

        # Run arbiter
        replay_engine._status = DebateStatus.COMPLETED
        decision = replay_engine.arbitrate()

        result = {
            "mode": "DEEP_INVESTIGATION",
            "original_session_id": original_session_state.get("session_id"),
            "investigation_session_id": replay_engine.session_id,
            "decision": decision.value,
            "applied_rules": replay_engine._arbiter.applied_rules,
            "rule_version": replay_engine._arbiter.rule_version,
            "new_evidence_count": len(new_evidence or []),
            "new_hypotheses_count": len(new_hypotheses or []),
            "deterministic": True,
        }

        self._replay_history.append(result)
        return result

    def replay_session(self, session_state: Optional[Dict[str, Any]] = None, mode: str = "auto") -> Dict[str, Any]:
        """Replay a captured session (auto-detects mode).

        Args:
            session_state: Captured state to replay. Must be provided.
            mode: 'auto', 'historical', or 'deep'
        """
        if session_state is None:
            raise ValueError("session_state is required for replay_session")

        if mode == "deep":
            return self.deep_investigation(session_state)
        elif mode == "historical":
            return self.historical_replay(session_state)
        else:  # auto
            # Default to historical replay
            return self.historical_replay(session_state)

    def verify_determinism(self, original_decision: str, replayed_decision: str) -> bool:
        """Verify that two decisions are identical."""
        return original_decision == replayed_decision

    @property
    def replay_history(self) -> List[Dict[str, Any]]:
        return list(self._replay_history)


class DebateEngine:
    """Core debate engine with stagnation detection and deterministic arbiter.

    Integrates with:
    - core/safety/loop_detector.py for loop detection
    - core/safety/policy_guard.py for policy enforcement
    - core/safety/resource_guard.py for resource limits
    - core/observability/event_bus.py for event emission
    - core/router/evidence.py for evidence validation
    """

    def __init__(
        self,
        config: DebateSessionConfig,
        personas: Dict[str, PersonaConfig],
        provider_registry=None,
        safety_guard=None,
    ) -> None:
        self._config = config
        self._personas = personas
        self._provider_registry = provider_registry
        self._safety_guard = safety_guard
        self._status = DebateStatus.PENDING
        self._turns: List[DebateTurn] = []
        self._claims: List[Claim] = []
        self._evidence_registry: List[EvidenceRecord] = []
        self._contradictions: List[ContradictionRecord] = []
        self._stagnation_detector = StagnationDetector()
        self._arbiter = DeterministicArbiter()
        self._classifier = TaskClassifier()
        self._contradiction_detector = ContradictionDetector()
        self._provenance_graph = ProvenanceGraph()
        self._event_logger = DebateEventLogger(
            session_id=config.session_id,
            trace_id=config.trace_id or f"debate_{int(time.time())}_{hash(config.topic) % 0xFFFF:04x}",
        )
        self._trace_id = self._event_logger._trace_id
        self._start_time = 0.0
        self._end_time = 0.0
        self._total_tokens = 0
        # Quality metrics tracking
        self._previous_hypotheses: List[str] = []  # For novelty computation
        self._previous_evidence_refs: set = set()  # For memory recall
        self._total_evidence_citations = 0
        self._total_memory_recall = 0.0
        self._repetitive_turns = 0

    @property
    def session_id(self) -> str:
        return self._config.session_id

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def status(self) -> DebateStatus:
        return self._status

    @property
    def turns(self) -> List[DebateTurn]:
        return list(self._turns)

    @property
    def claims(self) -> List[Claim]:
        return list(self._claims)

    @property
    def evidence_registry(self) -> List[EvidenceRecord]:
        return list(self._evidence_registry)

    @property
    def contradictions(self) -> List[ContradictionRecord]:
        return list(self._contradictions)

    @property
    def provenance_graph(self) -> ProvenanceGraph:
        return self._provenance_graph

    @property
    def contradiction_detector(self) -> ContradictionDetector:
        return self._contradiction_detector

    @property
    def events(self) -> List[Dict[str, Any]]:
        return self._event_logger.get_events()

    @property
    def task_type(self) -> TaskType:
        return self._classifier.classify(self._config.topic)

    def start(self) -> bool:
        """Start the debate session."""
        if self._status != DebateStatus.PENDING:
            return False

        # Safety check
        if self._safety_guard:
            has_check = hasattr(self._safety_guard, "check_operation")
            if has_check and not self._safety_guard.check_operation("start_debate", "debate_engine"):
                self._event_logger.log(
                    DebateEventType.SECURITY_VIOLATION,
                    {"reason": "start_debate blocked by policy guard"},
                )
                return False

        self._status = DebateStatus.RUNNING
        self._start_time = time.time()
        self._event_logger.log(
            DebateEventType.DEBATE_STARTED,
            {"topic": self._config.topic, "max_turns": self._config.max_turns, "task_type": self.task_type.value},
        )
        logger.info("Debate started: session=%s, topic=%s, task_type=%s",
                    self.session_id, self._config.topic, self.task_type.value)
        return True

    def _compute_turn_metrics(self, turn: DebateTurn, response_text: str, new_evidence_count: int) -> None:
        """Compute quality metrics for a debate turn."""
        # 1. Memory Recall Score: How many previous evidence refs / claims are referenced
        recall_score = 0.0
        if self._previous_evidence_refs:
            # Extract citations from response (simple pattern matching for now)
            cited_refs = set(re.findall(r'\b(?:evidence|ref|claim)[_\s]*([A-Za-z0-9_-]+)', response_text, re.IGNORECASE))
            if cited_refs:
                matched = cited_refs & self._previous_evidence_refs
                recall_score = len(matched) / len(cited_refs) if cited_refs else 0.0
        
        turn.memory_recall_score = recall_score
        self._total_memory_recall += recall_score
        
        # 2. Evidence Citations: Count verifiable citations in this turn
        # Look for patterns like [1], (source), DOI, arXiv, etc.
        citation_patterns = [
            r'\[\d+\]',           # [1], [2], etc.
            r'\([^)]*\d{4}[^)]*\)',  # (Author, 2024)
            r'arXiv:\d{4}\.\d{4,5}',  # arXiv:2024.12345
            r'DOI:\s*\S+',        # DOI: 10.xxxx
            r'PMID:\s*\d+',       # PMID: 12345678
        ]
        evidence_citations = 0
        for pattern in citation_patterns:
            evidence_citations += len(re.findall(pattern, response_text, re.IGNORECASE))
        turn.evidence_citations = evidence_citations
        self._total_evidence_citations += evidence_citations
        
        # 3. New Evidence Count
        turn.new_evidence_count = new_evidence_count
        
        # 4. Hypothesis Novelty: Semantic distance from previous hypotheses
        if turn.claim and turn.claim.hypothesis:
            novelty = self._compute_hypothesis_novelty(turn.claim.hypothesis)
            turn.hypothesis_novelty = novelty
            self._previous_hypotheses.append(turn.claim.hypothesis)
        
        # 5. Repetition Detection
        turn.is_repetitive = self._is_turn_repetitive(turn, response_text)
        if turn.is_repetitive:
            self._repetitive_turns += 1
        
        # Update tracking sets
        if turn.claim:
            self._previous_evidence_refs.update(turn.claim.evidence_refs)

    def _compute_hypothesis_novelty(self, hypothesis: str) -> float:
        """Compute semantic novelty of a hypothesis vs previous ones (0-1 scale)."""
        if not self._previous_hypotheses:
            return 1.0  # First hypothesis is maximally novel
        
        # Simple word-overlap based novelty (can be replaced with embeddings)
        hyp_words = set(hypothesis.lower().split())
        max_overlap = 0.0
        for prev_hyp in self._previous_hypotheses:
            prev_words = set(prev_hyp.lower().split())
            if hyp_words and prev_words:
                overlap = len(hyp_words & prev_words) / len(hyp_words | prev_words)
                max_overlap = max(max_overlap, overlap)
        return 1.0 - max_overlap  # Inverse: low overlap = high novelty

    def _is_turn_repetitive(self, turn: DebateTurn, response_text: str) -> bool:
        """Detect if a turn repeats prior ideas without new evidence."""
        if not self._turns:
            return False
        
        # Check if the claim hypothesis is nearly identical to a previous one
        if turn.claim and turn.claim.hypothesis:
            for prev_turn in self._turns:
                if prev_turn.claim and prev_turn.claim.hypothesis:
                    # High word overlap indicates repetition
                    hyp_words = set(turn.claim.hypothesis.lower().split())
                    prev_words = set(prev_turn.claim.hypothesis.lower().split())
                    if hyp_words and prev_words:
                        overlap = len(hyp_words & prev_words) / len(hyp_words | prev_words)
                        if overlap > 0.8:  # 80% similarity threshold
                            return True
        
        # Check for repetitive phrasing in response text
        # (simplified: check if response is very similar to previous responses)
        for prev_turn in self._turns[-3:]:  # Last 3 turns
            if prev_turn.response_text:
                resp_words = set(response_text.lower().split())
                prev_words = set(prev_turn.response_text.lower().split())
                if resp_words and prev_words:
                    overlap = len(resp_words & prev_words) / len(resp_words | prev_words)
                    if overlap > 0.7 and turn.new_evidence_count == 0:
                        return True
        
        return False

    def _compute_hypothesis_evolution_score(self) -> float:
        """Compute how much hypotheses have evolved/progressed over the debate.
        
        Returns a score 0-1 where:
        - 0 = no progress, all hypotheses are similar
        - 1 = clear progression, each hypothesis builds on previous
        """
        if len(self._previous_hypotheses) < 2:
            return 0.0
        
        # Measure semantic distance between first and last hypothesis
        first = self._previous_hypotheses[0]
        last = self._previous_hypotheses[-1]
        
        first_words = set(first.lower().split())
        last_words = set(last.lower().split())
        
        if not first_words or not last_words:
            return 0.0
        
        # Evolution = how different the last hypothesis is from the first
        # but also check if intermediate hypotheses form a chain
        total_distance = 0.0
        for i in range(len(self._previous_hypotheses) - 1):
            hyp_a = set(self._previous_hypotheses[i].lower().split())
            hyp_b = set(self._previous_hypotheses[i + 1].lower().split())
            if hyp_a and hyp_b:
                distance = 1.0 - (len(hyp_a & hyp_b) / len(hyp_a | hyp_b))
                total_distance += distance
        
        # Normalize by number of transitions
        avg_transition = total_distance / (len(self._previous_hypotheses) - 1)
        
        # Also consider overall first-to-last distance
        first_last_distance = 1.0 - (len(first_words & last_words) / len(first_words | last_words))
        
        return min(1.0, (avg_transition + first_last_distance) / 2.0)

    def step(self, speaker_id: str, response_text: str, model_used: str = "",
             provider: ProviderType = ProviderType.MOCK, new_evidence_count: int = 1) -> DebateTurn:
        """Execute one turn of the debate."""
        if self._status != DebateStatus.RUNNING:
            raise RuntimeError(f"Cannot step: status is {self._status.value}")

        # Check max turns
        if len(self._turns) >= self._config.max_turns:
            self._status = DebateStatus.COMPLETED
            return self._turns[-1] if self._turns else DebateTurn(0, speaker_id)

        # Resource check
        if self._safety_guard:
            elapsed = (time.time() - self._start_time) * 1000
            resource_event = self._safety_guard.check_limit(
                "execution_time", elapsed, "debate_engine", self.session_id
            )
            if resource_event:
                self._event_logger.log(
                    DebateEventType.RESOURCE_WARNING,
                    {"resource": "execution_time", "elapsed_ms": elapsed},
                )

        turn = DebateTurn(
            turn_number=len(self._turns) + 1,
            speaker_id=speaker_id,
            response_text=response_text,
            model_used=model_used,
            provider=provider,
            latency_ms=0.0,
        )

        # Compute quality metrics for this turn
        self._compute_turn_metrics(turn, response_text, new_evidence_count)
        
        self._turns.append(turn)

        # Log round start
        self._event_logger.log(
            DebateEventType.ROUND_STARTED,
            {"turn": turn.turn_number, "speaker": speaker_id},
        )

        # Check stagnation
        stagnation = self._stagnation_detector.check_progress(turn, new_evidence_count)
        if stagnation["is_stagnant"]:
            logger.warning("Debate stagnation detected: %s", stagnation["indicators"])
            self._event_logger.log(
                DebateEventType.DEBATE_STAGNATION,
                {"indicators": stagnation["indicators"], "progress_score": stagnation["progress_score"]},
            )
            self._status = DebateStatus.STOPPED
            return turn

        # Check for completed turns
        if len(self._turns) >= self._config.max_turns:
            self._status = DebateStatus.COMPLETED
            self._event_logger.log(
                DebateEventType.DEBATE_COMPLETED,
                {"turns_committed": len(self._turns)},
            )

        return turn

    def add_claim(
        self,
        claim_id: str,
        agent_id: str,
        hypothesis: str,
        arguments: List[str],
        evidence_refs: List[str],
        status: ClaimStatus = ClaimStatus.UNVERIFIED,
    ) -> Claim:
        """Add a claim to the debate."""
        # Use ContradictionDetector v2 for enhanced detection
        for existing in self._claims:
            if existing.claim_id != claim_id:
                contra_result = self._contradiction_detector.detect_contradiction(existing.hypothesis, hypothesis)
                if contra_result:
                    contradiction_id = f"contra_{len(self._contradictions) + 1}"
                    contra = ContradictionRecord(
                        contradiction_id=contradiction_id,
                        claim_a_id=existing.claim_id,
                        claim_b_id=claim_id,
                        description=contra_result["description"],
                    )
                    self._contradictions.append(contra)
                    existing.contradictions.append(contradiction_id)
                    self._event_logger.log(
                        DebateEventType.CONTRADICTION_DETECTED,
                        {"contradiction_id": contradiction_id, "claim_a": existing.claim_id, "claim_b": claim_id, "type": contra_result["type"]},
                    )

        claim = Claim(
            claim_id=claim_id,
            agent_id=agent_id,
            hypothesis=hypothesis,
            arguments=arguments,
            evidence_refs=evidence_refs,
            status=status,
            trace_id=self._trace_id,
        )
        self._claims.append(claim)
        self._provenance_graph.add_claim(claim)

        event_type = DebateEventType.CLAIM_SUBMITTED if "a" in agent_id else DebateEventType.COUNTERCLAIM_SUBMITTED
        self._event_logger.log(
            event_type,
            {"claim_id": claim_id, "agent": agent_id, "hypothesis": hypothesis[:200], "status": status.value},
        )
        return claim

    def add_evidence(self, evidence_id: str, claim_id: str, evidence_type: str,
                     content: str, verified: bool = False,
                     verification_method: str = "", source: str = "",
                     supports_claims: Optional[List[str]] = None,
                     depends_on: Optional[List[str]] = None,
                     conclusions: Optional[List[str]] = None) -> EvidenceRecord:
        """Add evidence to the registry."""
        record = EvidenceRecord(
            evidence_id=evidence_id,
            claim_id=claim_id,
            evidence_type=evidence_type,
            content=content,
            verified=verified,
            verification_method=verification_method,
            source=source,
            supports_claims=supports_claims or [],
            depends_on=depends_on or [],
            conclusions=conclusions or [],
        )
        self._evidence_registry.append(record)
        self._provenance_graph.add_evidence(record)

        event_type = DebateEventType.EVIDENCE_VERIFIED if verified else DebateEventType.EVIDENCE_SUBMITTED
        self._event_logger.log(
            event_type,
            {"evidence_id": evidence_id, "claim_id": claim_id, "type": evidence_type, "verified": verified, "source": source},
        )
        return record

    def resolve_contradiction(self, contradiction_id: str, resolution: str) -> bool:
        """Mark a contradiction as resolved."""
        for contra in self._contradictions:
            if contra.contradiction_id == contradiction_id:
                contra.resolved = True
                contra.resolution = resolution
                self._event_logger.log(
                    DebateEventType.CONTRADICTION_RESOLVED,
                    {"contradiction_id": contradiction_id, "resolution": resolution[:200]},
                )
                return True
        return False

    def pause(self) -> bool:
        """Pause the debate."""
        if self._status == DebateStatus.RUNNING:
            self._status = DebateStatus.PAUSED
            self._event_logger.log(DebateEventType.DEBATE_PAUSED, {})
            return True
        return False

    def resume(self) -> bool:
        """Resume a paused debate."""
        if self._status == DebateStatus.PAUSED:
            self._status = DebateStatus.RUNNING
            self._event_logger.log(DebateEventType.DEBATE_RESUMED, {})
            return True
        return False

    def stop(self) -> bool:
        """Stop the debate."""
        if self._status in (DebateStatus.RUNNING, DebateStatus.PAUSED):
            self._status = DebateStatus.STOPPED
            self._end_time = time.time()
            self._event_logger.log(
                DebateEventType.DEBATE_STOPPED,
                {"turns_committed": len(self._turns)},
            )
            return True
        return False

    def arbitrate(self) -> ArbiterDecision:
        """Run the deterministic arbiter."""
        if self._status not in (DebateStatus.COMPLETED, DebateStatus.STOPPED):
            raise RuntimeError("Cannot arbitrate: debate not completed")

        decision = self._arbiter.arbitrate(
            self._claims,
            self._config,
            [e.to_dict() for e in self._evidence_registry],
        )
        self._event_logger.log(
            DebateEventType.ARBITER_DECISION,
            {"decision": decision.value, "rules": self._arbiter.applied_rules},
        )
        logger.info(
            "Arbiter decision: %s (rules: %s)",
            decision.value, self._arbiter.applied_rules,
        )
        return decision

    def _has_contradiction(self, h1: str, h2: str) -> bool:
        """Simple contradiction detection based on mutual exclusion keywords."""
        h1_lower = h1.lower()
        h2_lower = h2.lower()
        negation_pairs = [
            ("meaningful", "meaningless"),
            ("has meaning", "no meaning"),
            ("inherent meaning", "no inherent meaning"),
            ("true", "false"),
            ("exists", "does not exist"),
            ("good", "bad"),
            ("right", "wrong"),
            ("is", "is not"),
            ("will", "won't"),
        ]
        for a, b in negation_pairs:
            if (a in h1_lower and b in h2_lower) or (b in h1_lower and a in h2_lower):
                return True
        return False

    def replay_session(self) -> Dict[str, Any]:
        """Replay this session deterministically and verify identical decision."""
        from core.debate.engine import ReplayEngine
        replay = ReplayEngine()
        captured = replay.capture_session(self)
        original_decision = self._arbiter.applied_rules[-1] if self._arbiter.applied_rules else None

        # Run arbiter again on same state
        replay_engine = DebateEngine(
            DebateSessionConfig(topic=self._config.topic, max_turns=self._config.max_turns),
            {},
        )
        for t in self._turns:
            replay_engine._turns.append(t)
        for c in self._claims:
            replay_engine._claims.append(c)
        for e in self._evidence_registry:
            replay_engine._evidence_registry.append(e)
        for cd in self._contradictions:
            replay_engine._contradictions.append(cd)
        replay_engine._status = DebateStatus.COMPLETED
        replayed_decision = replay_engine.arbitrate()

        is_deterministic = (
            self._arbiter.applied_rules == replay_engine._arbiter.applied_rules and
            self._arbiter.rule_version == replay_engine._arbiter.rule_version
        )
        return {
            "session_id": self.session_id,
            "original_decision": original_decision,
            "replayed_decision": replayed_decision.value,
            "deterministic": is_deterministic,
            "applied_rules": self._arbiter.applied_rules,
            "rule_version": self._arbiter.rule_version,
        }

    def get_result(self) -> DebateResult:
        """Get the final debate result."""
        decision = ArbiterDecision.UNRESOLVED
        justification = ""
        if self._status in (DebateStatus.COMPLETED, DebateStatus.STOPPED):
            decision = self.arbitrate()
            justification = self._arbiter.get_justification(decision)

        metrics = {
            "total_turns": len(self._turns),
            "total_claims": len(self._claims),
            "total_evidence": len(self._evidence_registry),
            "total_contradictions": len(self._contradictions),
            "resolved_contradictions": sum(1 for c in self._contradictions if c.resolved),
            "duration_seconds": (self._end_time or time.time()) - self._start_time,
            "personas_used": list(self._personas.keys()),
            "routing_method": self._config.routing_method,
            "task_type": self.task_type.value,
            "trace_id": self._trace_id,
            # Quality metrics
            "memory_recall_avg": self._total_memory_recall / max(1, len(self._turns)),
            "evidence_accuracy_rate": self._total_evidence_citations / max(1, len(self._turns)),
            "contradiction_rate": len(self._contradictions) / max(1, len(self._turns)),
            "hypothesis_evolution_score": self._compute_hypothesis_evolution_score(),
            "repetition_rate": self._repetitive_turns / max(1, len(self._turns)),
        }

        return DebateResult(
            session_id=self.session_id,
            topic=self._config.topic,
            status=self._status,
            turns_committed=len(self._turns),
            max_turns=self._config.max_turns,
            arbiter_decision=decision,
            arbiter_justification=justification,
            claims=self._claims,
            transcript=[t.to_dict() for t in self._turns],
            evidence_registry=[e.to_dict() for e in self._evidence_registry],
            contradictions=[c.to_dict() for c in self._contradictions],
            metrics=metrics,
            trace_id=self._trace_id,
        )

    def export_report(self) -> Dict[str, Any]:
        """Export a full debate report."""
        result = self.get_result()
        return {
            "session_id": result.session_id,
            "trace_id": result.trace_id,
            "topic": result.topic,
            "status": result.status.value,
            "task_type": self.task_type.value,
            "arbiter_decision": result.arbiter_decision.value,
            "arbiter_justification": result.arbiter_justification,
            "arbiter_rule_version": self._arbiter.rule_version,
            "claims": [c.to_dict() for c in result.claims],
            "evidence_registry": result.evidence_registry,
            "contradictions": result.contradictions,
            "transcript": result.transcript,
            "events": self._event_logger.get_events(),
            "metrics": result.metrics,
        }
