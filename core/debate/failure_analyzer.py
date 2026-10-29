"""Failure Analyzer — transforms experimental failures into structured knowledge.

Extracts observable errors, identifies failure phases, classifies failures,
distinguishes immediate causes from root causes, and links diagnostics to evidence.
Preserves alternative hypotheses without premature conclusion.
"""

from __future__ import annotations

import json
import logging
import re
import time
import traceback as tb_module
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("core.debate.failure_analyzer")


# ── Enums ────────────────────────────────────────────────────────────────────


class FailureCategory(str, Enum):
    """Classification of failure types."""
    SYNTAX_ERROR = "SYNTAX_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    LOGIC_ERROR = "LOGIC_ERROR"
    VALIDATION_GAP = "VALIDATION_GAP"
    TEST_FAILURE = "TEST_FAILURE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    SECURITY_REJECTION = "SECURITY_REJECTION"
    CONFIGURATION_MISMATCH = "CONFIGURATION_MISMATCH"
    MODEL_OUTPUT_FAILURE = "MODEL_OUTPUT_FAILURE"
    NONDETERMINISTIC_BEHAVIOR = "NONDETERMINISTIC_BEHAVIOR"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class HypothesisStatus(str, Enum):
    """Status of a causal hypothesis."""
    UNTESTED = "UNTESTED"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    VERIFIED_CAUSAL = "VERIFIED_CAUSAL"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ObservedError:
    """An error observed during execution."""
    error_type: str
    message: str
    stack_trace: str = ""
    phase: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message[:500],
            "stack_trace": self.stack_trace[:1000],
            "phase": self.phase,
            "timestamp": self.timestamp,
        }


@dataclass
class CandidateCause:
    """A hypothesized cause of failure."""
    cause_id: str
    description: str
    is_immediate_cause: bool = False
    is_root_cause: bool = False
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    alternative_hypotheses: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cause_id": self.cause_id,
            "description": self.description[:300],
            "is_immediate_cause": self.is_immediate_cause,
            "is_root_cause": self.is_root_cause,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "alternative_hypotheses": self.alternative_hypotheses,
            "confidence": self.confidence,
        }


@dataclass
class FailureDiagnostic:
    """Structured diagnostic of a failure."""
    run_id: str
    status: str
    failure_category: FailureCategory
    observed_errors: List[ObservedError] = field(default_factory=list)
    candidate_causes: List[CandidateCause] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    root_cause_verified: bool = False
    alternative_explanations: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "failure_category": self.failure_category.value,
            "observed_errors": [e.to_dict() for e in self.observed_errors],
            "candidate_causes": [c.to_dict() for c in self.candidate_causes],
            "missing_evidence": self.missing_evidence,
            "root_cause_verified": self.root_cause_verified,
            "alternative_explanations": self.alternative_explanations,
            "timestamp": self.timestamp,
        }


# ── Failure Analyzer ─────────────────────────────────────────────────────────


class FailureAnalyzer:
    """Analyzes failed runs to produce structured diagnostics.

    Responsibilities:
    - Extract observable errors from traces
    - Identify failure phases
    - Classify failures into categories
    - Distinguish immediate cause from root cause
    - Link each diagnostic to evidence
    - Preserve alternative hypotheses
    """

    # Patterns for error classification
    _ERROR_PATTERNS = {
        FailureCategory.SYNTAX_ERROR: [
            r"SyntaxError",
            r"invalid syntax",
            r"unexpected indent",
            r"unexpected EOF",
            r"incomplete input",
        ],
        FailureCategory.RUNTIME_ERROR: [
            r"TypeError",
            r"NameError",
            r"AttributeError",
            r"KeyError",
            r"IndexError",
            r"ValueError",
            r"ZeroDivisionError",
            r"ImportError",
            r"ModuleNotFoundError",
        ],
        FailureCategory.LOGIC_ERROR: [
            r"AssertionError",
            r"incorrect result",
            r"wrong output",
            r"logic error",
        ],
        FailureCategory.TEST_FAILURE: [
            r"FAILED",
            r"test failed",
            r"assertion failed",
            r"E .*",  # pytest errors
        ],
        FailureCategory.DEPENDENCY_FAILURE: [
            r"No module named",
            r"dependency.*not found",
            r"cannot import",
        ],
        FailureCategory.RESOURCE_EXHAUSTION: [
            r"MemoryError",
            r"OutOfMemory",
            r"timeout",
            r"timed out",
            r"too many open files",
        ],
        FailureCategory.SECURITY_REJECTION: [
            r"Permission denied",
            r"Access denied",
            r"Unauthorized",
            r"Forbidden",
        ],
        FailureCategory.CONFIGURATION_MISMATCH: [
            r"Configuration error",
            r"invalid config",
            r"missing required",
            r"schema validation failed",
        ],
    }

    def __init__(self):
        self._diagnostics: Dict[str, FailureDiagnostic] = {}

    def analyze_failure(
        self,
        run_id: str,
        status: str,
        error_output: str = "",
        trace: Optional[Dict[str, Any]] = None,
        code: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> FailureDiagnostic:
        """Analyze a failed run and produce a structured diagnostic."""
        diagnostic = FailureDiagnostic(
            run_id=run_id,
            status=status,
            failure_category=FailureCategory.UNKNOWN_FAILURE,
        )

        # Extract errors from output
        errors = self._extract_errors(error_output, trace)
        diagnostic.observed_errors = errors

        if not errors:
            diagnostic.missing_evidence.append("No error output or trace available")
            diagnostic.alternative_explanations.append(
                "Failure may be due to non-deterministic behavior or external factors"
            )
        else:
            # Classify the failure
            diagnostic.failure_category = self._classify_failure(errors)

            # Generate candidate causes
            diagnostic.candidate_causes = self._generate_candidate_causes(
                run_id, errors, code, config
            )

            # Check for missing evidence
            diagnostic.missing_evidence = self._identify_missing_evidence(
                errors, trace, config
            )

        # Store diagnostic
        self._diagnostics[run_id] = diagnostic

        logger.info(
            "Failure analyzed: %s (category=%s, errors=%d)",
            run_id, diagnostic.failure_category.value, len(errors),
        )

        return diagnostic

    def get_diagnostic(self, run_id: str) -> Optional[FailureDiagnostic]:
        """Retrieve a diagnostic by run ID."""
        return self._diagnostics.get(run_id)

    def get_all_diagnostics(self) -> List[FailureDiagnostic]:
        """Get all diagnostics."""
        return list(self._diagnostics.values())

    def _extract_errors(
        self, error_output: str, trace: Optional[Dict[str, Any]]
    ) -> List[ObservedError]:
        """Extract structured errors from output and trace."""
        errors = []

        # Parse from trace if available
        if trace:
            for phase, phase_trace in trace.items():
                if isinstance(phase_trace, dict):
                    exception = phase_trace.get("exception")
                    if exception:
                        errors.append(ObservedError(
                            error_type=exception.get("type", "Unknown"),
                            message=exception.get("message", ""),
                            stack_trace=exception.get("stack_trace", ""),
                            phase=phase,
                        ))

        # Parse from error output
        if error_output:
            # Check for test failure patterns first
            if re.search(r"FAILED|test failed|AssertionError", error_output, re.IGNORECASE):
                errors.append(ObservedError(
                    error_type="TestFailure",
                    message=error_output[:200],
                    phase="test_execution",
                ))
                return errors

            # Split by common error separators
            lines = error_output.split("\n")
            current_error = None

            for line in lines:
                # Match exception type at start of line
                exc_match = re.match(
                    r"^(\w+Error): (.+)$", line.strip()
                )
                if exc_match:
                    if current_error:
                        errors.append(current_error)
                    current_error = ObservedError(
                        error_type=exc_match.group(1),
                        message=exc_match.group(2),
                    )
                elif line.strip().startswith("Traceback"):
                    continue
                elif current_error and line.strip():
                    current_error.stack_trace += line + "\n"

            if current_error:
                errors.append(current_error)

        return errors

    def _classify_failure(self, errors: List[ObservedError]) -> FailureCategory:
        """Classify failure based on observed errors."""
        # Check for test failures first (highest priority)
        if any(
            "FAILED" in e.message or "test failed" in e.message.lower() or "AssertionError" in e.error_type
            for e in errors
        ):
            return FailureCategory.TEST_FAILURE

        for error in errors:
            for category, patterns in self._ERROR_PATTERNS.items():
                # Skip test failure pattern since we already checked
                if category == FailureCategory.TEST_FAILURE:
                    continue
                for pattern in patterns:
                    if re.search(pattern, error.error_type + " " + error.message):
                        return category

        return FailureCategory.UNKNOWN_FAILURE

    def _generate_candidate_causes(
        self,
        run_id: str,
        errors: List[ObservedError],
        code: Optional[str],
        config: Optional[Dict[str, Any]],
    ) -> List[CandidateCause]:
        """Generate candidate causes for the failure."""
        causes = []

        # Immediate cause from first error
        if errors:
            first_error = errors[0]
            causes.append(CandidateCause(
                cause_id=f"CAUSE-{run_id}-001",
                description=f"Immediate cause: {first_error.error_type}: {first_error.message[:100]}",
                is_immediate_cause=True,
                supporting_evidence=[f"Error in phase: {first_error.phase}"],
            ))

        # Root cause hypotheses
        if code:
            # Check for known bug patterns
            if "_ngrams" in code or "words[i : i + n]" in code:
                causes.append(CandidateCause(
                    cause_id=f"CAUSE-{run_id}-002",
                    description="Potential bug: non-hashable list in set comprehension (expected tuple)",
                    is_root_cause=True,
                    supporting_evidence=["Code contains _ngrams pattern"],
                    alternative_hypotheses=[
                        "Bug exists but not triggered in this run",
                        "Different root cause entirely"
                    ],
                    confidence=0.7,
                ))

        # Configuration-related causes
        if config:
            missing = [k for k, v in config.items() if v is None or v == ""]
            if missing:
                causes.append(CandidateCause(
                    cause_id=f"CAUSE-{run_id}-003",
                    description=f"Configuration mismatch: {', '.join(missing)} not set",
                    supporting_evidence=[f"Missing config: {missing}"],
                ))

        return causes

    def _identify_missing_evidence(
        self,
        errors: List[ObservedError],
        trace: Optional[Dict[str, Any]],
        config: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Identify what evidence is missing for a complete diagnosis."""
        missing = []

        if not trace:
            missing.append("Execution trace unavailable")
        if not config:
            missing.append("Configuration snapshot unavailable")

        # Check for specific missing information
        if errors and not any(
            "stack_trace" in e.__dict__ and e.stack_trace for e in errors
        ):
            missing.append("Full stack traces unavailable")

        return missing

    def verify_root_cause(self, run_id: str, hypothesis_id: str) -> bool:
        """Mark a candidate cause as verified root cause."""
        diagnostic = self._diagnostics.get(run_id)
        if not diagnostic:
            return False

        for cause in diagnostic.candidate_causes:
            if cause.cause_id == hypothesis_id:
                cause.is_root_cause = True
                diagnostic.root_cause_verified = True
                return True

        return False
