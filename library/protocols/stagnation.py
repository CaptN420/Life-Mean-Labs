"""Stagnation detection — identifies when debates or reasoning stall.

Adapted from Mia_Brain concepts.
Pure Python, zero LLM.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("StagnationDetection")


class StagnationDetector:
    """Detects when a debate or reasoning process has stalled."""

    def __init__(self):
        self._turn_history: List[Dict[str, Any]] = []
        self._consecutive_duplicates: int = 0
        self._last_speaker: str = ""

    # ------------------------------------------------------------------
    def add_turn(self, speaker: str, response: str, turn_id: int = 0) -> Dict[str, Any]:
        """Record a new turn and check for stagnation patterns."""
        self._turn_history.append({
            "turn_id": turn_id,
            "speaker": speaker,
            "response": response,
            "timestamp": len(self._turn_history),
        })

        # Check for repetition patterns
        result = self._check_stagnation(speaker, response)
        return result

    # ------------------------------------------------------------------
    def _check_stagnation(self, speaker: str, response: str) -> Dict[str, Any]:
        """Check if the current turn indicates stagnation."""
        indicators = []

        # Check consecutive repetition
        if speaker == self._last_speaker:
            self._consecutive_duplicates += 1
            if self._consecutive_duplicates >= 2:
                indicators.append({
                    "type": "consecutive_repetition",
                    "severity": "high",
                    "message": f"Speaker '{speaker}' has repeated {self._consecutive_duplicates + 1} times consecutively",
                })
        else:
            self._consecutive_duplicates = 0
        self._last_speaker = speaker

        # Check for short responses (potential stall)
        if len(response.strip()) < 20:
            indicators.append({
                "type": "short_response",
                "severity": "low",
                "message": f"Short response from '{speaker}' ({len(response)} chars)",
            })

        # Check for vague language patterns
        vague_patterns = ["maybe", "perhaps", "possibly", "might", "could be"]
        response_lower = response.lower()
        if any(p in response_lower for p in vague_patterns):
            indicators.append({
                "type": "vague_language",
                "severity": "medium",
                "message": f"Vague language detected from '{speaker}'",
            })

        # Check for circular reasoning patterns
        if self._has_circular_pattern(response):
            indicators.append({
                "type": "circular_reasoning",
                "severity": "high",
                "message": f"Circular reasoning pattern detected from '{speaker}'",
            })

        return {
            "stagnation_detected": len(indicators) > 0,
            "indicators": indicators,
            "turn_id": len(self._turn_history),
            "total_turns": len(self._turn_history),
        }

    # ------------------------------------------------------------------
    def _has_circular_pattern(self, response: str) -> bool:
        """Check if response contains circular reasoning patterns."""
        # Simple heuristic: check for self-referential patterns
        circular_patterns = [
            "because I said so",
            "this is true because",
            "as I mentioned before",
            "as we have established",
        ]
        response_lower = response.lower()
        return any(p in response_lower for p in circular_patterns)

    # ------------------------------------------------------------------
    def get_alternatives(self, exclude: str = "") -> List[str]:
        """Get alternative speakers who haven't spoken recently."""
        # In a real implementation, this would query the argument state
        # For now, return placeholder alternatives
        all_speakers = ["Existentialist", "Stoic", "Nihilist", "Spiritual", "Skeptic", "Pragmatist"]
        if exclude:
            all_speakers = [s for s in all_speakers if s != exclude]
        return all_speakers

    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        """Get current stagnation detection status."""
        return {
            "total_turns": len(self._turn_history),
            "consecutive_duplicates": self._consecutive_duplicates,
            "last_speaker": self._last_speaker,
            "stagnation_risk": "high" if self._consecutive_duplicates >= 2 else "low",
        }
