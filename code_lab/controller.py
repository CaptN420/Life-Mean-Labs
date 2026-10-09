"""Code Lab controller — run registry, lifecycle, API-facing state.

Manages multiple Code Lab runs, runs them in background threads, and exposes
state/events for the HTTP API and UI (mirrors ExperimentUIController patterns).
"""

from __future__ import annotations

import logging
import threading
import time
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
        return view.to_dict() if view else None

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
