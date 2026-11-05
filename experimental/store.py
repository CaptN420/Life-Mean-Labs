"""ExperimentDesignStore — durable, versioned store for experiment designs.

Designs are the frozen contract of an experiment, so they must survive a
process restart: a manifest that only lives in RAM cannot serve
reproducibility. This store keeps the same API as before (``save`` / ``get`` /
``list`` / ``transition``) and adds a disk backing store plus version history.

Layout (one file per design version, so a FROZEN snapshot is never overwritten):

    <root>/<design_id>.v<version>.json   e.g. DESIGN-AB12CD34EF56.v1.json
    <root>/<design_id>.v<version>.json   ...v2.json (after a transition)

Envelope::

    {"schema": "experiment-design/1", "saved_at": <unix ts>, "design": {...}}

Rules:
  * every write is atomic (tmp file + ``os.replace``) — a crash never leaves a
    half-written design on disk;
  * a write failure RAISES (``DesignStoreError``) instead of pretending success
    — no silent fallback;
  * a corrupt file on startup is skipped with a warning, never guessed at;
  * in-memory state is the cached latest version per design_id; ``history()``
    exposes every persisted version.

In a container this must point at a mounted volume (the dashboard mounts
``/app/data``), otherwise the durability guarantee is cosmetic.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from experimental.schema import DESIGN_STATES, ExperimentDesign

logger = logging.getLogger("experimental.store")

SCHEMA = "experiment-design/1"
_ENV_ROOT = "LIFE_MEAN_DESIGNS_DIR"

# Lifecycle rank: used to pick "latest" when a version has multiple lifecycle
# snapshots on disk (DRAFT -> ... -> FROZEN), and to order history.
_STATUS_RANK = {
    "DRAFT": 0, "REVIEWED": 1, "APPROVED": 2, "FROZEN": 3,
    "REJECTED": 4, "SUPERSEDED": 5,
}


def _rank(design: ExperimentDesign) -> tuple:
    return (int(design.version), _STATUS_RANK.get(design.status, -1))


class DesignStoreError(RuntimeError):
    """Raised when a design could not be persisted (never silently swallowed)."""


def _default_root() -> Path:
    """Resolve the designs directory.

    Precedence: ``LIFE_MEAN_DESIGNS_DIR`` env var, then ``<repo>/data/
    experiments/designs``. The repo root is derived from this file so the
    location does not depend on the process CWD.
    """
    env = os.environ.get(_ENV_ROOT)
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "data" / "experiments" / "designs"


class ExperimentDesignStore:
    def __init__(self, root: Optional[Path] = None, *, autoload: bool = True) -> None:
        self.root = Path(root) if root is not None else _default_root()
        self._designs: Dict[str, ExperimentDesign] = {}
        self._versions: Dict[str, Dict[int, str]] = {}  # design_id -> {version: path}
        self._lock = threading.Lock()
        if autoload:
            self._load()

    # ── disk helpers ──────────────────────────────────────────────────────
    def _path_for(self, design: ExperimentDesign) -> Path:
        # Version AND lifecycle state: a DRAFT and the FROZEN snapshot of the
        # same version are distinct artefacts, and the frozen one must never be
        # overwritten by a later edit of the same version.
        return self.root / f"{design.design_id}.v{int(design.version)}.{design.status}.json"

    def _write_atomic(self, path: Path, payload: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            os.replace(tmp, path)  # atomic on POSIX and Windows
        except OSError as exc:  # noqa: BLE001 - re-raised, never swallowed
            raise DesignStoreError(f"cannot persist design at {path}: {exc}") from exc

    def _persist(self, design: ExperimentDesign) -> None:
        path = self._path_for(design)
        self._write_atomic(
            path,
            {"schema": SCHEMA, "saved_at": time.time(), "design": design.to_dict()},
        )
        self._versions.setdefault(design.design_id, {})[_rank(design)] = str(path)

    def _load(self) -> None:
        if not self.root.exists():
            return
        loaded = 0
        for path in sorted(self.root.glob("*.v*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if raw.get("schema") != SCHEMA:
                    logger.warning("skipping %s: unknown schema %r", path.name, raw.get("schema"))
                    continue
                design = ExperimentDesign.from_dict(raw["design"])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logger.warning("skipping unreadable design %s: %s", path.name, exc)
                continue
            self._versions.setdefault(design.design_id, {})[_rank(design)] = str(path)
            cur = self._designs.get(design.design_id)
            if cur is None or _rank(design) >= _rank(cur):
                self._designs[design.design_id] = design
            loaded += 1
        if loaded:
            logger.info("loaded %d design version(s) from %s", loaded, self.root)

    # ── public API (unchanged signatures) ─────────────────────────────────
    def save(self, design: ExperimentDesign) -> ExperimentDesign:
        with self._lock:
            self._persist(design)
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

    def history(self, design_id: str) -> List[dict]:
        """Every persisted snapshot of one design, oldest first."""
        with self._lock:
            snapshots = dict(self._versions.get(design_id, {}))
        out: List[dict] = []
        for key in sorted(snapshots):
            path = Path(snapshots[key])
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                out.append(raw["design"])
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("history: unreadable %s: %s", path.name, exc)
        return out

    def transition(self, design_id: str, target: str) -> ExperimentDesign:
        """Advance a design's lifecycle. Returns the new design; every previous
        version stays on disk (frozen stays frozen / SUPERSEDED marks a replaced
        version). Raises DesignStateError (or KeyError if unknown)."""
        if target not in DESIGN_STATES:
            raise ValueError(f"invalid target state '{target}'")
        with self._lock:
            cur = self._designs.get(design_id)
            if cur is None:
                raise KeyError(design_id)
            nxt = cur.transition(target)
            self._persist(nxt)
            self._designs[design_id] = nxt
            return nxt
