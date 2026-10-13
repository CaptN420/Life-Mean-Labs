"""In-memory feedback store for long experimental runs (OPT-IN experimental).

A run can take a long time (e.g. 30 LLM tours). Instead of blocking on one
synchronous POST, the API starts the run in a background thread that publishes
a *feedback event* as each stage/tour completes, and the UI polls a lightweight
endpoint to render a live timeline ("what is happening, where, and the text").

This store is deliberately small, in-memory, thread-safe and single-process —
appropriate for the single-threaded dashboard server. It never persists and the
stable core does not depend on it.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_EXPIRY_S = 600  # feedback entries older than this are pruned


class RunFeedbackStore:
    """Thread-safe map run_id -> feedback entry, with auto-pruning."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: Dict[str, Dict[str, Any]] = {}

    def create(self) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._prune_locked()
            self._runs[run_id] = {
                "run_id": run_id,
                "created": time.time(),
                "status": "running",  # running | passed | failed | inconclusive | error
                "executor": "",
                "events": [],       # one per tour/stage, in order
                "result": None,     # set when finished
            }
        return run_id

    def set_meta(self, run_id: str, executor: str, message: str = "") -> None:
        with self._lock:
            e = self._runs.get(run_id)
            if not e:
                return
            e["executor"] = executor
            if message:
                e["events"].append({"ts": time.time(), "kind": "meta", "text": message})

    def add_event(self, run_id: str, text: str, tour: Optional[int] = None,
                  kind: str = "tour", **extra: Any) -> None:
        """Append a feedback event (e.g. 'tour 3/30 -> PASS hash=...')."""
        with self._lock:
            e = self._runs.get(run_id)
            if not e:
                return
            e["events"].append({"ts": time.time(), "kind": kind, "text": text,
                                "tour": tour, **extra})

    def finish(self, run_id: str, status: str, result: Any) -> None:
        with self._lock:
            e = self._runs.get(run_id)
            if not e:
                return
            e["status"] = status
            e["result"] = result

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            e = self._runs.get(run_id)
            if not e:
                return None
            return {
                "run_id": e["run_id"], "status": e["status"],
                "executor": e["executor"],
                "result": e["result"],
                "events": list(e["events"]),
            }

    def _prune_locked(self) -> None:
        now = time.time()
        stale = [rid for rid, e in self._runs.items()
                 if now - e["created"] > _EXPIRY_S]
        for rid in stale:
            del self._runs[rid]


# A single shared store for the (single-threaded) HTTP server; tests may inject
# their own via ``handler.experimental_feedback``.
STORE = RunFeedbackStore()
