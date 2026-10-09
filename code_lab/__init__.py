"""Code Lab — experimental code-generation pipeline over the stable core.

CODE LAB
    ↓
EXPERIMENTAL LAYER
    ↓
USES STABLE CORE (EventBus, SmartRouter, OracleValidator, RawDebateRecorder,
                   ToolWorker/tools, deterministic protocol)
"""

from .config import CodeLabConfig
from .workspace import CodeLabWorkspace, WorkspaceError
from .engine import CodeLabEngine, build_default_engine

__all__ = [
    "CodeLabConfig",
    "CodeLabWorkspace",
    "WorkspaceError",
    "CodeLabEngine",
    "build_default_engine",
]
