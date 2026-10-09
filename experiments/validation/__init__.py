"""Validation module for synthetic data generation.

Provides deterministic validation of task answers against ground truth,
with support for multiple domains and validation strategies.
"""

from __future__ import annotations

from .oracle import OracleValidator
from .schemas import ValidationResult

__all__ = ["OracleValidator", "ValidationResult"]
