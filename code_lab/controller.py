"""Code Lab controller — run registry, lifecycle, API-facing state.

Manages multiple Code Lab runs, runs them in background threads, and exposes
state/events for the HTTP API and UI (mirrors ExperimentUIController patterns).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import CodeLabConfig
from .engine import CodeLabEngine, build_default_engine
from .workspace import CodeLabWorkspace

logger = logging.getLogger("CodeLab.Controller")


class CodeLabRunView:
    """Immutable-ish snapshot of a run's public state for the UI/API."""

    def __init__(self, run_id: str, status: str, config: Dict[str, Any]) -> None:
        self.run_id = run_id
        self.status = status
        self.config = config
        self.created_at = config.get("created_at", "")
        self.events: List[Dict[str, Any]] = []
        self.result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "config": self.config,
            "events": self.events,
            "result": self.result,
        }


class CodeLabController:
    """Owns all Code Lab runs in a session; thread-safe."""

    # Bounded size of the lab-wide event log (oldest entries are evicted).
    TIMELINE_LIMIT = 500

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._runs: Dict[str, CodeLabRunView] = {}
        self._engines: Dict[str, CodeLabEngine] = {}
        self._stop_flags: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._base_dir = base_dir
        # Lab-wide consolidated event log: every real run event across all runs.
        # Each entry carries `run_id` + `time`; backend-real, never synthesized.
        self._timeline: List[Dict[str, Any]] = []

    # ── run management ─────────────────────────────────────────────────────
    def create_run(self, config: CodeLabConfig) -> CodeLabRunView:
        """Register a new run (idle) and return its view."""
        with self._lock:
            cfg = config
            view = CodeLabRunView(cfg.run_id, "pending", cfg.to_dict())
            self._runs[cfg.run_id] = view
            return view

    def start_run(
        self,
        run_id: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        wait: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Start a run. If wait=True, runs synchronously and returns the result."""
        view = self._runs.get(run_id)
        if view is None:
            return None
        config = CodeLabConfig.from_dict(view.config)

        def handler(ev: Dict[str, Any]) -> None:
            with self._lock:
                view.events.append(ev)
                if ev["type"] == "RUN_COMPLETED":
                    view.status = "passed"
                elif ev["type"] == "RUN_FAILED":
                    view.status = "failed"
                elif ev["type"] == "RUN_STOPPED":
                    view.status = "stopped"
                # Also record on the lab-wide timeline (backend-real event).
                self._timeline.append(ev)
                if len(self._timeline) > self.TIMELINE_LIMIT:
                    self._timeline = self._timeline[-self.TIMELINE_LIMIT:]
            if on_event is not None:
                try:
                    on_event(ev)
                except Exception as e:  # pragma: no cover
                    logger.warning("on_event failed: %s", e)

        engine = build_default_engine(config, event_handler=handler, base_dir=self._base_dir)
        with self._lock:
            self._engines[run_id] = engine
            view.status = "running"
            self._stop_flags.setdefault(run_id, threading.Event())

        if wait:
            result = engine.run()
            with self._lock:
                view.status = result["status"]
                view.result = result
            return result

        t = threading.Thread(target=self._run_worker, args=(run_id, engine, view), daemon=True)
        t.start()
        return None

    def _run_worker(self, run_id: str, engine: CodeLabEngine, view: CodeLabRunView) -> None:
        try:
            result = engine.run()
            with self._lock:
                view.status = result["status"]
                view.result = result
        except Exception as e:  # pragma: no cover
            logger.exception("run worker crashed")
            with self._lock:
                view.status = "failed"
                view.result = {"run_id": run_id, "status": "failed", "error": str(e)}
        finally:
            self._stop_flags.pop(run_id, None)

    def stop_run(self, run_id: str) -> bool:
        """Request cooperative stop of a running engine."""
        with self._lock:
            engine = self._engines.get(run_id)
            view = self._runs.get(run_id)
        if engine is None:
            return False
        engine.request_stop()
        if view is not None:
            view.status = "stopping"
        return True

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        view = self._runs.get(run_id)
        if view is None:
            return None
        data = view.to_dict()
        # Conversation-first surface (mirrors Debate Lab): the canonical
        # conversation is derived ONLY from real backend events, joined with
        # the full agent responses from the backend-real agent_trace — never
        # reconstructed from template/workflow/status.
        data["conversation"] = self._build_conversation(view.events, view.result)
        return data

    def _build_conversation(self, events: List[Dict[str, Any]],
                            result: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Derive the canonical Code Lab conversation from backend events.

        Only real events produce entries. Full visible agent responses come
        from ``result.agent_trace`` (backend-real, written by the agents),
        matched to AGENT_RESPONSE / AGENT_FAILED events per-role in sequence so
        retries (DEVELOPER attempt 2) and the REVIEWER/JUDGE stages align. If a
        response was never produced (failure / deterministic path), no text is
        fabricated — ``response`` stays None and the UI shows the honest status.
        """
        # Per-role FIFO of agent_trace entries (agent -> list of turn results).
        trace: Dict[str, deque] = defaultdict(deque)
        for tr in (result or {}).get("agent_trace") or []:
            role = tr.get("agent") or tr.get("role")
            if role:
                trace[role].append(tr)

        conv: List[Dict[str, Any]] = []
        for idx, ev in enumerate(events):
            t = ev.get("type")
            base: Dict[str, Any] = {
                "event_index": idx,
                "time": ev.get("time"),
                "run_id": ev.get("run_id"),
            }
            if t == "RUN_STARTED":
                conv.append({**base, "type": "RUN_STARTED", "role": None, "stage": None,
                             "model": None, "turn": None, "response": None,
                             "message": "Run started", "detail": {
                                 "llm_available": ev.get("llm_available")}})
            elif t == "AGENT_RESPONSE":
                role = ev.get("role")
                tr = trace[role].popleft() if role in trace else None
                conv.append({**base, "type": "AGENT_RESPONSE", "role": role,
                             "stage": ev.get("stage"),
                             "model": ev.get("model"),
                             "configured_model": ev.get("configured_model"),
                             "selection_mode": ev.get("selection_mode"),
                             "duration_ms": ev.get("duration_ms"),
                             "finish_reason": ev.get("finish_reason"),
                             "attempt": (tr or {}).get("attempt"),
                             "turn": None,
                             "response": ev.get("response") or (tr or {}).get("response")})
            elif t == "AGENT_FAILED":
                role = ev.get("role")
                tr = trace[role].popleft() if role in trace else None
                conv.append({**base, "type": "AGENT_FAILED", "role": role,
                             "stage": ev.get("stage"),
                             "model": ev.get("model"),
                             "configured_model": ev.get("configured_model"),
                             "selection_mode": ev.get("selection_mode"),
                             "duration_ms": ev.get("duration_ms"),
                             "error_type": ev.get("error_type"),
                             "message": ev.get("message"),
                             "turn": None,
                             "response": ev.get("response") or (tr or {}).get("response")})
            elif t == "PLAN_CREATED":
                conv.append({**base, "type": "PLAN", "role": "PLANNER", "stage": "plan",
                             "model": None, "turn": None, "response": None,
                             "router": ev.get("router"),
                             "plan": ev.get("plan")})
            elif t == "AGENT_SELECTED":
                conv.append({**base, "type": "AGENT_SELECTED", "role": None, "stage": None,
                             "model": None, "turn": None, "response": None,
                             "detail": {
                                 "roles": ev.get("roles"),
                                 "template_id": ev.get("template_id"),
                                 "template_version": ev.get("template_version"),
                                 "template_hash": ev.get("template_hash")}})
            elif t in ("FILE_CREATED", "FILE_MODIFIED"):
                conv.append({**base, "type": "FILE_EVENT", "role": ev.get("by_agent"),
                             "stage": ev.get("operation") or t,
                             "model": None, "turn": ev.get("iteration"), "response": None,
                             "detail": {"file": ev.get("file") or (ev.get("files") or []),
                                        "operation": ev.get("operation")}})
            elif t in ("TEST_STARTED", "TEST_PASSED", "TEST_FAILED"):
                conv.append({**base, "type": "TEST", "role": "TEST_RUNNER", "stage": "test",
                             "model": None, "turn": ev.get("iteration"), "response": None,
                             "detail": {"status": t,
                                        "passed": ev.get("passed"),
                                        "failures": ev.get("failures"),
                                        "total": ev.get("total")}})
            elif t in ("CRITIQUE_STARTED", "REPAIR_STARTED"):
                conv.append({**base, "type": "PHASE", "role": "CRITIC" if t == "CRITIQUE_STARTED" else "REPAIR",
                             "stage": t.split("_STARTED")[0].lower(),
                             "model": None, "turn": ev.get("iteration"), "response": None,
                             "message": t.replace("_STARTED", "").title()})
            elif t == "VALIDATION_COMPLETED":
                conv.append({**base, "type": "VALIDATION", "role": None, "stage": "validation",
                             "model": None, "turn": None, "response": None,
                             "detail": ev.get("results")})
            elif t == "JUDGE_COMPLETED":
                conv.append({**base, "type": "JUDGE", "role": "JUDGE", "stage": "judge",
                             "model": None, "turn": None, "response": None,
                             "message": "Semantic judge verdict",
                             "detail": {"verdict": ev.get("verdict")}})
            elif t in ("RUN_COMPLETED", "RUN_FAILED", "RUN_STOPPED"):
                detail = {k: ev.get(k) for k in (
                    "status", "files_created", "iterations", "error_count",
                    "stage_reached", "deterministic_validation", "semantic_judge_status",
                ) if ev.get(k) is not None}
                conv.append({**base, "type": "TERMINAL", "role": None, "stage": None,
                             "model": None, "turn": None, "response": None,
                             "message": t.replace("_", " ").title(), "detail": detail})
        return conv

    def read_raw(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Read the immutable RAW snapshot + trajectory for a run (from disk).

        RAW is the source of truth: the immutable ``run_<id>.json`` snapshot
        plus the append-only ``trajectory.jsonl`` written by the engine.
        Returns None if the run is unknown.
        """
        view = self._runs.get(run_id)
        if view is None:
            return None
        try:
            ws = CodeLabWorkspace(CodeLabConfig.from_dict(view.config), base_dir=self._base_dir)
            snapshot = None
            sp = ws.raw / f"run_{run_id}.json"
            if sp.exists():
                snapshot = json.loads(sp.read_text(encoding="utf-8"))
            return {"run_id": run_id, "snapshot": snapshot,
                    "trajectory": ws.read_raw("trajectory")}
        except Exception as e:  # pragma: no cover
            logger.warning("read_raw failed for %s: %s", run_id, e)
            return {"run_id": run_id, "snapshot": None, "trajectory": [],
                    "error": str(e)}

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._runs[r].to_dict() for r in sorted(self._runs)]

    def list_files(self, run_id: str) -> Optional[List[str]]:
        """List source files in the run workspace (from disk, source of truth).

        Filters out __pycache__ bytecode noise so the UI shows meaningful files.
        """
        view = self._runs.get(run_id)
        if view is None:
            return None
        try:
            ws = CodeLabWorkspace(CodeLabConfig.from_dict(view.config), base_dir=self._base_dir)
            return [f for f in ws.list_files() if "__pycache__" not in f and not f.endswith(".pyc")]
        except Exception as e:  # pragma: no cover
            logger.warning("list_files failed for %s: %s", run_id, e)
            return []

    def read_file(self, run_id: str, rel_path: str) -> Optional[str]:
        view = self._runs.get(run_id)
        if view is None:
            return None
        try:
            ws = CodeLabWorkspace(CodeLabConfig.from_dict(view.config), base_dir=self._base_dir)
            return ws.read_text(rel_path)
        except Exception as e:  # pragma: no cover
            logger.warning("read_file failed: %s", e)
            return None

    def cleanup_run(self, run_id: str) -> bool:
        """Delete a run workspace + unregister (explicit user action; rule 9)."""
        view = self._runs.get(run_id)
        if view is None:
            return False
        try:
            ws = CodeLabWorkspace(CodeLabConfig.from_dict(view.config), base_dir=self._base_dir)
            ws.cleanup()
        except Exception as e:  # pragma: no cover
            logger.warning("cleanup failed: %s", e)
        with self._lock:
            self._runs.pop(run_id, None)
            self._engines.pop(run_id, None)
        return True

    def get_timeline(self, limit: int = 200) -> Dict[str, Any]:
        """Return the lab-wide consolidated event log, newest-last.

        Each event is a backend-real dict carried over from the per-run callback
        chain (type, time, run_id, role/tool/model metadata where applicable).
        Large payload fields (source, tests, plan, response) are stripped so the
        timeline stays a diagnostic surface, not a data dump. ``count`` is the
        total number of events recorded this session (may exceed ``limit``).
        """
        with self._lock:
            total = len(self._timeline)
            trimmed = []
            for ev in self._timeline[-limit:]:
                trimmed.append(
                    {k: v for k, v in ev.items()
                     if k not in ("source", "tests", "plan", "result", "response", "code")}
                )
            runs_count = len({ev["run_id"] for ev in self._timeline if "run_id" in ev})
        return {"events": trimmed, "count": total, "total_events": total, "runs_count": runs_count}

    def get_dashboard_data(self) -> Dict[str, Any]:
        runs = self.list_runs()
        running = sum(1 for r in runs if r["status"] in ("running", "pending", "stopping"))
        return {
            "total_runs": len(runs),
            "running_count": running,
            "runs": runs,
        }
