"""Debate Lab run persistence — immutable RAW provenance snapshot.

Mirrors the Code Lab workspace RAW convention:
    debate_lab_runs/<run_id>/
        raw/run_<run_id>.json      # immutable full run snapshot (written once)
        raw/events.jsonl           # append-only backend-real event stream

Historical RAW is IMMUTABLE: a completed run is never overwritten, so a later
Settings change can never rewrite an old run's effective configuration (spec
§29).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


class DebateLabRunStore:
    """Filesystem persistence for Debate Lab runs (run-rooted)."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        # base_dir may arrive as a str (e.g. tempfile.mkdtemp()) — coerce.
        self.base = Path(base_dir) if base_dir else (Path.cwd() / "debate_lab_runs")

    def _root(self, run_id: str) -> Path:
        return self.base / run_id

    def _raw(self, run_id: str) -> Path:
        return self._root(run_id) / "raw"

    def save_snapshot(self, run_id: str, snapshot: Dict[str, Any]) -> Path:
        """Write the immutable run snapshot. Never overwrites an existing one."""
        raw = self._raw(run_id)
        raw.mkdir(parents=True, exist_ok=True)
        target = raw / f"run_{run_id}.json"
        if target.exists():
            return target  # immutable — historical RAW is never rewritten
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(target)
        return target

    def append_event(self, run_id: str, event: Dict[str, Any]) -> None:
        raw = self._raw(run_id)
        raw.mkdir(parents=True, exist_ok=True)
        with open(raw / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def read_snapshot(self, run_id: str) -> Optional[Dict[str, Any]]:
        target = self._raw(run_id) / f"run_{run_id}.json"
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover
            return None

    def read_events(self, run_id: str) -> List[Dict[str, Any]]:
        target = self._raw(run_id) / "events.jsonl"
        if not target.exists():
            return []
        out = []
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # pragma: no cover - skip corrupt lines
                continue
        return out

    def cleanup(self, run_id: str) -> None:
        """Remove a run directory (explicit user action only)."""
        root = self._root(run_id)
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
