"""Deterministic oracle validator for synthetic data.

Provides ground-truth validation for math, physics, and chemistry tasks
using exact computation rather than LLM judgment.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional

from .schemas import ValidationResult

logger = logging.getLogger("OracleValidator")


class OracleValidator:
    """Deterministic validator using ground truth computation."""

    def __init__(self):
        self._validation_count = 0
        self._failure_count = 0

    def validate(
        self,
        task_description: str,
        answer: Any,
        ground_truth: Any,
        domain: str = "math",
    ) -> ValidationResult:
        """Validate an answer against ground truth.

        Args:
            task_description: Original task description
            answer: Computed answer
            ground_truth: Expected answer
            domain: Task domain

        Returns:
            ValidationResult with validity and score
        """
        self._validation_count += 1

        if answer is None:
            self._failure_count += 1
            return ValidationResult(
                valid=False,
                score=0.0,
                method="deterministic",
                error="No answer provided",
                steps=["answer_is_none"],
            )

        if ground_truth is None:
            self._failure_count += 1
            return ValidationResult(
                valid=False,
                score=0.0,
                method="deterministic",
                error="No ground truth available",
                steps=["no_ground_truth"],
            )

        # Validate based on domain
        if domain == "math":
            return self._validate_math(task_description, answer, ground_truth)
        elif domain == "physics":
            return self._validate_physics(task_description, answer, ground_truth)
        elif domain == "chemistry":
            return self._validate_chemistry(task_description, answer, ground_truth)
        else:
            return self._validate_generic(answer, ground_truth)

    def _validate_math(
        self, description: str, answer: Any, ground_truth: Any
    ) -> ValidationResult:
        """Validate math answers with tolerance."""
        try:
            # Numeric comparison with tolerance
            if isinstance(answer, (int, float)) and isinstance(ground_truth, (int, float)):
                diff = abs(float(answer) - float(ground_truth))
                tolerance = 1e-6
                valid = diff < tolerance
                if not valid:
                    self._failure_count += 1
                score = 1.0 if valid else max(0.0, 1.0 - diff / (abs(float(ground_truth)) + 1e-9))

                return ValidationResult(
                    valid=valid,
                    score=score,
                    method="deterministic",
                    evidence={
                        "answer": answer,
                        "ground_truth": ground_truth,
                        "difference": diff,
                        "tolerance": tolerance,
                    },
                    steps=["parse_numbers", "compute_difference", "check_tolerance"],
                )

            # String comparison
            if isinstance(answer, str) and isinstance(ground_truth, str):
                valid = answer.lower().strip() == ground_truth.lower().strip()
                if not valid:
                    self._failure_count += 1
                return ValidationResult(
                    valid=valid,
                    score=1.0 if valid else 0.0,
                    method="deterministic",
                    evidence={"answer": answer, "ground_truth": ground_truth},
                    steps=["string_compare"],
                )

            # Fallback to equality
            valid = answer == ground_truth
            if not valid:
                self._failure_count += 1
            return ValidationResult(
                valid=valid,
                score=1.0 if valid else 0.0,
                method="deterministic",
                evidence={"answer": answer, "ground_truth": ground_truth},
            )

        except (TypeError, ValueError) as e:
            return ValidationResult(
                valid=False,
                score=0.0,
                method="deterministic",
                error=str(e),
                steps=["validation_error"],
            )

    def _validate_physics(
        self, description: str, answer: Any, ground_truth: Any
    ) -> ValidationResult:
        """Validate physics answers with physical tolerance."""
        try:
            if isinstance(answer, (int, float)) and isinstance(ground_truth, (int, float)):
                diff = abs(float(answer) - float(ground_truth))
                # Physics problems often have larger tolerances
                tolerance = max(1e-3, abs(float(ground_truth)) * 0.01)
                valid = diff < tolerance
                score = 1.0 if valid else max(0.0, 1.0 - diff / (abs(float(ground_truth)) + 1e-9))

                return ValidationResult(
                    valid=valid,
                    score=score,
                    method="deterministic",
                    evidence={
                        "answer": answer,
                        "ground_truth": ground_truth,
                        "difference": diff,
                        "tolerance": tolerance,
                    },
                    steps=["parse_physics_values", "compute_difference", "check_physical_tolerance"],
                )

            return ValidationResult(valid=False, score=0.0, method="deterministic", error="Invalid types")

        except (TypeError, ValueError) as e:
            return ValidationResult(
                valid=False,
                score=0.0,
                method="deterministic",
                error=str(e),
            )

    def _validate_chemistry(
        self, description: str, answer: Any, ground_truth: Any
    ) -> ValidationResult:
        """Validate chemistry answers."""
        try:
            if isinstance(answer, (int, float)) and isinstance(ground_truth, (int, float)):
                diff = abs(float(answer) - float(ground_truth))
                # Molar masses have typical tolerance of 0.1
                tolerance = 0.1
                valid = diff < tolerance
                score = 1.0 if valid else max(0.0, 1.0 - diff / (abs(float(ground_truth)) + 1e-9))

                return ValidationResult(
                    valid=valid,
                    score=score,
                    method="deterministic",
                    evidence={
                        "answer": answer,
                        "ground_truth": ground_truth,
                        "difference": diff,
                        "tolerance": tolerance,
                    },
                    steps=["parse_chemistry_values", "compute_difference", "check_molar_tolerance"],
                )

            return ValidationResult(valid=False, score=0.0, method="deterministic", error="Invalid types")

        except (TypeError, ValueError) as e:
            return ValidationResult(
                valid=False,
                score=0.0,
                method="deterministic",
                error=str(e),
            )

    def _validate_generic(self, answer: Any, ground_truth: Any) -> ValidationResult:
        """Generic validation fallback."""
        try:
            if answer == ground_truth:
                return ValidationResult(
                    valid=True,
                    score=1.0,
                    method="deterministic",
                    evidence={"answer": answer, "ground_truth": ground_truth},
                )

            return ValidationResult(
                valid=False,
                score=0.0,
                method="deterministic",
                evidence={"answer": answer, "ground_truth": ground_truth},
            )

        except Exception as e:
            return ValidationResult(
                valid=False,
                score=0.0,
                method="deterministic",
                error=str(e),
            )

    def get_statistics(self) -> Dict[str, Any]:
        """Get validation statistics."""
        return {
            "total_validations": self._validation_count,
            "failures": self._failure_count,
            "pass_rate": (self._validation_count - self._failure_count) / max(1, self._validation_count),
        }
