"""Compare — subject/topic tree (folder architecture over RAW evidence).

Groups experiments into a hierarchical folder tree so runs can be compared
within a theme (correlation view) instead of only pairwise by id. Folders are
REAL directories on disk; each leaf holds one JSON marker per experiment.

Minimal architecture (derived from the actual RAW data):

    data/subjects/
        <topic>/                 # general folder, auto-created on new subject
            <subfolder>/          # optional specificity (e.g. difficulty_range)
        e.g. math/[1,5]/, chemistry/[1,5]/, coding/<custom>

A topic is the broad subject an experiment belongs to (math, chemistry,
coding, philosophical, ...). A subfolder is optional and narrower (e.g. a
difficulty range or a task family). When a NEW topic pops up it is registered
automatically on first use — no manual folder creation.

The tree only RECORDS experiment ids; it never rewrites RAW. A marker file is
a tiny JSON {experiment_id, subject_path, registered_at, source_condition}.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default location of the subject folder tree.
DEFAULT_SUBJECTS_DIR = Path(__file__).resolve().parent.parent / "data" / "subjects"

_MARKER_SUFFIX = ".exp.json"


class SubjectTreeError(RuntimeError):
    """Raised on an invalid subject registration or a missing experiment."""


def _safe_component(name: str) -> str:
    """Sanitize a folder component so it can never escape the tree root.

    Rejects separators, dots-only segments, and any path traversal. The user
    provides topic/subfolder names via the UI, so this is a security boundary.
    """
    name = str(name).strip().strip("/\\")
    if not name or name in (".", ".."):
        raise SubjectTreeError(f"invalid subject component: {name!r}")
    if any(ch in name for ch in "/\\"):
        raise SubjectTreeError(f"subject component must be a single name, got {name!r}")
    if any(ch in name for ch in ':"*?<>|'):
        raise SubjectTreeError(f"subject component has forbidden characters: {name!r}")
    return name


def _subject_path(subject: str) -> List[str]:
    """Split a ``topic/subfolder`` (or ``topic``) spec into safe components."""
    parts = [p for p in str(subject).replace("\\", "/").split("/") if p]
    if not parts:
        raise SubjectTreeError("subject must be at least a topic name")
    return [_safe_component(p) for p in parts]


class SubjectTree:
    """Persistent subject folder tree over experiment RAW evidence."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else default_subjects_dir()
        self._lock = threading.Lock()

    # ── path helpers ───────────────────────────────────────────────────────
    def _base(self, parts: List[str]) -> Path:
        """Return the leaf directory for a subject path (auto-creates dirs)."""
        base = self.root.joinpath(*parts)
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _marker(self, base: Path, experiment_id: str) -> Path:
        return base / f"{experiment_id}{_MARKER_SUFFIX}"

    # ── registry ───────────────────────────────────────────────────────────
    def register(self, experiment_id: str, subject: str,
                 source_condition: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Assign an experiment to a subject, auto-creating the general folder
        (and any subfolder) when it does not exist yet.

        Returns the marker payload. Idempotent: re-registering the same
        experiment under the same subject overwrites the marker.
        """
        parts = _subject_path(subject)
        with self._lock:
            base = self._base(parts)
            payload = {
                "experiment_id": str(experiment_id),
                "subject": "/".join(parts),
                "topic": parts[0],
                "subfolder": "/".join(parts[1:]) or None,
                "source_condition": dict(source_condition or {}),
                "registered_at": time.time(),
            }
            self._marker(base, str(experiment_id)).write_text(
                json.dumps(payload, indent=2), encoding="utf-8")
            return payload

    def unregister(self, experiment_id: str) -> bool:
        """Remove an experiment from every subject (returns True if removed)."""
        removed = False
        with self._lock:
            for base, _dirs, files in os.walk(self.root):
                target = self._marker(Path(base), str(experiment_id))
                if target.exists():
                    target.unlink()
                    removed = True
        return removed

    def subject_of(self, experiment_id: str) -> Optional[str]:
        """Return the subject path (topic[/subfolder]) an experiment is in, or
        None if it is not registered."""
        with self._lock:
            for base, _dirs, files in os.walk(self.root):
                if self._marker(Path(base), str(experiment_id)).exists():
                    rel = Path(base).relative_to(self.root)
                    return "/".join(rel.parts) or None
        return None

    # ── tree traversal ─────────────────────────────────────────────────────
    def tree(self) -> Dict[str, Any]:
        """Full nested structure: {topic: {"subjects": {sub: {...}},
        "experiments": [ids]}} — the folder view the dashboard renders."""
        with self._lock:
            return self._walk(self.root)

    def _walk(self, base: Path) -> Dict[str, Any]:
        node: Dict[str, Any] = {"subjects": {}, "experiments": []}
        if not base.is_dir():
            return node
        for entry in sorted(os.listdir(base)):
            p = base / entry
            if p.is_dir():
                node["subjects"][entry] = self._walk(p)
            elif entry.endswith(_MARKER_SUFFIX):
                try:
                    payload = json.loads(p.read_text(encoding="utf-8"))
                    node["experiments"].append(str(payload.get("experiment_id", entry[: -len(_MARKER_SUFFIX)])))
                except (json.JSONDecodeError, OSError):
                    node["experiments"].append(entry[: -len(_MARKER_SUFFIX)])
        node["experiments"] = sorted(set(node["experiments"]))
        return node

    def experiment_ids(self, subject: str, recursive: bool = True) -> List[str]:
        """Experiment ids under a subject path. `recursive` includes subfolders."""
        parts = _subject_path(subject) if subject else []
        target = self.root.joinpath(*parts)
        if not target.exists():
            return []
        with self._lock:
            if recursive:
                ids: List[str] = []
                for base, _dirs, files in os.walk(target):
                    for fname in files:
                        if fname.endswith(_MARKER_SUFFIX):
                            ids.append(fname[: -len(_MARKER_SUFFIX)])
                return sorted(set(ids))
            node = self._walk(target)
            return node["experiments"]

    def topics(self) -> List[str]:
        """Top-level topic names (sorted)."""
        if not self.root.is_dir():
            return []
        return sorted(
            d.name for d in os.scandir(self.root)
            if d.is_dir() and not d.name.startswith("."))

    # ── bootstrap from RAW evidence ─────────────────────────────────────────
    def bootstrap_from_raw(self, raw_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Auto-register every run that has RAW evidence into a DEFAULT subject.

        Minimal architecture from the actual data: topic = condition domain,
        subfolder = difficulty_range (the one variable that actually varies
        between runs). Runs with no verdict tasks (empty test artifacts) are
        skipped - they carry no evidence. A researcher may re-route afterward.
        """
        from compare.loader import list_available_experiments, load_experiment

        registered: Dict[str, int] = {}
        skipped_no_evidence = 0
        for eid in list_available_experiments(raw_dir):
            try:
                m = load_experiment(eid, raw_dir)
            except Exception:
                continue
            if m.condition.get("source") in ("code_lab", "debate_lab"):
                # Lab runs have no experiment domain/difficulty; they are
                # browsable in Compare but must not pollute the subject tree.
                continue
            if m.num_tasks == 0 or (m.num_tasks and not m.has_verdicts):
                skipped_no_evidence += 1
                continue
            domain = m.condition.get("domain") or "unknown"
            dr = m.condition.get("difficulty_range")
            if isinstance(dr, (list, tuple)) and len(dr) == 2:
                sub = f"[{dr[0]},{dr[1]}]"
            else:
                sub = "other"
            subject = f"{domain}/{sub}"
            self.register(eid, subject, source_condition=m.condition)
            registered[subject] = registered.get(subject, 0) + 1
        return {
            "registered": registered,
            "skipped_no_evidence": skipped_no_evidence,
            "topics": self.topics(),
        }

def default_subjects_dir() -> Path:
    return DEFAULT_SUBJECTS_DIR