"""Recovery Manager — orchestrates failure recovery and pipeline resilience.

Adapted from Mia_Brain concepts.
Pure Python, zero LLM for core logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from library.reliability.fallback import DeterministicFallback

logger = logging.getLogger("RecoveryManager")


class RecoveryManager:
    """Orchestrates failure recovery and pipeline resilience."""

    def __init__(self):
        self._fallback = DeterministicFallback()
        self._recovery_history: List[Dict[str, Any]] = []
        self._failure_count: int = 0
        self._max_retries: int = 3

    # ------------------------------------------------------------------
    def record_failure(self, failure_context: Dict[str, Any]) -> Dict[str, Any]:
        """Record a failure and attempt recovery."""
        self._failure_count += 1
        logger.warning("RecoveryManager: Failure #%d recorded", self._failure_count)

        # Analyze and generate recovery proposal
        proposal = self._fallback.analyze_failure(failure_context)

        # Record in history
        self._recovery_history.append({
            "failure_id": self._failure_count,
            "timestamp": self._failure_count,
            "failure_context": failure_context,
            "recovery_proposal": proposal,
            "status": "recovered" if proposal.get("confidence", 0) > 0.5 else "escalated",
        })

        return proposal

    # ------------------------------------------------------------------
    def should_retry(self, attempt: int = 0) -> bool:
        """Determine if a retry should be attempted."""
        if attempt >= self._max_retries:
            logger.warning("RecoveryManager: Max retries (%d) reached", self._max_retries)
            return False

        # Check if failures are escalating
        recent_failures = [
            h for h in self._recovery_history
            if h["failure_id"] > self._failure_count - 5
        ]
        if len(recent_failures) > 3:
            logger.warning("RecoveryManager: Too many recent failures, skipping retry")
            return False

        return True

    # ------------------------------------------------------------------
    def get_recovery_status(self) -> Dict[str, Any]:
        """Get current recovery status."""
        return {
            "total_failures": self._failure_count,
            "recovery_attempts": len(self._recovery_history),
            "max_retries": self._max_retries,
            "recent_failures": len([
                h for h in self._recovery_history
                if h["failure_id"] > self._failure_count - 5
            ]),
        }

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset recovery state."""
        self._failure_count = 0
        self._recovery_history = []
        logger.info("RecoveryManager: State reset")


# Convenience function
def recover(failure_context: Dict[str, Any]) -> Dict[str, Any]:
    """Public convenience function — analyzes failure and returns recovery proposal."""
    manager = RecoveryManager()
    return manager.record_failure(failure_context)
