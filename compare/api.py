"""Compare API handlers — a mixin the dashboard handler inherits.

Read-only endpoints. Compare never writes history; it only reads RAW evidence
and returns a deterministic report.

  GET /api/compare/available           -> experiment ids with RAW evidence
  GET /api/compare/run/<id>            -> one run's measured metrics + condition
  POST /api/compare                    {experiment_ids: [...]} -> full report

A missing/unreadable experiment returns 404 (honest), never a silently
reduced comparison.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from compare import CompareEngine, CompareLoadError
from compare.index import load_index, build_index, write_index
from compare.loader import list_available_experiments, load_experiment
from compare.subjects import SubjectTree, SubjectTreeError, default_subjects_dir

_ID_RE = re.compile(r"^/api/compare/run/([^/]+)$")


class CompareApiMixin:
    """Mixin providing the /api/compare/* handlers."""

    # A shared subject tree for the (single-threaded) HTTP server; tests may
    # inject their own via ``handler.compare_subjects``.
    compare_subjects: Any = None

    def _subjects(self) -> SubjectTree:
        return self.compare_subjects or SubjectTree()

    def _run_rows(self, metrics_list) -> List[Dict[str, Any]]:
        """Run dicts with subject attribution, for the report/detail views."""
        tree = self._subjects()
        return [
            {**m.to_dict(),
             "subject": tree.subject_of(m.experiment_id)}
            for m in metrics_list
        ]

    # ── GET ───────────────────────────────────────────────────────────────
    def _compare_available(self) -> None:
        self._send_json({"experiment_ids": list_available_experiments()})

    def _compare_browser(self, refresh: bool = False) -> None:
        index = load_index(refresh=refresh)
        self._send_json(index)

    def _compare_run(self, experiment_id: str) -> None:
        try:
            metrics = load_experiment(experiment_id)
        except CompareLoadError as e:
            self._send_error(404, str(e), code="not_found")
            return
        tree = self._subjects()
        self._send_json({
            "experiment": metrics.detail(),
            "subject": tree.subject_of(experiment_id),
        })

    def _compare_tree(self) -> None:
        tree = self._subjects()
        self._send_json({
            "tree": tree.tree(),
            "topics": tree.topics(),
            "root": str(default_subjects_dir()),
        })

    # ── POST ──────────────────────────────────────────────────────────────
    def _compare_report(self, data: Dict[str, Any]) -> None:
        ids = (data or {}).get("experiment_ids", [])
        if not ids:
            self._send_error(400, "experiment_ids is required (non-empty)",
                             code="invalid_request")
            return
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            self._send_error(400, "experiment_ids must be a list of strings",
                             code="invalid_request")
            return
        # Deduplicate, preserve order.
        seen, ordered = set(), []
        for eid in ids:
            if eid not in seen:
                seen.add(eid)
                ordered.append(eid)
        try:
            outcome = CompareEngine().compare(ordered)
        except CompareLoadError as e:
            self._send_error(404, str(e), code="not_found")
            return
        self._send_json({"compared": ordered,
                         "runs": self._run_rows(outcome.runs),
                         "report": outcome.to_dict()})

    def _compare_subject_report(self, data: Dict[str, Any]) -> None:
        """Compare all experiments under a subject path (correlation view)."""
        subject = (data or {}).get("subject", "")
        if not subject:
            self._send_error(400, "subject is required", code="invalid_request")
            return
        try:
            ids = self._subjects().experiment_ids(subject, recursive=True)
        except SubjectTreeError as e:
            self._send_error(400, str(e), code="invalid_subject")
            return
        if not ids:
            self._send_error(404, f"no experiments registered under subject '{subject}'",
                             code="not_found")
            return
        try:
            outcome = CompareEngine().compare(ids)
        except CompareLoadError as e:
            self._send_error(404, str(e), code="not_found")
            return
        self._send_json({"subject": subject, "experiment_ids": ids,
                         "runs": self._run_rows(outcome.runs),
                         "report": outcome.to_dict()})

    def _compare_tree_register(self, data: Dict[str, Any]) -> None:
        """Assign an experiment to a subject (auto-creates the folder)."""
        experiment_id = (data or {}).get("experiment_id", "")
        subject = (data or {}).get("subject", "")
        if not experiment_id or not subject:
            self._send_error(400, "experiment_id and subject are required",
                             code="invalid_request")
            return
        # The experiment must have RAW evidence to be comparable.
        try:
            load_experiment(experiment_id)
        except CompareLoadError as e:
            self._send_error(404, str(e), code="not_found")
            return
        try:
            payload = self._subjects().register(experiment_id, subject)
        except SubjectTreeError as e:
            self._send_error(400, str(e), code="invalid_subject")
            return
        self._send_json({"registered": payload})

    def _compare_tree_bootstrap(self, data: Dict[str, Any] = None) -> None:
        """Auto-build the subject tree from RAW evidence (topic=domain,
        subfolder=difficulty_range)."""
        summary = self._subjects().bootstrap_from_raw()
        self._send_json(summary)