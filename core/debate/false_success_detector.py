"""False Success Detector — identifies cases where validator reports PASS despite observable errors.

Checks for:
- Compilable but unexecuted code
- Missing tests
- Tests not covering critical path
- Undetected exceptions
- Structure-only validation
- Falsified or unverifiable test output
- Gap between declared status and execution evidence
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.false_success_detector")


# ── Enums ────────────────────────────────────────────────────────────────────


class FalseSuccessStatus(str, Enum):
    """Status of false success detection."""
    CONFIRMED_PASS = "CONFIRMED_PASS"
    SUSPECTED_FALSE_PASS = "SUSPECTED_FALSE_PASS"
    CONFIRMED_FALSE_PASS = "CONFIRMED_FALSE_PASS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class FalseSuccessFinding:
    """A finding of potential false success."""
    run_id: str
    status: FalseSuccessStatus
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    explanation: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "evidence": self.evidence,
            "explanation": self.explanation[:300],
            "timestamp": self.timestamp,
        }


# ── False Success Detector ───────────────────────────────────────────────────


class FalseSuccessDetector:
    """Detects cases where validator reports PASS despite observable errors.

    Never automatically concludes a run is incorrect based on unusual scores alone.
    Explains reasoning for each status assignment.
    """

    # Patterns indicating potential false success
    _SUSPICIOUS_PATTERNS = [
        (r"test passed.*without executing", "Tests passed without execution"),
        (r"PASS.*code not run", "PASS but code not executed"),
        (r"structure valid.*logic invalid", "Structure-only validation"),
        (r"0 failures.*no tests run", "No tests executed"),
        (r"all checks passed.*skipped", "Checks passed with skips"),
    ]

    def __init__(self):
        self._findings: Dict[str, FalseSuccessFinding] = {}

    def analyze_run(
        self,
        run_id: str,
        validator_output: str = "",
        test_output: str = "",
        code_executed: bool = False,
        tests_run: int = 0,
        tests_passed: int = 0,
        exceptions_detected: List[str] = None,
    ) -> FalseSuccessFinding:
        """Analyze a run for potential false success."""
        findings = []

        # Check if code was actually executed
        if not code_executed and (tests_passed > 0 or "PASS" in validator_output):
            findings.append(FalseSuccessFinding(
                run_id=run_id,
                status=FalseSuccessStatus.SUSPECTED_FALSE_PASS,
                confidence=0.6,
                reasons=["Code was not executed but tests passed"],
                explanation="Validator reports PASS but code execution evidence is absent",
            ))

        # Check test coverage
        if tests_run == 0 and tests_passed > 0:
            findings.append(FalseSuccessFinding(
                run_id=run_id,
                status=FalseSuccessStatus.SUSPECTED_FALSE_PASS,
                confidence=0.8,
                reasons=["Tests passed but zero tests were executed"],
                explanation="Impossible state: passed tests without execution",
            ))

        # Check for suspicious patterns in output
        for pattern, description in self._SUSPICIOUS_PATTERNS:
            if re.search(pattern, validator_output + " " + test_output, re.IGNORECASE):
                findings.append(FalseSuccessFinding(
                    run_id=run_id,
                    status=FalseSuccessStatus.SUSPECTED_FALSE_PASS,
                    confidence=0.7,
                    reasons=[description],
                    evidence=[pattern],
                ))

        # Check for undetected exceptions
        if exceptions_detected:
            findings.append(FalseSuccessFinding(
                run_id=run_id,
                status=FalseSuccessStatus.SUSPECTED_FALSE_PASS,
                confidence=0.9,
                reasons=["Exceptions detected but not reported"],
                evidence=exceptions_detected[:5],
            ))

        # Determine final status
        if not findings:
            finding = FalseSuccessFinding(
                run_id=run_id,
                status=FalseSuccessStatus.CONFIRMED_PASS,
                confidence=0.9,
                explanation="No indicators of false success found",
            )
        elif any(f.status == FalseSuccessStatus.CONFIRMED_FALSE_PASS for f in findings):
            finding = findings[0]
        else:
            # Aggregate findings
            max_confidence = max(f.confidence for f in findings)
            if max_confidence >= 0.8:
                status = FalseSuccessStatus.CONFIRMED_FALSE_PASS
            else:
                status = FalseSuccessStatus.SUSPECTED_FALSE_PASS

            finding = FalseSuccessFinding(
                run_id=run_id,
                status=status,
                confidence=max_confidence,
                reasons=[r for f in findings for r in f.reasons],
                explanation="Multiple indicators suggest potential false success",
            )

        self._findings[run_id] = finding
        logger.info(
            "False success analysis for %s: %s (confidence=%.2f)",
            run_id, finding.status.value, finding.confidence,
        )
        return finding

    def get_finding(self, run_id: str) -> Optional[FalseSuccessFinding]:
        """Get a finding by run ID."""
        return self._findings.get(run_id)

    def get_all_findings(self) -> List[FalseSuccessFinding]:
        """Get all findings."""
        return list(self._findings.values())

    def get_suspected_runs(self) -> List[str]:
        """Get all runs suspected of false success."""
        return [
            run_id for run_id, f in self._findings.items()
            if f.status in (FalseSuccessStatus.SUSPECTED_FALSE_PASS, FalseSuccessStatus.CONFIRMED_FALSE_PASS)
        ]
