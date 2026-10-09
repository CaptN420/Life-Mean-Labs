"""Reliability — deterministic recovery and resilience mechanisms.

Adapted from Mia_Brain concepts.
Pure Python, zero LLM for core logic.
"""

from __future__ import annotations

from library.reliability.context import (
    AdaptiveBudgetPlan,
    ComplexitySignals,
    ComplexityWeights,
    DEFAULT_WEIGHTS,
    CALIBRATION_VARIANTS,
    compute_signals,
    compute_complexity,
    compute_complexity_weighted,
    classify_complexity,
    plan_budget,
)
from library.reliability.fallback import FallbackRecovery, DeterministicFallback
from library.reliability.manager import RecoveryManager, recover

__all__ = [
    "AdaptiveBudgetPlan",
    "ComplexitySignals",
    "ComplexityWeights",
    "DEFAULT_WEIGHTS",
    "CALIBRATION_VARIANTS",
    "compute_signals",
    "compute_complexity",
    "compute_complexity_weighted",
    "classify_complexity",
    "plan_budget",
    "FallbackRecovery",
    "DeterministicFallback",
    "RecoveryManager",
    "recover",
]
