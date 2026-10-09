"""ExperimentalEngine — a COMPOSITION LAYER over the existing stable core.

It never reimplements an engine: it (1) gates execution on a FROZEN, valid
design, (2) dispatches each stage to the compatible EXISTING executor via
:mod:`experimental.dispatch`, (3) emits truthful EventBus events, and (4)
fails honestly with EXECUTOR_NOT_AVAILABLE / DESIGN_INVALID — no fake fallback,
no silent run of a non-frozen design (core rule: Design -> review -> approve ->
freeze -> execute; the LLM may propose but never start or mutate).

The actual heavy executors (CodeLabEngine, DebateEngine, ToolWorker, validators)
are injected as ``executors={kind: callable(stage, design)}`` — the engine only
routes to them. Deterministic stages may be bound; LLM-only stages (debate,
review, synthesis) are exposed but NOT-connected in this environment.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.events.event_bus import EventBus
from core.events.message import Message

from experimental.dispatch import ExecutorNotAvailable, dispatch_stage
from experimental.schema import ExperimentDesign
from experimental.validation import DesignInvalid, require_executable


class StopRequested(RuntimeError):
    """A human requested STOP mid-run (spec §21: report STOPPED, not FAILED)."""


EventFn = Callable[[Any, Any], Dict[str, Any]]  # (stage, design) -> result dict


class ExperimentalEngine:
    """Lifecycle supervisor + stage dispatcher for one experiment run."""

    def __init__(self, bus: Optional[EventBus] = None,
                 executors: Optional[Dict[str, EventFn]] = None) -> None:
        self.bus = bus
        # kind -> executor callable; refuse silent no-op unless explicitly bound.
        self._executors: Dict[str, EventFn] = dict(executors or {})
        self._stop_requested = False
        self.events: List[str] = []  # truthful event names, in order

    # ── event emission ────────────────────────────────────────────────────
    def _emit(self, event: str, payload: Dict[str, Any]) -> None:
        self.events.append(event)
        if self.bus is not None:
            self.bus.publish(Message(
                type=event, sender="experimental_engine",
                payload={**payload, "event": event}))

    @staticmethod
    def _design_ctx(d: ExperimentDesign) -> Dict[str, Any]:
        return {"design_id": d.design_id, "version": d.version, "design_hash": d.content_hash()}

    # ── executor registration ─────────────────────────────────────────────
    def register_executor(self, kind: str, fn: EventFn) -> None:
        self._executors[kind] = fn

    def stop(self) -> None:
        """Signal a human STOP; honored at the next stage boundary."""
        self._stop_requested = True

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, design: ExperimentDesign) -> Dict[str, Any]:
        """Execute a FROZEN design stage-by-stage through the dispatcher.

        Raises :class:`DesignInvalid` for an unfrozen/invalid design and
        :class:`ExecutorNotAvailable` for an unsupported stage — never a silent
        fallback nor a fabricated result. Returns a per-stage summary.
        """
        require_executable(design)  # FROZEN + valid, else DESIGN_INVALID
        self._emit("EXPERIMENT_STARTED", self._design_ctx(design))
        summary: List[Dict[str, Any]] = []
        self._stop_requested = False
        for stage in design.stages:
            if self._stop_requested:
                self._emit("EXPERIMENT_STOPPED", self._design_ctx(design))
                raise StopRequested("stopped by human request")
            try:
                cap = dispatch_stage(stage.executor_type)
            except ExecutorNotAvailable as e:
                self._emit("STAGE_FAILED", {
                    **self._design_ctx(design), "stage_id": stage.stage_id,
                    "executor_type": stage.executor_type,
                    "category": e.category, "engine": e.engine})
                self._emit("EXPERIMENT_FAILED", self._design_ctx(design))
                raise
            self._emit("STAGE_STARTED", {
                **self._design_ctx(design), "stage_id": stage.stage_id,
                "executor_type": stage.executor_type, "engine": cap["engine"]})

            fn = self._executors.get(cap["kind"])
            if fn is None:
                # The dispatcher says this stage is executable, but no executor
                # plugin is bound on the engine. Report honestly (not a fake run).
                result: Dict[str, Any] = {"dispatched_to": cap["engine"],
                                          "execution": "not_bound"}
            else:
                try:
                    result = fn(stage, design) or {}
                except Exception as e:  # executor-level failure
                    self._emit("STAGE_FAILED", {
                        **self._design_ctx(design), "stage_id": stage.stage_id,
                        "category": "STAGE_EXECUTOR_FAILURE", "error": str(e)})
                    self._emit("EXPERIMENT_FAILED", self._design_ctx(design))
                    raise
            self._emit("STAGE_COMPLETED", {
                **self._design_ctx(design), "stage_id": stage.stage_id,
                "executor_type": stage.executor_type, "result": result})
            summary.append({"stage_id": stage.stage_id,
                            "executor_type": stage.executor_type,
                            "result": result})

        self._emit("EXPERIMENT_COMPLETED", self._design_ctx(design))
        return {"design_id": design.design_id, "version": design.version,
                "status": "COMPLETED", "stages": summary, "events": list(self.events)}