"""Compare V1 — RAW evidence loader.

Reads historical experimental evidence from ``data/raw_debates/<id>.jsonl``
(the append-only RAW, one JSON object per task) and reduces each line into a
:class:`compare.models.TaskRecord`, then aggregates into a
:class:`compare.models.RunMetrics`.

Compare is strictly read-only over RAW: it never writes a RAW file, never
mutates history. Fields that vary between legacy and current RAW shapes are
read tolerantly (safe .get with defaults); a task line that cannot be parsed
into evidence is skipped, never fabricated.

Validation semantics (spec §25): a ``divergent``/missing verdict is counted
separately from FAIL — NOT_REACHED != FAIL is respected.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from compare.models import RunMetrics, TaskRecord

# Default location of the RAW evidence store.
DEFAULT_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_debates"


class CompareLoadError(RuntimeError):
    """Raised when the raw evidence for an experiment cannot be read."""


def _as_list(value: Any) -> List[str]:
    """Normalise a tools/workers value (list, str, or missing) to a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return []


def _failure_reason(line: Dict[str, Any]) -> str:
    """Deterministic failure reason from a RAW line's validation result.

    Mirrors the coarse categories in the Failure Bank (§25). A "no_answer"
    is its own category — distinct from an incorrect answer.
    """
    vr = line.get("validation_result")
    if not isinstance(vr, dict):
        return "no_validation_result"
    if vr.get("error"):
        return str(vr["error"])
    method = vr.get("method", "")
    if method == "no_answer":
        return "no_answer_computed"
    # valid key: True / False / "true"/"false"
    valid = vr.get("valid")
    if isinstance(valid, str):
        valid = valid.lower() == "true"
    if not valid:
        return "incorrect_answer"
    return ""


def task_record_from_line(line: Dict[str, Any]) -> Optional[TaskRecord]:
    """Reduce one RAW JSONL object into a TaskRecord (or None if unusable).

    ``valid`` comes from the deterministic validation verdict only; a line
    without one is counted as no-verdict, never as a fabricated FAIL.
    """
    task_id = str(line.get("task_id", ""))
    experiment_id = str(line.get("experiment_id", ""))
    run_id = str(line.get("run_id", ""))
    if not task_id:
        return None

    metadata = dict(line.get("metadata") or {})
    domain = str(metadata.get("domain") or (line.get("config") or {}).get("domain") or "")
    diff = line.get("difficulty")
    if diff is None:
        diff = metadata.get("difficulty")
    if isinstance(diff, (int, float)):
        difficulty = int(diff)
    else:
        difficulty = None

    vr = line.get("validation_result")
    if isinstance(vr, dict):
        valid = vr.get("valid")
        if isinstance(valid, str):
            valid = valid.lower() == "true"
        score = float(vr.get("score", 0.0) or 0.0)
    else:
        valid = None
        score = 0.0

    tools = _as_list(line.get("tools_used") or metadata.get("tools_used"))
    workers = _as_list(line.get("workers_used") or metadata.get("workers_used"))

    return TaskRecord(
        task_id=task_id,
        run_id=run_id,
        experiment_id=experiment_id,
        domain=domain,
        difficulty=difficulty,
        valid=valid,
        score=score,
        tools_used=tools,
        workers_used=workers,
        failure_reason=_failure_reason(line) if valid is False else "",
        metadata=metadata,
    )


def _dimension_stats(tasks: Iterable[TaskRecord], key: str) -> Dict[str, Dict[str, float]]:
    """{value: {"passed": n, "total": n, "accuracy": float}} over tasks."""
    buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"passed": 0, "total": 0})
    for t in tasks:
        value = getattr(t, key)
        if value is None or value == "":
            continue
        if key == "difficulty":
            value = f"diff_{value}"
        b = buckets[str(value)]
        b["total"] += 1
        if t.valid is True:
            b["passed"] += 1
    out: Dict[str, Dict[str, float]] = {}
    for value, counts in buckets.items():
        total = counts["total"]
        out[value] = {"passed": counts["passed"], "total": total,
                      "accuracy": (counts["passed"] / total) if total else 0.0}
    return dict(sorted(out.items()))


def aggregate(tasks: List[TaskRecord], condition: Dict[str, Any],
              experiment_id: str, run_id: str = "") -> RunMetrics:
    """Aggregate TaskRecords into RunMetrics (deterministic)."""
    if not tasks:
        return RunMetrics(experiment_id=experiment_id, run_id=run_id,
                          condition=dict(condition or {}))
    passed = sum(1 for t in tasks if t.valid is True)
    failed = sum(1 for t in tasks if t.valid is False)
    no_verdict = len(tasks) - passed - failed

    tools: List[str] = []
    for t in tasks:
        for tool in t.tools_used:
            if tool and tool not in tools:
                tools.append(tool)
    workers: List[str] = []
    for t in tasks:
        for w in t.workers_used:
            if w and w not in workers:
                workers.append(w)

    failure_reasons: Dict[str, int] = defaultdict(int)
    for t in tasks:
        if t.failure_reason:
            failure_reasons[t.failure_reason] += 1

    total = len(tasks)
    return RunMetrics(
        experiment_id=experiment_id,
        run_id=run_id,
        condition=dict(condition or {}),
        tasks=tasks,
        num_tasks=total,
        num_passed=passed,
        num_failed=failed,
        num_no_verdict=no_verdict,
        success_rate=passed / total,
        avg_score=sum(t.score for t in tasks) / total,
        by_domain=_dimension_stats(tasks, "domain"),
        by_difficulty=_dimension_stats(tasks, "difficulty"),
        tools_used=tools,
        workers_used=workers,
        failure_reasons=dict(failure_reasons),
    )


def default_raw_dir() -> Path:
    """Return the default RAW evidence directory."""
    return DEFAULT_RAW_DIR


def load_experiment(experiment_id: str, raw_dir: Optional[Path] = None) -> RunMetrics:
    """Load one experiment's RAW evidence into a RunMetrics.

    Args:
        experiment_id: The experiment id, e.g. ``exp_12d54dac``. The RAW file
            ``<experiment_id>.jsonl`` is read from ``raw_dir`` (default
            ``data/raw_debates``).
    """
    raw_dir = raw_dir or default_raw_dir()
    path = raw_dir / f"{experiment_id}.jsonl"
    if not path.exists():
        # Code Lab / Debate Lab runs persist their RAW snapshot elsewhere;
        # delegate to the lab-run adapter instead of reporting a false 404.
        from compare.lab_runs import is_lab_run_id, load_lab_run
        if is_lab_run_id(experiment_id):
            return load_lab_run(experiment_id)
        raise CompareLoadError(
            f"no RAW evidence for experiment '{experiment_id}' at {path}")
    tasks: List[TaskRecord] = []
    condition: Dict[str, Any] = {}
    run_id = ""
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
            if not condition and obj.get("config"):
                condition = dict(obj["config"])
            if not run_id and obj.get("run_id"):
                run_id = str(obj["run_id"])
            rec = task_record_from_line(obj)
            if rec is not None:
                tasks.append(rec)
    return aggregate(tasks, condition, experiment_id, run_id)


def load_experiments(experiment_ids: Iterable[str],
                     raw_dir: Optional[Path] = None) -> List[RunMetrics]:
    """Load several experiments. A missing/invalid one raises
    :class:`CompareLoadError` (honest — never silently drop a requested run
    and compare a smaller set as if it were complete)."""
    out: List[RunMetrics] = []
    for eid in experiment_ids:
        out.append(load_experiment(str(eid), raw_dir))
    return out


def list_available_experiments(raw_dir: Optional[Path] = None,
                               include_lab_runs: Optional[bool] = None) -> List[str]:
    """List every id with RAW evidence — experiments + Code Lab / Debate Lab.

    Lab runs are included only for the default RAW store (production view);
    passing an explicit ``raw_dir`` (tests, isolated scans) keeps the result
    scoped to that directory unless ``include_lab_runs=True`` is forced.
    """
    explicit_dir = raw_dir is not None
    raw_dir = raw_dir or default_raw_dir()
    if include_lab_runs is None:
        include_lab_runs = not explicit_dir
    ids = []
    if raw_dir.is_dir():
        for name in os.listdir(raw_dir):
            if name.endswith(".jsonl"):
                ids.append(name[: -len(".jsonl")])
    if include_lab_runs:
        try:
            from compare.lab_runs import list_lab_run_rows
            ids.extend(str(row.get("experiment_id")) for row in list_lab_run_rows()
                       if row.get("experiment_id"))
        except Exception:  # pragma: no cover - availability must never fail
            pass
    return sorted(set(ids))