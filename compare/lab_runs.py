"""Compare — Code Lab / Debate Lab run discovery and normalization.

The Compare browser historically indexed only ``data/raw_debates/*.jsonl``
(synthetic-data experiments). Code Lab and Debate Lab persist their own RAW
snapshots:

  code_lab_runs/<run_id>/raw/run_<run_id>.json
  debate_lab_runs/<run_id>/raw/run_<run_id>.json

This module turns those snapshots into (a) the same lightweight index row
shape used by ``compare.index`` so the browser lists them, and (b) a
``RunMetrics`` with no per-task records so they can be inspected and compared
without inventing task evidence. Compare stays read-only: nothing here writes
a lab run.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from compare.models import RunMetrics

CODE_LAB_PREFIX = "codelab_"
DEBATE_LAB_PREFIX = "debatelab_"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def default_code_lab_runs_dir() -> Path:
    return _PROJECT_ROOT / "code_lab_runs"


def default_debate_lab_runs_dir() -> Path:
    return _PROJECT_ROOT / "debate_lab_runs"


def is_lab_run_id(run_id: str) -> bool:
    rid = str(run_id or "")
    return rid.startswith(CODE_LAB_PREFIX) or rid.startswith(DEBATE_LAB_PREFIX)


def _iso_from_mtime(path: Path) -> Optional[str]:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
    except OSError:
        return None


def _normalizes_status(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if value in ("completed", "passed", "pass", "success", "succeeded", "ok"):
        return "COMPLETED"
    if value in ("failed", "fail", "error", "errored"):
        return "FAILED"
    return "INCONCLUSIVE"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _base_row(run_id: str, source: str, status: str, steps: int,
              created_at: Optional[str], subject: str,
              execution_mode: str, extra: Optional[Dict[str, Any]] = None,
              not_recorded: Optional[List[str]] = None) -> Dict[str, Any]:
    steps = int(steps or 0)
    num_tasks = steps if steps > 0 else 1
    if status == "COMPLETED":
        passed, failed = num_tasks, 0
    elif status == "FAILED":
        passed, failed = 0, num_tasks
    else:
        passed, failed = 0, 0
    row: Dict[str, Any] = {
        "experiment_id": run_id,
        "run_id": run_id,
        "source": source,
        "subject": subject or source,
        "created_at": created_at,
        "num_tasks": num_tasks,
        "num_passed": passed,
        "num_failed": failed,
        "num_no_verdict": num_tasks - passed - failed,
        "success_rate": (passed / num_tasks) if num_tasks else 0.0,
        "status": status,
        "execution_mode": execution_mode,
        "seed": None,
        "generator_strategy": "not_recorded",
        "workers": [],
        "tools": [],
        "not_recorded": not_recorded if not_recorded is not None else [],
    }
    if extra:
        row.update(extra)
    return row


def code_lab_row(snap_path: Path) -> Optional[Dict[str, Any]]:
    data = _read_json(snap_path)
    if data is None:
        return None
    run_id = str(data.get("run_id") or snap_path.parent.parent.name)
    role = data.get("role_template") or {}
    template_id = ""
    if isinstance(role, dict):
        template_id = str(role.get("template_id") or role.get("id") or "")
    status = _normalizes_status(data.get("status"))
    iterations = int(data.get("iterations") or 0)
    trace = data.get("agent_trace") or []
    steps = iterations or len(trace)
    date = _iso_from_mtime(snap_path)
    row = _base_row(
        run_id=run_id,
        source="code_lab",
        status=status,
        steps=steps,
        created_at=date,
        subject=template_id or str(data.get("project") or "code_lab"),
        execution_mode=str(data.get("execution_mode") or "not_recorded"),
        extra={
            "duration": data.get("duration"),
            "files_created": list(data.get("files_created") or []),
            "deterministic_validation": data.get("deterministic_validation_status"),
            "semantic_judge": (data.get("semantic_judge") or {}).get("status")
            if isinstance(data.get("semantic_judge"), dict) else None,
        },
        not_recorded=["title", "models", "validator_versions"],
    )
    return row


def debate_lab_row(snap_path: Path) -> Optional[Dict[str, Any]]:
    data = _read_json(snap_path)
    if data is None:
        return None
    run_id = str(data.get("run_id") or snap_path.parent.parent.name)
    status = _normalizes_status(data.get("status") or data.get("execution_status"))
    turns = int(data.get("turns_committed") or data.get("last_committed_turn") or 0)
    date = str(data.get("ended_at") or "")[:19] or _iso_from_mtime(snap_path)
    row = _base_row(
        run_id=run_id,
        source="debate_lab",
        status=status,
        steps=turns,
        created_at=date,
        subject=str(data.get("template_id") or "debate_lab"),
        execution_mode="debate",
        extra={
            "topic": data.get("topic"),
            "run_name": data.get("run_name"),
            "max_turns": data.get("max_turns"),
            "duration": data.get("duration_seconds"),
            "validation_status": data.get("validation_status"),
        },
        not_recorded=["title", "models", "validator_versions"],
    )
    return row


def _scan_dir(root: Path, prefix: str, row_fn) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for name in sorted(os.listdir(root)):
        if not name.startswith(prefix):
            continue
        snap = root / name / "raw" / f"run_{name}.json"
        if not snap.is_file():
            continue
        row = row_fn(snap)
        if row is not None:
            rows.append(row)
    return rows


def list_lab_run_rows(code_lab_root: Optional[Path] = None,
                      debate_lab_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Index rows for every Code Lab / Debate Lab run with a RAW snapshot."""
    cl_root = code_lab_root or default_code_lab_runs_dir()
    dl_root = debate_lab_root or default_debate_lab_runs_dir()
    return (_scan_dir(cl_root, CODE_LAB_PREFIX, code_lab_row)
            + _scan_dir(dl_root, DEBATE_LAB_PREFIX, debate_lab_row))


def lab_runs_newest_mtime(code_lab_root: Optional[Path] = None,
                          debate_lab_root: Optional[Path] = None) -> float:
    """Newest mtime across lab run snapshots (for index staleness checks)."""
    newest = 0.0
    for root, prefix in (
        (code_lab_root or default_code_lab_runs_dir(), CODE_LAB_PREFIX),
        (debate_lab_root or default_debate_lab_runs_dir(), DEBATE_LAB_PREFIX),
    ):
        if not root.is_dir():
            continue
        for name in os.listdir(root):
            if not name.startswith(prefix):
                continue
            snap = root / name / "raw" / f"run_{name}.json"
            try:
                newest = max(newest, snap.stat().st_mtime)
            except OSError:
                continue
    return newest


def _lab_snapshot_path(run_id: str,
                       code_lab_root: Optional[Path] = None,
                       debate_lab_root: Optional[Path] = None) -> Optional[Path]:
    rid = str(run_id or "")
    if rid.startswith(CODE_LAB_PREFIX):
        root = code_lab_root or default_code_lab_runs_dir()
    elif rid.startswith(DEBATE_LAB_PREFIX):
        root = debate_lab_root or default_debate_lab_runs_dir()
    else:
        return None
    snap = root / rid / "raw" / f"run_{rid}.json"
    return snap if snap.is_file() else None


def load_lab_run(run_id: str,
                 code_lab_root: Optional[Path] = None,
                 debate_lab_root: Optional[Path] = None) -> RunMetrics:
    """Load a Code Lab / Debate Lab run as RunMetrics (no task records).

    Raises ``compare.loader.CompareLoadError`` when the snapshot is missing or
    unreadable — never fabricates a run.
    """
    from compare.loader import CompareLoadError

    path = _lab_snapshot_path(run_id, code_lab_root, debate_lab_root)
    if path is None:
        raise CompareLoadError(f"no RAW evidence for lab run '{run_id}'")
    data = _read_json(path)
    if data is None:
        raise CompareLoadError(f"unreadable RAW snapshot for lab run '{run_id}' at {path}")

    if str(run_id).startswith(CODE_LAB_PREFIX):
        row = code_lab_row(path)
        condition: Dict[str, Any] = {
            "source": "code_lab",
            "project": data.get("project"),
            "execution_mode": data.get("execution_mode"),
            "role_template": data.get("role_template"),
            "settings_snapshot": data.get("settings_snapshot"),
            "plan": data.get("plan"),
        }
        condition = {k: v for k, v in condition.items() if v not in (None, "", {}, [])}
    else:
        row = debate_lab_row(path)
        provenance = data.get("provenance") or {}
        condition = {
            "source": "debate_lab",
            "topic": data.get("topic"),
            "template_id": data.get("template_id"),
            "max_turns": data.get("max_turns"),
            "execution_mode": "debate",
        }
        if isinstance(provenance, dict):
            for key in ("effective_roles", "configured_role_models",
                        "configured_model_pool", "model_routing_method",
                        "speaker_selection_mode"):
                if key in provenance:
                    condition[key] = provenance[key]
        condition = {k: v for k, v in condition.items() if v not in (None, "", {}, [])}

    row = row or {}
    num_tasks = int(row.get("num_tasks") or 0)
    num_passed = int(row.get("num_passed") or 0)
    num_failed = int(row.get("num_failed") or 0)
    failure_reasons: Dict[str, int] = {}
    errors = data.get("errors") or []
    if errors:
        failure_reasons["lab_run_error"] = len(errors) if isinstance(errors, list) else 1

    return RunMetrics(
        experiment_id=str(run_id),
        run_id=str(data.get("run_id") or run_id),
        condition=condition,
        tasks=[],
        num_tasks=num_tasks,
        num_passed=num_passed,
        num_failed=num_failed,
        num_no_verdict=max(num_tasks - num_passed - num_failed, 0),
        success_rate=(num_passed / num_tasks) if num_tasks else 0.0,
        failure_reasons=failure_reasons,
    )
