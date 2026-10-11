"""Stage dispatch — map a design stage's ``executor_type`` onto the compatible
EXISTING execution component.

This is the §9/§10 seam that keeps the Experimental Engine a composition layer
and NEVER reproduces the old bug where non-Code-Lab templates fail inside
CodeLabEngine. Each stage selects ONE component; unsupported/unconnected
executor types fail cleanly with EXECUTOR_NOT_AVAILABLE (no fake fallback,
spec §11 / §21).

Only ``connected == True`` executors may be dispatched to a run. Code Lab and
deterministic validation are available deterministically; DebateEngine /
ResearchWorker / LLM review / synthesis require a live backend and are marked
honestly as not-connected in this environment.
"""

from __future__ import annotations

from typing import Any, Dict


class ExecutorNotAvailable(RuntimeError):
    """Raised when a stage's executor is unknown or not connected.

    category == \"EXECUTOR_NOT_AVAILABLE\" (spec §21). ``executor_type`` echoes
    the requested executor and ``engine`` the component that would run it.
    """

    def __init__(self, message: str, executor_type: str, engine: Any = None,
                 category: str = "EXECUTOR_NOT_AVAILABLE") -> None:
        super().__init__(message)
        self.executor_type = executor_type
        self.engine = engine
        self.category = category


# Stage-level executor catalog. `connected` mirrors what is actually runnable
# right now: Code Lab + deterministic validation need no live LLM; the debate /
# research / LLM-review / synthesis executors require a live authentication
# backend (down here) and are therefore NOT connected this session.
STAGE_EXECUTORS: Dict[str, Dict[str, Any]] = {
    "code_lab": {
        "engine": "CodeLabEngine",
        "kind": "code",
        "connected": True,
        "classifies": ("code", "coding", "benchmark", "repair", "test"),
        "description": "Code Lab: deterministic + multi-agent code generation/validation.",
    },
    "code": {"engine": "CodeLabEngine", "kind": "code", "connected": True,
             "classifies": ("code",), "description": "Code execution via CodeLabEngine."},
    "benchmark": {"engine": "CodeLabEngine", "kind": "code", "connected": True,
                  "classifies": ("benchmark",), "description": "Deterministic benchmark."},
    "deterministic": {"engine": "ToolWorker + validators", "kind": "deterministic",
                      "connected": True, "classifies": ("validation",),
                      "description": "Deterministic validators / tool host."},
    # ── DEBATE → CODE chain (deterministic design debate → spec → code → verify) ──
    "debate_code": {"engine": "RetryAgent (debate→spec→code→verify)", "kind": "debate_code",
                    "connected": True, "classifies": ("debate", "code", "integration"),
                    "description": "Closed, traceable DEBATE→DECISION_SPEC→CODE→VERIFY chain."},
    "tool_execution": {"engine": "ToolWorker", "kind": "deterministic", "connected": True,
                       "classifies": ("tool",), "description": "Stable tool execution."},
    "validation": {"engine": "ToolWorker + validators", "kind": "deterministic",
                   "connected": True, "classifies": ("validation",),
                   "description": "Deterministic checks (no semantic judgment)."},
    # ── LLM / live-backend stages: exist as executors, NOT connected this env ──
    "debate": {"engine": "DebateEngine", "kind": "debate", "connected": False,
               "classifies": ("debate",), "description": "Philosophical/council debate."},
    "general_reasoning": {"engine": None, "kind": "reasoning", "connected": False,
                          "classifies": ("reasoning",),
                          "description": "Standalone reasoning executor (none wired)."},
    "research": {"engine": "ResearchWorker", "kind": "research", "connected": False,
                 "classifies": ("research",),
                 "description": "Research worker (not present/wired this env)."},
    "review": {"engine": "LLM reviewer", "kind": "review", "connected": False,
               "classifies": ("review",), "description": "LLM semantic review."},
    "synthesis": {"engine": "LLM synthesis", "kind": "synthesis", "connected": False,
                  "classifies": ("synthesis",), "description": "LLM result synthesis."},
}


def dispatch_stage(executor_type: str) -> Dict[str, Any]:
    """Resolve a stage's executor_type to its EXISTING executor descriptor.

    Raises :class:`ExecutorNotAvailable` when unregistered or not connected —
    never a silent fallback. This is the single decision point the
    ExperimentalEngine calls before touching any engine."""
    cap = STAGE_EXECUTORS.get(executor_type)
    if cap is None:
        raise ExecutorNotAvailable(
            f"executor_type '{executor_type}' has no registered executor",
            executor_type)
    if not cap.get("connected"):
        raise ExecutorNotAvailable(
            f"executor_type '{executor_type}' targets "
            f"{cap.get('engine') or 'a not-yet-wired executor'} "
            "which is NOT connected now",
            executor_type, engine=cap.get("engine"))
    return dict(cap, executor_type=executor_type)


# Re-export for a single import surface.
EXECUTOR_NOT_AVAILABLE = ExecutorNotAvailable  # noqa: A101  (alias used by validation)


def executor_catalog() -> Dict[str, Dict[str, Any]]:
    """Public, serializable view of every stage executor + its connectivity
    (used by capability discovery, spec §13)."""
    out: Dict[str, Dict[str, Any]] = {}
    for et, cap in STAGE_EXECUTORS.items():
        out[et] = {k: v for k, v in cap.items() if k != "classifies"}
    return out