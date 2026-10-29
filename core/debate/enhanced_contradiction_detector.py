"""Enhanced Contradiction Detector with precise classification.

Classifies contradictions into:
- LOGICAL_CONTRADICTION: Direct logical incompatibility
- SEMANTIC_TENSION: Semantic tension without direct contradiction
- CONTEXT_DEPENDENT: Depends on context to determine incompatibility
- NO_CONTRADICTION: No contradiction detected

Scores are heuristic and clearly labeled as such.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.contradiction_detector")


# ── Enums ────────────────────────────────────────────────────────────────────


class ContradictionType(str, Enum):
    """Precise classification of contradiction."""
    LOGICAL_CONTRADICTION = "LOGICAL_CONTRADICTION"
    SEMANTIC_TENSION = "SEMANTIC_TENSION"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"
    NO_CONTRADICTION = "NO_CONTRADICTION"


class CertaintyLevel(str, Enum):
    """Certainty level of the detection."""
    CERTAIN = "CERTAIN"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNCERTAIN = "UNCERTAIN"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ContradictionFinding:
    """A finding from contradiction detection."""

    type: ContradictionType
    pattern: str
    certainty: CertaintyLevel
    confidence: float  # Heuristic score, clearly labeled
    description: str
    is_heuristic: bool = True  # Always true for these detectors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "pattern": self.pattern,
            "certainty": self.certainty.value,
            "confidence": self.confidence,
            "description": self.description,
            "is_heuristic": self.is_heuristic,
        }


# ── Enhanced Contradiction Detector ──────────────────────────────────────────


class EnhancedContradictionDetector:
    """Enhanced contradiction detection with precise classification.

    Distinguishes between:
    - LOGICAL_CONTRADICTION: Direct negation or logical incompatibility
    - SEMANTIC_TENSION: Semantic tension without direct contradiction
    - CONTEXT_DEPENDENT: Requires context to determine
    - NO_CONTRADICTION: No contradiction found

    All scores are heuristic and marked as such.
    """

    # Strong negation patterns (logical contradiction)
    _STRONG_NEGATIONS = [
        ("has meaning", "no meaning"),
        ("has inherent meaning", "no inherent meaning"),
        ("is meaningful", "meaningless"),
        ("exists", "does not exist"),
        ("is real", "not real"),
        ("is true", "is false"),
        ("will happen", "won't happen"),
        ("can happen", "cannot happen"),
        ("should be", "should not be"),
        ("ought to", "ought not to"),
        ("is right", "is wrong"),
        ("is good", "is bad"),
        ("is possible", "is impossible"),
        ("is necessary", "is contingent"),
        ("is designed", "is accidental"),
    ]

    # Semantic tension patterns (not direct contradiction)
    _SEMANTIC_TENSIONS = [
        ("purpose", "random"),
        ("designed", "accidental"),
        ("ordered", "chaotic"),
        ("determined", "free"),
        ("objective", "subjective"),
        ("absolute", "relative"),
        ("universal", "local"),
        ("inherent", "constructed"),
    ]

    # Context-dependent patterns
    _CONTEXT_PATTERNS = [
        ("consciousness", "artificial"),
        ("free will", "determinism"),
        ("moral", "amoral"),
        ("value", "valueless"),
    ]

    def detect_contradiction(self, h1: str, h2: str) -> Optional[ContradictionFinding]:
        """Detect contradiction between two hypotheses with precise classification."""
        h1_lower = h1.lower()
        h2_lower = h2.lower()

        # 1. Check for strong logical contradictions
        finding = self._check_strong_negations(h1_lower, h2_lower)
        if finding:
            return finding

        # 2. Check for semantic tensions
        finding = self._check_semantic_tensions(h1_lower, h2_lower)
        if finding:
            return finding

        # 3. Check for context-dependent tensions
        finding = self._check_context_dependent(h1_lower, h2_lower)
        if finding:
            return finding

        return None

    def _check_strong_negations(self, h1: str, h2: str) -> Optional[ContradictionFinding]:
        """Check for strong logical negations."""
        for affirmative, negative in self._STRONG_NEGATIONS:
            # Check direct negation
            if (affirmative in h1 and negative in h2) or (negative in h1 and affirmative in h2):
                return ContradictionFinding(
                    type=ContradictionType.LOGICAL_CONTRADICTION,
                    pattern=f"{affirmative} vs {negative}",
                    certainty=CertaintyLevel.CERTAIN,
                    confidence=0.9,
                    description=f"Direct logical contradiction: '{affirmative}' vs '{negative}'",
                )

        # Check for explicit negation words
        negation_words = {"not", "no ", "never", "cannot", "won't", "isn't", "aren't", "doesn't"}
        h1_has_neg = any(neg in h1 for neg in negation_words)
        h2_has_neg = any(neg in h2 for neg in negation_words)

        # If both have negations, check if they negate each other
        if h1_has_neg and h2_has_neg:
            # Extract the core assertions
            h1_core = self._extract_core_assertion(h1)
            h2_core = self._extract_core_assertion(h2)
            if h1_core and h2_core and h1_core == h2_core:
                return ContradictionFinding(
                    type=ContradictionType.LOGICAL_CONTRADICTION,
                    pattern="mutual_negation",
                    certainty=CertaintyLevel.LIKELY,
                    confidence=0.85,
                    description=f"Mutual negation detected around core concept: '{h1_core}'",
                )

        return None

    def _check_semantic_tensions(self, h1: str, h2: str) -> Optional[ContradictionFinding]:
        """Check for semantic tensions (not direct contradictions)."""
        for a, b in self._SEMANTIC_TENSIONS:
            if (a in h1 and b in h2) or (b in h1 and a in h2):
                return ContradictionFinding(
                    type=ContradictionType.SEMANTIC_TENSION,
                    pattern=f"{a} vs {b}",
                    certainty=CertaintyLevel.POSSIBLE,
                    confidence=0.65,
                    description=f"Semantic tension: '{a}' vs '{b}'",
                    is_heuristic=True,
                )

        return None

    def _check_context_dependent(self, h1: str, h2: str) -> Optional[ContradictionFinding]:
        """Check for context-dependent tensions."""
        for a, b in self._CONTEXT_PATTERNS:
            if (a in h1 and b in h2) or (b in h1 and a in h2):
                return ContradictionFinding(
                    type=ContradictionType.CONTEXT_DEPENDENT,
                    pattern=f"{a} vs {b}",
                    certainty=CertaintyLevel.UNCERTAIN,
                    confidence=0.5,
                    description=f"Context-dependent tension: '{a}' vs '{b}'",
                    is_heuristic=True,
                )

        return None

    def _extract_core_assertion(self, text: str) -> Optional[str]:
        """Extract the core assertion from a negated statement."""
        # Remove common negation prefixes
        negations = ["it is not that ", "it is not ", "there is no ", "there isn't "]
        for neg in negations:
            if text.startswith(neg):
                text = text[len(neg):]

        # Return a simplified version (first 50 chars)
        return text.strip()[:50] or None

    def batch_detect(self, claims: List[Dict[str, Any]]) -> List[ContradictionFinding]:
        """Detect contradictions between all pairs of claims."""
        findings = []
        for i, c1 in enumerate(claims):
            for c2 in claims[i + 1:]:
                finding = self.detect_contradiction(c1.get("hypothesis", ""), c2.get("hypothesis", ""))
                if finding:
                    findings.append(finding)
        return findings

    def classify_pair(self, h1: str, h2: str) -> ContradictionType:
        """Quick classification of a pair without detailed findings."""
        finding = self.detect_contradiction(h1, h2)
        if finding:
            return finding.type
        return ContradictionType.NO_CONTRADICTION
