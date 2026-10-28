"""Real engine runner for Life_mean Studio.

This module wires the Studio's Quick Run / RUN / STOP controls to the REAL
Life_mean experiment engine (`experiments.ui_controller.ExperimentUIController`),
so a run genuinely executes the multi-agent / deterministic pipeline it is not
a visual stub.

It is deliberately Qt-free: all orchestration lives here in pure Python so it
can be unit-tested headlessly. The GUI layer only consumes
:meth:`StudioRunner.drain_events` / :meth:`StudioRunner.status` via a Qt timer.

Design / threading notes
------------------------
* ``RUN``  -> register + start an experiment on the real controller, and record
  the run in the Studio's own SQLite (``sessions`` + ``event_references``) so
  it shows up in history. No subprocess, no network server execution runs in
  a controller-owned background thread inside this process.
* ``STOP`` -> real cooperative cancellation via ``controller.stop_experiment()``.
* The engine invokes our subscription callback on its OWN thread WHILE holding
  its internal lock. That callback must therefore NEVER re-enter the controller
  (e.g. ``get_experiment``) or it deadlocks. We only mark the run as finished
  and enqueue an event; the actual finalization (read state -> write session ->
  compute status) happens lazily on the calling thread via ``_maybe_finalize``,
  which calls the controller with NO runner lock held (no lock-order cycle).
* Two independent locks: ``_lock`` guards active-run bookkeeping; ``_event_lock``
  guards the event queue + handlers. They are never held while calling the
  controller, so there is no circular wait with the controller's own lock.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("LifeMean.Studio.Runner")


class RunnerError(RuntimeError):
    """Raised for invalid run requests (e.g. already busy)."""


class StudioRunner:
    """Orchestrates real experiment runs for the Studio UI."""

    def __init__(self, storage: Any, controller: Any = None) -> None:
        """
        Args:
            storage: A ``life_mean_studio.engine.storage.StudioStorage`` instance
                (records sessions/events for every run).
            controller: The real ``ExperimentUIController``; injectable for tests.
        """
        if controller is None:
            from experiments.ui_controller import ExperimentUIController
            controller = ExperimentUIController()
        self.storage = storage
        self.controller = controller

        # Active-run bookkeeping (RLock so nested snapshots are safe).
        self._lock = threading.RLock()
        self._active_id: Optional[str] = None
        self._active_session: Optional[str] = None
        self._active_workflow: Optional[str] = None
        self._stop_requested = False
        self._finished_id: Optional[str] = None
        self._finalized: set = set()

        # Event queue + handlers (own lock, never held across a controller call).
        self._event_lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []
        self._handlers: List[Callable[[str, Dict[str, Any]], None]] = []

    # ------------------------------------------------------------------ config

    @staticmethod
    def build_config(workflow: Any = None, **overrides: Any) -> Dict[str, Any]:
        """Translate a workflow (dict / WorkflowConfig) into an engine config.

        Overrides win over values derived from the workflow, so the GUI can e.g.
        force the execution mode independently of the stored workflow.
        """
        if isinstance(workflow, dict):
            base = workflow.get("config", workflow)
        elif workflow is not None and hasattr(workflow, "to_dict"):
            base = workflow.to_dict()
        else:
            base = {}

        def _get(keys, default):
            for k in keys:
                if isinstance(base, dict) and base.get(k) is not None:
                    return base[k]
            return default

        debate = str(_get(["mode"], "single")).lower() == "multi"
        config = {
            "seed": int(_get(["seed"], 42)),
            "domain": str(_get(["domain"], "math")),
            "difficulty_range": [1, 5],
            "num_tasks": int(_get(["num_tasks"], 10)),
            "debate": debate,
        }
        model = _get(["llm_model"], None)
        if model:
            config["llm_model"] = model
        config.update(overrides)
        return config

    # ------------------------------------------------------------------ public

    def is_active(self) -> bool:
        self._maybe_finalize()
        with self._lock:
            return self._active_id is not None

    def start(self, config: Dict[str, Any],
              workflow_id: Optional[str] = None) -> str:
        """Register + start a real experiment run.

        Returns the experiment id. Raises :class:`RunnerError` if a run is
        already in progress (one run at a time via Quick Run).
        """
        self._maybe_finalize()
        with self._lock:
            if self._active_id is not None:
                raise RunnerError("A run is already in progress stop it first.")
            experiment_id = f"studio_{uuid.uuid4().hex[:12]}"
            session_id = self.storage.create_session(workflow_id=workflow_id)
            self._active_id = experiment_id
            self._active_session = session_id
            self._active_workflow = workflow_id
            self._stop_requested = False

        # Register + subscribe before starting so no event can be missed.
        self.controller.register_experiment(experiment_id, config)
        self.controller.subscribe(
            experiment_id, "started",
            lambda data, eid=experiment_id: self._on_engine_event(eid, "started", data))
        self.controller.subscribe(
            experiment_id, "stopped",
            lambda data, eid=experiment_id: self._on_engine_event(eid, "stopped", data))

        self.storage.update_session(session_id, {"status": "running"})
        self.storage.add_event_reference(
            "experiment.started", session_id=session_id, run_id=experiment_id,
            payload={"config": config, "workflow_id": workflow_id})

        ok = self.controller.start_experiment(experiment_id)
        if not ok:
            with self._lock:
                self._active_id = None
                self._active_session = None
                self._active_workflow = None
            self.storage.update_session(session_id, {"status": "failed"})
            raise RunnerError(f"Engine refused to start experiment {experiment_id}")

        self._enqueue("started", {"experiment_id": experiment_id, "config": config})
        logger.info("StudioRunner started %s (session %s)", experiment_id, session_id)
        return experiment_id

    def stop(self) -> bool:
        """Request a real cancellation of the active run."""
        self._maybe_finalize()
        with self._lock:
            exp_id = self._active_id
            self._stop_requested = True
        if exp_id is None:
            return False
        self._enqueue("stop_requested", {"experiment_id": exp_id})
        return self.controller.stop_experiment(exp_id)

    def status(self) -> Dict[str, Any]:
        """Snapshot of the active run state (or empty dict when idle)."""
        self._maybe_finalize()
        with self._lock:
            exp_id = self._active_id
            session_id = self._active_session
        if exp_id is None:
            return {}
        st = self.controller.get_experiment(exp_id)
        return {
            "experiment_id": exp_id,
            "session_id": session_id,
            "is_running": bool(st.is_running) if st else False,
            "state": st.to_dict() if st else {},
            "stop_requested": self._stop_requested,
        }

    def subscribe(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register a handler called as ``callback(event, data)`` for every event."""
        with self._event_lock:
            self._handlers.append(callback)

    def drain_events(self) -> List[Dict[str, Any]]:
        """Return and clear all queued events (consumed by the GUI)."""
        self._maybe_finalize()
        with self._event_lock:
            events, self._events = self._events, []
        return events

    # ------------------------------------------------------------------ events

    def _on_engine_event(self, experiment_id: str, event: str, _data: Dict[str, Any]) -> None:
        """Engine-layer callback, runs on an engine thread holding the controller
        lock. MUST NOT re-enter the controller  it only marks the run as
        finished and enqueues a low-level event. Real work happens lazily in
        :meth:`_maybe_finalize` on the calling thread."""
        with self._lock:
            if experiment_id != self._active_id:
                return
            if event == "stopped":
                self._finished_id = experiment_id
                self._enqueue("engine_finished", {"experiment_id": experiment_id})

    def _maybe_finalize(self) -> None:
        """Finalize a finished run on the CALLING thread (never on the engine
        callback thread). Safe to call from is_active/status/start/stop/drain."""
        with self._lock:
            eid = self._finished_id
            if eid is None:
                return
            if eid in self._finalized:
                return
            self._finalized.add(eid)
            session_id = self._active_session
            was_stopped = self._stop_requested

        # Read state WITHOUT holding any runner lock (controller lock is free
        # here  we are not inside the engine's notify callback).
        state = self.controller.get_experiment(eid)
        errors = state.errors if state is not None else []
        metrics = state.to_dict() if state is not None else {}

        if errors:
            status = "failed"
        elif was_stopped:
            status = "cancelled"
        else:
            status = "completed"

        if session_id:
            try:
                self.storage.update_session(session_id, {"status": status})
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Could not finalize session %s: %s", session_id, exc)
        try:
            self.storage.add_event_reference(
                "experiment.finished", session_id=session_id, run_id=eid,
                payload={"status": status, "metrics": metrics})
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Could not record finish event: %s", exc)

        with self._lock:
            self._active_id = None
            self._active_session = None
            self._active_workflow = None
            self._finished_id = None

        self._enqueue("finished", {"experiment_id": eid, "status": status, "metrics": metrics})
        logger.info("StudioRunner finalized %s -> %s", eid, status)

    def _enqueue(self, event: str, data: Dict[str, Any]) -> None:
        with self._event_lock:
            self._events.append({"event": event, "data": data, "ts": time.time()})
            handlers = list(self._handlers)
        for handler in handlers:
            try:
                handler(event, data)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Runner handler error: %s", exc)