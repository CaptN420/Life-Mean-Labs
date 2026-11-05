"""Persistence for the self-extension layer (P5).

Why: the registries lived only in memory. `POST /api/extensions/tools` answered
``status: "proposed"``/``"active"`` and everything vanished on restart — a
success the user could never find again. A restart also silently reset the
approval history.

Design:
* one JSON document per kind, written atomically (tmp + replace);
* the file is read at layer creation and written after every mutation;
* a save failure is raised to the caller, never swallowed: an approval that
  could not be stored must not look approved.

Nothing is deleted here; a rollback removes the entry from the registry, which
is the registry's own semantics, and the previous file state stays in the
``.bak`` copy taken before each write.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("life_mean_extensions.store")

SCHEMA = "life-mean-extensions/1"


def extensions_dir() -> Path:
    """Where the extension registries live (override: LIFE_MEAN_EXTENSIONS_DIR)."""
    env = os.environ.get("LIFE_MEAN_EXTENSIONS_DIR")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "data" / "extensions"


class ExtensionStore:
    """Atomic JSON persistence for skills, tools, needs and pipeline items."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory) if directory else extensions_dir()
        self.path = self.directory / "registries.json"
        self.last_error: str = ""

    # ── lecture ────────────────────────────────────────────────────────────
    def load(self) -> Dict[str, Any]:
        """Return the stored document, or an empty one if absent/unreadable."""
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # Never guess: an unreadable file means "nothing loaded", and the
            # reason is logged so the UI can show why the lists are empty.
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.error("could not read %s: %s", self.path, exc)
            return {}
        if raw.get("schema") != SCHEMA:
            self.last_error = f"unknown schema: {raw.get('schema')!r}"
            logger.warning("ignoring %s: %s", self.path, self.last_error)
            return {}
        return raw

    # ── écriture ───────────────────────────────────────────────────────────
    def save(self, payload: Dict[str, Any]) -> bool:
        """Write atomically. Returns False and sets ``last_error`` on failure."""
        document = {"schema": SCHEMA, "saved_at": time.time(), **payload}
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                # NO DELETE: previous state is kept next to the new one.
                self.path.replace(self.path.with_suffix(".json.bak"))
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)
            self.last_error = ""
            return True
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.error("could not persist %s: %s", self.path, exc)
            return False

    def describe(self) -> Dict[str, Any]:
        """Honest status of the storage, for any API payload."""
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "writable": os.access(self.directory if self.directory.exists() else self.directory.parent,
                                  os.W_OK),
            "last_error": self.last_error,
        }
