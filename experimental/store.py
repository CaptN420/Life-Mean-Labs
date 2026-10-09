"""ExperimentDesignStore — holds designs for the sandbox API.

In-memory store keyed by design_id (thread-safe enough for the single-threaded
HTTP server). Direct mutation is impossible by design: every lifecycle change
goes through ``transition`` which returns a NEW design and marks the old one
SUPERSEDED / keeps the frozen one immutable. A future persistence layer can
swap the backing store without touching callers.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

from experimental.schema import DESIGN_STATES, ExperimentDesign


class ExperimentDesignStore:
    def __init__(self) -> None:
        self._designs: Dict[str, ExperimentDesign] = {}
        self._lock = threading.Lock()

    def save(self, design: ExperimentDesign) -> ExperimentDesign:
        with self._lock:
            self._designs[design.design_id] = design
        return design

    def get(self, design_id: str) -> Optional[ExperimentDesign]:
        with self._lock:
            d = self._designs.get(design_id)
            return d.clone() if d is not None else None

    def list(self) -> list:
        with self._lock:
            items = [d.to_dict() for d in self._designs.values()]
        items.sort(key=lambda d: d.get("design_id", ""))
        return items

    def transition(self, design_id: str, target: str) -> ExperimentDesign:
        """Advance a design's lifecycle. Returns the new design; the previous
        snapshot stays in the store (frozen stays frozen / SUPERSEDED is the
        terminal marker for a replaced version). Raises DesignStateError."""
        if target not in DESIGN_STATES:
            raise ValueError(f"invalid target state '{target}'")
        with self._lock:
            cur = self._designs.get(design_id)
            if cur is None:
                raise KeyError(design_id)
            nxt = cur.transition(target)
            self._designs[design_id] = nxt
            return nxt