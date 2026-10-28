"""
Life_mean Lab — Isolated Execution Environment

Provides sandboxed execution for agents with:
- Path-restricted workspaces
- Resource limits (CPU, memory, time)
- Independent abort mechanism
- Audit logging
"""

from .sandbox import SandboxWorkspace, validate_path
from .resource_limits import ResourceLimits, ProcessMonitor
from .abort_mechanism import AbortRegistry, abort_run
from .lab_orchestrator import LabOrchestrator

__all__ = [
    "SandboxWorkspace",
    "validate_path",
    "ResourceLimits",
    "ProcessMonitor",
    "AbortRegistry",
    "abort_run",
    "LabOrchestrator",
]
