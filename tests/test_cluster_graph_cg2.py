"""CG2 — Cluster Graph endpoint payload tests (backend, no HTTP socket).

Exercises the same path as ``GET /api/cluster/graph`` (compare index rows +
RAW conditions + SubjectTree + fingerprint cache) against SIMULATED real RAW
fixtures: verifies the payload shape, counts, JSON serialization of absent
scores (null not 0), cache reuse/invalidation, and — critically — that building
the graph NEVER modifies the RAW files. No LLM anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

from compare.index import build_index, load_index
from compare.loader import load_experiment
from compare.graph import build_graph_payload
from compare.subjects import SubjectTree


def _raw_line(task_id, eid, domain, seed, tools, valid=True):
    return json.dumps({
        "task_id": task_id,
        "experiment_id": eid,
        "run_id": f"run_{eid}",
        "timestamp": 1_700_000_000.0,
        "config": {"domain": domain, "seed": seed, "num_tasks": 2, "deterministic": True},
        "metadata": {"domain": domain},
        "tools_used": list(tools),
        "workers_used": [f"w_{eid}"],
        "validation_result": {"valid": valid, "score": 1.0 if valid else 0.0},
    })


def _make_raw(raw_dir: Path):
    """Write two RAW experiments (same domain, differ in seed -> HIGHLY_CONTROLLED)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "exp_a.jsonl").write_text(
        "\n".join([
            _raw_line("t1", "exp_a", "math", 1, ["math_gcd"]),
            _raw_line("t2", "exp_a", "math", 1, ["math_gcd"]),
        ]) + "\n", encoding="utf-8")
    (raw_dir / "exp_b.jsonl").write_text(
        "\n".join([
            _raw_line("t1", "exp_b", "math", 2, ["math_gcd"]),
            _raw_line("t2", "exp_b", "math", 2, ["math_gcd"]),
        ]) + "\n", encoding="utf-8")


def _raw_snapshot(raw_dir: Path):
    out = {}
    for p in sorted(raw_dir.iterdir()):
        if p.suffix == ".jsonl":
            out[p.name] = p.read_bytes()
    return out


def _graph_args(raw_dir: Path, subjects_root: Path):
    rows = build_index(raw_dir)          # same as load_index()[...] fresh
    conds = {}
    for r in rows:
        conds[r["experiment_id"]] = load_experiment(r["experiment_id"], raw_dir).condition
    st = SubjectTree(root=subjects_root)
    for r in rows:
        st.register(r["experiment_id"], r["subject"] or "unknown")
    return rows, conds, st


def test_payload_shape_and_null_scores(tmp_path):
    raw_dir = tmp_path / "raw"; _make_raw(raw_dir)
    rows, conds, st = _graph_args(raw_dir, tmp_path / "subjects")
    cache = tmp_path / "graph.json"
    payload = build_graph_payload(rows, st, conds, cache_path=cache)

    assert payload["version"]
    assert payload["counts"]["nodes"] == len(payload["nodes"])  # 2 RUN + 1 SUBJECT(math)
    # counts sanity
    assert payload["counts"]["nodes"] == len(payload["nodes"])
    assert payload["counts"]["edges"] == len(payload["edges"])

    # Everything must serialize to JSON, and absent similarity scores must be
    # explicit null (never 0) for belongs_to/comparability edges.
    blob = json.dumps(payload)
    for e in payload["edges"]:
        if e["kind"] in ("belongs_to", "comparability"):
            assert e["score"] is None
    # comparability HIGHLY_CONTROLLED present (same domain, seed differs), no %.
    comps = [e for e in payload["edges"] if e["kind"] == "comparability"]
    assert comps and comps[0]["meta"]["comparability_kind"] == "HIGHLY_CONTROLLED"
    assert comps[0]["score"] is None
    assert "HIGHLY_CONTROLLED" in blob


def test_empty_graph(tmp_path):
    st = SubjectTree(root=tmp_path / "subjects")
    payload = build_graph_payload([], st, {}, cache_path=tmp_path / "g.json")
    assert payload["counts"]["nodes"] == 0
    assert payload["counts"]["edges"] == 0
    assert payload["counts"]["clusters"] == 0
    assert payload["cache"]["source_fingerprint"]


def test_isolated_nodes_no_similarity(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "x.jsonl").write_text(_raw_line("t1", "x", "chem", 1, ["chem_molar"]) + "\n", encoding="utf-8")
    (raw_dir / "y.jsonl").write_text(_raw_line("t1", "y", "physics", 2, ["phys_tool"]) + "\n", encoding="utf-8")
    rows, conds, st = _graph_args(raw_dir, tmp_path / "subjects")
    payload = build_graph_payload(rows, st, conds, cache_path=tmp_path / "g.json")
    sim = [e for e in payload["edges"] if e["kind"] == "similarity"]
    assert sim == []  # no shared tool/worker -> isolated
    belongs = [e for e in payload["edges"] if e["kind"] == "belongs_to"]
    assert len(belongs) == 2


def test_cache_reuse_and_source_invalidation(tmp_path):
    raw_dir = tmp_path / "raw"; _make_raw(raw_dir)
    rows, conds, st = _graph_args(raw_dir, tmp_path / "subjects")
    cache = tmp_path / "g.json"
    p1 = build_graph_payload(rows, st, conds, cache_path=cache)
    p2 = build_graph_payload(rows, st, conds, cache_path=cache)
    # Same sources+params -> same fingerprints (reusable).
    assert p1["cache"]["source_fingerprint"] == p2["cache"]["source_fingerprint"]
    assert p1["cache"]["params_fingerprint"] == p2["cache"]["params_fingerprint"]
    # A source change (new run appeared in the index rows) flips the fingerprint.
    extra_row = {"experiment_id": "exp_c", "subject": "math", "tools": [], "workers": [],
                 "seed": 3, "generator_strategy": "x", "execution_mode": "deterministic"}
    rows2 = rows + [extra_row]
    p3 = build_graph_payload(rows2, st, conds, cache_path=cache)
    assert p3["cache"]["source_fingerprint"] != p1["cache"]["source_fingerprint"]


def test_raw_files_never_modified_by_graph_build(tmp_path):
    raw_dir = tmp_path / "raw"; _make_raw(raw_dir)
    before = _raw_snapshot(raw_dir)
    rows, conds, st = _graph_args(raw_dir, tmp_path / "subjects")
    for _ in range(2):  # build + cache round-trip
        build_graph_payload(rows, st, conds, cache_path=tmp_path / "g.json")
    after = _raw_snapshot(raw_dir)
    assert before == after, "RAW evidence must be byte-identical after graph building"


def test_endpoint_wiring_uses_same_conditions_source(tmp_path):
    # The endpoint derives rows via the cached index + conditions via
    # load_experiment().condition — assert the compare index (used by the
    # endpoint `load_index()`) yields the same experiment ids as the RAW.
    raw_dir = tmp_path / "raw"; _make_raw(raw_dir)
    idx = load_index(raw_dir=raw_dir)
    ids = [r["experiment_id"] for r in idx["experiments"]]
    assert ids == sorted(ids)
    assert set(ids) == {"exp_a", "exp_b"}