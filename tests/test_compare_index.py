"""Tests for Compare browser index (compare/index.py).

The browser index derives lightweight, honest listing rows from RAW so the
Compare tab can show experiments without loading every full file. All fixtures
use tmp dirs; never the real data/raw_debates.
"""

import json
import time
from pathlib import Path

import pytest

from compare.index import (
    build_index,
    default_index_path,
    load_index,
    write_index,
)
from compare.loader import CompareLoadError


def _write_raw(tmp: Path, experiment_id: str, lines: list, parent: str = "raw"):
    """Write RAW lines for an experiment under tmp/<parent>/<id>.jsonl."""
    d = tmp / parent
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{experiment_id}.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines), encoding="utf-8")


def _line(experiment_id: str, valid=True, task="task_x", domain="math",
          ts=1700000000.0, seed=42, mode="deterministic"):
    return {
        "run_id": "run_a", "task_id": task, "experiment_id": experiment_id,
        "config": {"domain": domain, "seed": seed},
        "validation_result": {"valid": valid, "score": 1.0 if valid else 0.0,
                              "method": "deterministic", "error": None},
        "timestamp": ts,
        "metadata": {"execution_mode": mode},
        "provenance": {"experiment_id": experiment_id, "seed": seed,
                       "generator_version": "1.0.0", "generator_strategy": "template",
                       "routing_decision": {"selected": ["math_validation_worker"],
                                            "usage": {"math_validation_worker": 1}}},
        "workers_used": ["math_validation_worker"],
        "tools_used": ["math_gcd"],
    }


class TestBuildIndex:
    def test_build_index_sorts_by_created_at_desc(self, tmp_path):
        _write_raw(tmp_path, "exp_old",
                   [_line("exp_old", ts=1000.0, task="t1")])
        _write_raw(tmp_path, "exp_new",
                   [_line("exp_new", ts=9000.0, task="t1")])
        rows = build_index(tmp_path / "raw")
        assert [r["experiment_id"] for r in rows] == ["exp_new", "exp_old"]

    def test_counts_pass_fail_no_verdict(self, tmp_path):
        _write_raw(tmp_path, "exp_mix", [
            _line("exp_mix", valid=True, task="t1"),
            _line("exp_mix", valid=False, task="t2"),
            _line("exp_mix", **{"valid": None, "task": "t3"}),
        ])
        r = build_index(tmp_path / "raw")[0]
        assert r["num_tasks"] == 3
        assert r["num_passed"] == 1
        assert r["num_failed"] == 1
        assert r["num_no_verdict"] == 1

    def test_status_flags_failures(self, tmp_path):
        _write_raw(tmp_path, "exp_f", [_line("exp_f", valid=False)])
        r = build_index(tmp_path / "raw")[0]
        assert r["status"] == "COMPLETED_WITH_FAILURES"

    def test_status_completed(self, tmp_path):
        _write_raw(tmp_path, "exp_ok", [_line("exp_ok", valid=True)])
        r = build_index(tmp_path / "raw")[0]
        assert r["status"] == "COMPLETED"

    def test_status_inconclusive_when_no_verdict(self, tmp_path):
        _write_raw(tmp_path, "exp_nv", [_line("exp_nv", **{"valid": None})])
        r = build_index(tmp_path / "raw")[0]
        assert r["status"] == "INCONCLUSIVE"

    def test_empty_file_excluded(self, tmp_path):
        d = tmp_path / "raw"
        d.mkdir(parents=True, exist_ok=True)
        (d / "exp_empty.jsonl").write_text("", encoding="utf-8")
        assert build_index(d) == []

    def test_subject_from_config(self, tmp_path):
        _write_raw(tmp_path, "exp_m", [_line("exp_m", domain="chemistry")])
        assert build_index(tmp_path / "raw")[0]["subject"] == "chemistry"

    def test_not_recorded_fields_listed(self, tmp_path):
        _write_raw(tmp_path, "exp_a", [_line("exp_a")])
        r = build_index(tmp_path / "raw")[0]
        assert "title" in r["not_recorded"]
        assert "template" in r["not_recorded"]
        assert "models" in r["not_recorded"]

    def test_seed_and_strategy_extracted(self, tmp_path):
        _write_raw(tmp_path, "exp_s", [_line("exp_s", seed=7)])
        r = build_index(tmp_path / "raw")[0]
        assert r["seed"] == 7.0
        assert r["generator_strategy"] == "template"


class TestIndexPersistence:
    def test_write_then_load_roundtrip(self, tmp_path):
        _write_raw(tmp_path, "exp_a", [_line("exp_a")])
        rows = build_index(tmp_path / "raw")
        idx_path = tmp_path / "compare_index.json"
        write_index(rows, idx_path)
        assert idx_path.exists()
        idx = load_index(tmp_path / "raw", idx_path)
        assert idx["count"] == 1
        assert idx["experiments"][0]["experiment_id"] == "exp_a"

    def test_load_index_rebuilds_when_stale(self, tmp_path):
        _write_raw(tmp_path, "exp_a", [_line("exp_a", task="t1")])
        idx_path = tmp_path / "ci.json"
        write_index(build_index(tmp_path / "raw"), idx_path)
        # Add a new RAW file -> stale mtime -> rebuild on load.
        time.sleep(0.01)
        _write_raw(tmp_path, "exp_b", [_line("exp_b", task="t1")])
        idx = load_index(tmp_path / "raw", idx_path)
        assert idx["fresh"] is True
        assert idx["count"] == 2

    def test_load_cached_index_not_fresh(self, tmp_path):
        _write_raw(tmp_path, "exp_a", [_line("exp_a")])
        idx_path = tmp_path / "ci.json"
        write_index(build_index(tmp_path / "raw"), idx_path)
        idx = load_index(tmp_path / "raw", idx_path)
        assert idx["fresh"] is False
        assert idx["count"] == 1

    def test_load_index_missing_corrupt_rebuilds(self, tmp_path):
        _write_raw(tmp_path, "exp_a", [_line("exp_a")])
        idx_path = tmp_path / "ci.json"
        if idx_path.exists():
            idx_path.unlink()
        idx = load_index(tmp_path / "raw", idx_path)
        assert idx["count"] == 1

    def test_default_index_path_is_data_compare_index(self):
        p = default_index_path()
        assert p.name == "compare_index.json"


class TestTaskRecordTolerance:
    def test_corrupt_line_skipped_never_fabricated(self, tmp_path):
        d = tmp_path / "raw"
        d.mkdir(parents=True, exist_ok=True)
        (d / "exp_x.jsonl").write_text(
            "{\"config\": {\"domain\": \"math\"}}\nnot-json\n", encoding="utf-8")
        rows = build_index(d)
        assert len(rows) == 1  # corrupt line skipped, file still counted
        assert rows[0]["num_tasks"] == 1