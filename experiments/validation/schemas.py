"""Validation result schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    """Result of validating a task answer."""

    valid: bool
    score: float = 0.0
    method: str = "deterministic"  # deterministic, llm_judge, hybrid
    evidence: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "score": self.score,
            "method": self.method,
            "evidence": self.evidence,
            "error": self.error,
            "steps": self.steps,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationResult":
        return cls(
            valid=data.get("valid", False),
            score=data.get("score", 0.0),
            method=data.get("method", "deterministic"),
            evidence=data.get("evidence", {}),
            error=data.get("error"),
            steps=data.get("steps", []),
        )


# CANONICAL FailureRecord lives in `experiments.failure_bank.schemas` (the
# semantic owner). This module re-exports the SAME class so both import paths
# resolve to ONE implementation — never two parallel dataclasses. It includes
# `validation_method` (merged from the former local schema).
from experiments.failure_bank.schemas import FailureRecord  # noqa: F401
