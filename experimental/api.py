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

    # ── collaborators ──────────────────────────────────────────────────────
    def _exp_store(self) -> ExperimentDesignStore:
        return self.experimental_store or _STORE

    def _exp_engine(self):
        return self.experimental_engine or build_engine()

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

    # ── routing helpers (used by dashboard do_GET / do_POST) ───────────────
    @classmethod
    def match_design_id(cls, path: str) -> Optional[str]:
        m = _ID_RE.match(path)
        return m.group(1) if m else None