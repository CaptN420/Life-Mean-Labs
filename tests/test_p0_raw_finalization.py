"""Regression: RAW persistence failure must mark the experiment FAILED, not
COMPLETED-without-evidence.

P0 integrity rule (audit): an experiment is only COMPLETED when its required
finalization (RAW write) actually succeeded. Previously `_persist_results_to_raw`
swallowed the write error and the derived lifecycle status stayed COMPLETED even
though no RAW evidence existed.
"""

import os
from pathlib import Path

from experiments.ui_controller import ExperimentUIController


def _fake_result(experiment_id: str) -> dict:
    """A minimal object exposing to_dict() like ExperimentResult."""
    class R:
        def to_dict(self):
            return {
                "experiment_id": experiment_id,
                "run_id": "run_x", "task_id": "task_x", "config": {},
                "routing_decision": {}, "workers_used": [], "tools_used": [],
                "answer": 1, "ground_truth": 1,
                "validation_result": {"valid": True, "score": 1.0, "method": "deterministic"},
                "provenance": None, "timestamp": 0.0, "metadata": {},
            }
    return R()


class TestRawPersistenceFailureMarksFailed:
    def test_success_writes_raw_and_stays_completed(self, tmp_path):
        ctl = ExperimentUIController()
        state = ctl.register_experiment("exp_p0_ok", {"seed": 1})
        results = [_fake_result("exp_p0_ok")]
        ctl._persist_results_to_raw("exp_p0_ok", results, mode="deterministic",
                                    raw_root=Path(tmp_path))
        raw = tmp_path / "exp_p0_ok.jsonl"
        assert raw.exists()
        content = raw.read_text(encoding="utf-8")
        assert '"execution_mode": "deterministic"' in content
        assert '"settings_snapshot"' in content
        # No error added -> never FAILED (correct path).
        assert state.errors == []
        assert state.to_dict()["status"] != "FAILED"

    def test_write_failure_marks_experiment_failed(self, tmp_path):
        ctl = ExperimentUIController()
        state = ctl.register_experiment("exp_p0_fail", {"seed": 1})
        # raw_root points INTO a file -> mkdir(parents=True) raises ENOTDIR.
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("x", encoding="utf-8")
        bad_root = blocker / "sub"
        # Wait: bad_root.parent is blocker (a file) so mkdir on sub raises NotADirectoryError.
        results = [_fake_result("exp_p0_fail")]
        ctl._persist_results_to_raw("exp_p0_fail", results, mode="deterministic",
                                    raw_root=Path(bad_root))
        # The failure must be surfaced as an error -> derived status FAILED.
        assert any("finalization_failure" in e for e in state.errors), state.errors
        assert state.to_dict()["status"] == "FAILED"

    def test_path_traversal_sanitized(self, tmp_path):
        ctl = ExperimentUIController()
        ctl.register_experiment("exp/slashed", {"seed": 1})
        results = [_fake_result("exp/slashed")]
        ctl._persist_results_to_raw("exp/slashed", results, raw_root=Path(tmp_path))
        # '/' replaced so no subdir traversal; a flat file is written.
        assert (tmp_path / "exp_slashed.jsonl").exists()