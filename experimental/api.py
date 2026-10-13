"""Sandbox API handlers — a mixin the dashboard handler inherits.

Endpoints (all human-gated, spec §15):
  GET  /api/experimental/capabilities      -> what executors are connected
  GET  /api/experimental/designs           -> list designs
  GET  /api/experimental/designs/{id}      -> one design
  POST /api/experimental/designs           -> designer.propose -> DRAFT (never runs)
  POST /api/experimental/designs/{id}/transition  {target}  -> lifecycle step
  POST /api/experimental/designs/{id}/run          -> only when FROZEN

The run endpoint executes through the REAL Code Lab / ToolWorker adapters via
:func:`experimental.executors.build_engine`. A non-frozen design cannot run
(400 DESIGN_INVALID); an unconnected stage fails with EXECUTOR_NOT_AVAILABLE.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from experimental.designer import ExperimentDesigner, DesignerInputError
from experimental.dispatch import ExecutorNotAvailable, executor_catalog
from experimental.engine import StopRequested
from experimental.executors import build_engine
from experimental.harness import run_executor
from experimental.schema import ExperimentDesign
from experimental.store import ExperimentDesignStore
from experimental.validation import DesignInvalid

# A single shared store for the (single-threaded) HTTP server; tests may inject
# their own via ``handler.experimental_store`` / ``handler.experimental_engine``.
_STORE = ExperimentDesignStore()
_ID_RE = re.compile(r"^/api/experimental/designs/([^/]+)$")


class ExperimentalApiMixin:
    """Mixin providing the /api/experimental/* handlers."""

    experimental_store: Any = None
    experimental_engine: Any = None
    experimental_feedback: Any = None

    # ── collaborators ──────────────────────────────────────────────────────
    def _exp_store(self) -> ExperimentDesignStore:
        return self.experimental_store or _STORE

    def _exp_engine(self):
        return self.experimental_engine or build_engine()

    def _exp_feedback(self):
        from experimental.feedback import STORE
        return self.experimental_feedback or STORE

    # ── GET ────────────────────────────────────────────────────────────────
    def _experimental_capabilities(self) -> None:
        catalogs = executor_catalog()
        try:
            from experiments.settings import model_pools
            pools = model_pools()
        except Exception:  # pragma: no cover
            pools = {}
        self._send_json({
            "executors": catalogs,
            "connected_executors": sorted(
                et for et, c in catalogs.items() if c.get("connected")),
            "model_domains": list(pools),
        })

    def _experimental_designs(self) -> None:
        self._send_json({"designs": self._exp_store().list()})

    def _experimental_design_get(self, design_id: str) -> None:
        d = self._exp_store().get(design_id)
        if d is None:
            self._send_error(404, f"design {design_id} not found", code="not_found")
            return
        self._send_json({"design": d.to_dict()})

    # ── POST ───────────────────────────────────────────────────────────────
    def _experimental_design_create(self, data: Dict[str, Any]) -> None:
        description = (data or {}).get("description", "")
        research_question = (data or {}).get("research_question", "")
        designer = ExperimentDesigner(
            capabilities=(data or {}).get("capabilities", {}))
        try:
            design = designer.propose(description, research_question)
        except DesignerInputError as e:
            self._send_error(400, str(e), code="designer_input")
            return
        self._exp_store().save(design)
        self._send_json({"design_id": design.design_id,
                         "status": design.status, "design": design.to_dict()})

    def _experimental_design_transition(self, design_id: str, data: Dict[str, Any]) -> None:
        target = (data or {}).get("target", "")
        try:
            nxt = self._exp_store().transition(design_id, target)
        except KeyError:
            self._send_error(404, f"design {design_id} not found", code="not_found")
            return
        except ValueError as e:
            self._send_error(400, str(e), code="invalid_transition")
            return
        self._send_json({"design_id": nxt.design_id, "status": nxt.status,
                         "frozen": nxt.is_frozen, "design": nxt.to_dict()})

    def _experimental_design_run(self, design_id: str) -> None:
        d = self._exp_store().get(design_id)
        if d is None:
            self._send_error(404, f"design {design_id} not found", code="not_found")
            return
        engine = self._exp_engine()
        try:
            summary = engine.run(d)
        except DesignInvalid as e:
            self._send_error(400, str(e), code="DESIGN_INVALID")
            return
        except ExecutorNotAvailable as e:
            self._send_error(422, str(e), code=e.category)
            return
        except StopRequested:
            self._send_json({"design_id": design_id, "status": "STOPPED"})
            return
        self._send_json(summary)

    def _experimental_harness(self, data: Dict[str, Any]) -> None:
        """Run a single connected executor in an isolated, throwaway sandbox.

        Body: ``{executor: <executor_type>, prompt?, tool?, args?, run_tests?...}``
        A ``not-connected`` executor is refused with EXECUTOR_NOT_AVAILABLE
        (422) — never faked. This is an OPT-IN experimental surface; the stable
        core does not depend on it.
        """
        executor_type = str((data or {}).get("executor") or "")
        if not executor_type:
            self._send_error(400, "missing 'executor'", code="missing_executor")
            return
        try:
            out = run_executor(executor_type, data or {})
        except ExecutorNotAvailable as e:
            self._send_error(422, str(e), code=e.category)
            return
        except Exception as e:  # pragma: no cover - defensive
            self._send_error(500, str(e), code="harness_error")
            return
        self._send_json(out)

    def _experimental_harness_start(self, data: Dict[str, Any]) -> None:
        """Start a harness run in a background thread, returning a ``run_id``
        immediately. The UI polls ``GET /api/experimental/feedback/<run_id>``
        to render a live timeline for long runs (e.g. ``llm_sweep``).
        """
        from experimental.feedback import RunFeedbackStore

        executor_type = str((data or {}).get("executor") or "")
        if not executor_type:
            self._send_error(400, "missing 'executor'", code="missing_executor")
            return
        store: RunFeedbackStore = self._exp_feedback()
        run_id = store.create()
        store.set_meta(run_id, executor_type,
                       f"started executor={executor_type}")

        import threading

        def _worker():
            try:
                status = "inconclusive"
                result = None
                try:
                    out = run_executor(executor_type, data or {},
                                       feedback_store=store, run_id=run_id)
                    status = out.get("status", "inconclusive")
                    result = out
                except ExecutorNotAvailable as e:
                    status = "error"
                    result = {"error": str(e), "code": e.category}
                except Exception as e:  # pragma: no cover - defensive
                    status = "error"
                    result = {"error": str(e)}
                store.finish(run_id, status, result)
            except Exception:  # pragma: no cover
                store.finish(run_id, "error", {"error": "worker crashed"})

        threading.Thread(target=_worker, daemon=True).start()
        self._send_json({"run_id": run_id, "status": "running",
                         "executor": executor_type})

    def _experimental_feedback_get(self, run_id: str) -> None:
        """Return the live feedback entry for a run (to be polled by the UI)."""
        from experimental.feedback import RunFeedbackStore

        entry = self._exp_feedback().get(run_id)
        if entry is None:
            self._send_error(404, f"run '{run_id}' not found", code="not_found")
            return
        self._send_json(entry)

    # ── routing helpers (used by dashboard do_GET / do_POST) ───────────────
    @classmethod
    def match_design_id(cls, path: str) -> Optional[str]:
        m = _ID_RE.match(path)
        return m.group(1) if m else None