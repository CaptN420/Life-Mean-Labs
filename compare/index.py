"""Compare browser index — lightweight, honest experiment listing.

The Compare tab needs a *browse* view (list all experiments with a
readable summary) without loading every full RAW file. This module builds /
caches a small index from ``data/raw_debates/*.jsonl``. Each row is derived
from RAW only:

  experiment_id, run_id, subject (domain), created_at (min timestamp),
  num_tasks/passed/failed/no_verdict, success_rate, status, execution_mode,
  seed, generator_strategy, first workers/tools.

Fields the RAW does not record (title, template, models, validator versions)
are reported as ``"not_recorded": true`` unless an experiment-specific
metadata source provides them — the UI must render these as "Not recorded",
never invent values.

The index is written to ``<raw_dir>/../compare_index.json`` and refreshed
when a RAW mtime grows newer than the index (or on explicit rebuild).

Compare stays read-only over RAW: this writes only its own sidecar index,
never RAW history.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from compare.loader import default_raw_dir, task_record_from_line

INDEX_NAME = "compare_index.json"


def _iso(ts: Optional[float]) -> Optional[str]:
    if not ts:
        return None
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
    except (ValueError, OSError):
        return None


def _scan_one(path: Path) -> Optional[Dict[str, Any]]:
    """Scan one RAW file into an index row (streams lines, keeps no tasks)."""
    config: Dict[str, Any] = {}
    run_id = ""
    exp_id = ""
    seed: Optional[float] = None
    gen_strategy = ""
    execution_mode = ""
    workers: List[str] = []
    tools: List[str] = []
    min_ts: Optional[float] = None
    passed = failed = no_verdict = 0
    total = 0

    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue  # corrupt line -> skip, never fabricate
                if not isinstance(obj, dict):
                    continue
                total += 1
                if not config and obj.get("config"):
                    config = dict(obj["config"])
                if not run_id and obj.get("run_id"):
                    run_id = str(obj["run_id"])
                if not exp_id and obj.get("experiment_id"):
                    exp_id = str(obj["experiment_id"])
                ts = obj.get("timestamp")
                if ts is not None:
                    ts = float(ts)
                    if min_ts is None or ts < min_ts:
                        min_ts = ts
                meta = obj.get("metadata") or {}
                if not execution_mode and isinstance(meta, dict):
                    execution_mode = str(meta.get("execution_mode") or "")
                prov = obj.get("provenance") or {}
                if isinstance(prov, dict):
                    if seed is None and prov.get("seed") is not None:
                        seed = float(prov["seed"])
                    if not gen_strategy and prov.get("generator_strategy"):
                        gen_strategy = str(prov["generator_strategy"])
                rec = task_record_from_line(obj)
                if rec is not None:
                    if rec.valid is True:
                        passed += 1
                    elif rec.valid is False:
                        failed += 1
                    else:
                        no_verdict += 1
                    for w in rec.workers_used:
                        if w and w not in workers:
                            workers.append(w)
                    for t in rec.tools_used:
                        if t and t not in tools:
                            tools.append(t)
    except OSError:
        return None

    if total == 0:
        return None

    domain = str(config.get("domain") or "")
    if not domain:
        # fall back to metadata domain carried on the first task line
        try:
            with open(path, encoding="utf-8") as fh:
                first = fh.readline().strip()
            if first:
                obj = json.loads(first)
                domain = str((obj.get("metadata") or {}).get("domain") or "")
        except (OSError, json.JSONDecodeError):
            domain = ""

    if not exp_id:
        exp_id = path.name[: -len(".jsonl")]

    status = "INCONCLUSIVE" if (passed + failed) == 0 else "COMPLETED"
    if failed:
        status = "COMPLETED_WITH_FAILURES"

    return {
        "experiment_id": exp_id,
        "run_id": run_id or None,
        "subject": domain or None,
        "created_at": _iso(min_ts),
        "num_tasks": total,
        "num_passed": passed,
        "num_failed": failed,
        "num_no_verdict": no_verdict,
        "success_rate": (passed / total) if total else 0.0,
        "status": status,
        "execution_mode": execution_mode or "not_recorded",
        "seed": seed if seed is not None else None,
        "generator_strategy": gen_strategy or "not_recorded",
        "workers": workers,
        "tools": tools,
        # Fields absent from RAW: the UI must render these honestly.
        "not_recorded": ["title", "template", "models", "validator_versions"],
    }


def default_index_path() -> Path:
    return default_raw_dir().parent / INDEX_NAME


def build_index(raw_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan every RAW file into index rows (sorted by created_at desc)."""
    raw_dir = raw_dir or default_raw_dir()
    rows: List[Dict[str, Any]] = []
    if not raw_dir.is_dir():
        return rows
    for name in sorted(os.listdir(raw_dir)):
        if not name.endswith(".jsonl"):
            continue
        row = _scan_one(raw_dir / name)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


def _index_mtime(path: Path) -> float:
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
            newest = max(newest, _index_mtime(raw_dir / name))
    return newest


def write_index(rows: List[Dict[str, Any]],
                index_path: Optional[Path] = None) -> Path:
    index_path = index_path or default_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(rows),
        "experiments": rows,
    }
    tmp = index_path.with_suffix(".jsonl.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, index_path)
    return index_path


def load_index(raw_dir: Optional[Path] = None,
               index_path: Optional[Path] = None,
               refresh: bool = False) -> Dict[str, Any]:
    """Return the cached index, rebuilding if stale or ``refresh`` is set.

    Returns ``{"experiments": [...], "count": n, "fresh": bool,
    "generated_at": str|None}``.
    """
    raw_dir = raw_dir or default_raw_dir()
    index_path = index_path or default_index_path()
    need_rebuild = refresh
    if not need_rebuild and index_path.exists():
        if _raw_newest_mtime(raw_dir) > _index_mtime(index_path):
            need_rebuild = True
    if need_rebuild or not index_path.exists():
        rows = build_index(raw_dir)
        write_index(rows, index_path)
        return {
            "experiments": rows,
            "count": len(rows),
            "fresh": True,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        rows = build_index(raw_dir)
        write_index(rows, index_path)
        return {
            "experiments": rows,
            "count": len(rows),
            "fresh": True,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    return {
        "experiments": list(payload.get("experiments", [])),
        "count": payload.get("count", len(payload.get("experiments", []))),
        "fresh": False,
        "generated_at": payload.get("generated_at"),
    }