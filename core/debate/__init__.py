"""Deterministic Debate Engine package.

Provides hypothesis confrontation with verifiable evidence,
stagnation detection, and deterministic arbitration.
"""

from .engine import (
    Claim,
    ClaimStatus,
    DebateEngine,
    DebateResult,
    DebateSessionConfig,
    DebateStatus,
    StagnationDetector,
    ArbiterDecision,
    DeterministicArbiter,
    DebateTurn,
)
from .events import DebateEvent, DebateEventLogger, DebateEventType

__all__ = [
    "Claim",
    "ClaimStatus",
    "DebateEngine",
    "DebateResult",
    "DebateSessionConfig",
    "DebateStatus",
    "StagnationDetector",
    "ArbiterDecision",
    "DeterministicArbiter",
    "DebateTurn",
    "DebateEvent",
    "DebateEventLogger",
    "DebateEventType",
]
