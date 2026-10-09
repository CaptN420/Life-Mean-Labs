"""Protocols — deterministic debate and reflection mechanisms.

Adapted from Mia_Brain concepts.
Pure Python, zero LLM.
"""

from __future__ import annotations

from library.protocols.reflection import ReflectionProtocol, reflect
from library.protocols.stagnation import StagnationDetector

__all__ = ["ReflectionProtocol", "reflect", "StagnationDetector"]
