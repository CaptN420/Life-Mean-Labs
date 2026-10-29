"""Safety layer for LIFE_MEAN.

Provides loop detection, policy enforcement, resource guards, and incident management.
"""
from __future__ import annotations

from .loop_detector import LoopDetector, LoopEvent
from .policy_guard import PolicyGuard, PolicyViolation
from .resource_guard import ResourceGuard, ResourceExceeded
from .incident_manager import IncidentManager, IncidentEvent
from .sentinel import Sentinel, SentinelConfig, SentinelAlertLevel, SentinelAction

__all__ = [
    "LoopDetector",
    "LoopEvent",
    "PolicyGuard",
    "PolicyViolation",
    "ResourceGuard",
    "ResourceExceeded",
    "IncidentManager",
    "IncidentEvent",
    "Sentinel",
    "SentinelConfig",
    "SentinelAlertLevel",
    "SentinelAction",
]
