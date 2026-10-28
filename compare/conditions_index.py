"""Conditions index — lightweight cache of experiment conditions from RAW.

Instead of re-reading every RAW file on each /api/cluster/graph request,
this module builds (and caches) a small index mapping experiment_id ->
condition snapshot. The index is rebuilt when any RAW mtime grows newer
than the index file (same strategy as compare_index.json).

The index lives at ``<raw_dir>/../conditions_index.json`` — co-located
with compare_index.json, never touches RAW files.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from compare.loader import default_raw_dir, load_experiment


INDEX_NAME = "conditions_index.json"


def _index_path(raw_dir: Optional[Path] = None) -> Path:
    raw_dir = raw_dir or default_raw_dir()
    return raw_dir.parent / INDEX_NAME


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _raw_newest_mtime(raw_dir: Path) -> float:
    newest = 0.0
    if not raw_dir.is_dir():
        return newest
    for name in os.listdir(raw_dir):
        if name.endswith(".jsonl"):
            p = raw_dir / name
            newest = max(newest, _mtime(p))
    return newest


def build_conditions_index(raw_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Build conditions index from RAW (reads each file once)."""
    raw_dir = raw_dir or default_raw_dir()
    out: Dict[str, Dict[str, Any]] = {}
    if not raw_dir.is_dir():
        return out
    for name in sorted(os.listdir(raw_dir)):
        if not name.endswith(".jsonl"):
            continue
        eid = name[:-len(".jsonl")]
        try:
            exp = load_experiment(eid, raw_dir)
            if exp.condition:
                out[eid] = exp.condition
        except Exception:
            pass  # missing/corrupt -> skip, never fabricate
    return out


def load_conditions_index(raw_dir: Optional[Path] = None,
                          index_path: Optional[Path] = None,
                          refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    """Return cached conditions, rebuilding if stale or ``refresh`` is set.

    Returns a mapping experiment_id -> condition snapshot (same shape as
    what ``load_experiment().condition`` returns).
    """
    raw_dir = raw_dir or default_raw_dir()
    index_path = index_path or _index_path(raw_dir)
    need_rebuild = refresh
    if not need_rebuild and index_path.exists():
        if _raw_newest_mtime(raw_dir) > _mtime(index_path):
            need_rebuild = True
    if need_rebuild or not index_path.exists():
        out = build_conditions_index(raw_dir)
        payload = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(out),
            "conditions": out,
        }
        tmp = index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, index_path)
        return out
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        return payload.get("conditions", {})
    except (OSError, json.JSONDecodeError):
        return build_conditions_index(raw_dir)


def conditions_fingerprint(conditions: Dict[str, Dict[str, Any]]) -> str:
    """Deterministic SHA-256 over the conditions mapping (for cache keying)."""
    import hashlib
    entries = []
    for eid in sorted(conditions):
        cond = conditions[eid] or {}
        entries.append({"experiment_id": eid, "condition": cond})
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
