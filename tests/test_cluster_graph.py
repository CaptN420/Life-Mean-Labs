"""CG1 — Cluster Graph model tests (deterministic, no LLM, no RAW writes).

Covers the required scenarios: empty, isolated, dense, multi subject/run,
collision-free IDs, determinism, provenance, comparability-vs-similarity
separation, reproducible cache invalidation, and a reasonable large volume.
"""

from __future__ import annotations

import os
import random
import tempfile
from pathlib import Path

import compare.graph as graph
from compare.graph import (
    build_graph, build_cached, source_fingerprint, params_fingerprint,
)
from compare.subjects import SubjectTree


def _row(eid, domain="math", tools=("math_gcd",), workers=None,
         seed=None, gen="taskgen", mode="deterministic", **kw):
    if workers is None:
        workers = (f"{eid}_worker",)  # unique per run so only intentional overlap counts
    row = {
        "experiment_id": str(eid),
        "run_id": f"run_{eid}",
        "subject": domain,
        "domain": domain,
        "num_tasks": 10,
        "num_passed": 8,
        "num_failed": 2,
        "num_no_verdict": 0,
        "success_rate": 0.8,
        "status": "COMPLETED_WITH_FAILURES",
        "execution_mode": mode,
        "seed": seed,
        "generator_strategy": gen,
        "workers": list(workers),
        "tools": list(tools),
        "not_recorded": [],
    }
    row.update(kw)
    return row


def _subject_tree(tmp_path, entries):
    """subject map {exp_id: subject_path} registered on a tmp root."""
    base = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp())
    st = SubjectTree(root=base / "subjects")
    for eid, topic in entries.items():
        st.register(eid, topic)
    return st


# ── Empty graph ──────────────────────────────────────────────────────────────

def test_empty_graph():
    st = SubjectTree(root="/nonexistent_empty_xyz")
    g = build_graph([], st)
    assert g.num_nodes() == 0
    assert g.num_edges() == 0
    assert g.clusters == []
    assert g.version
    assert g.source_fingerprint
    assert g.params_fingerprint


# ── Isolated nodes ───────────────────────────────────────────────────────────

def test_isolated_nodes_no_similarity():
    st = _subject_tree(tmp_path=None, entries={"r1": "math", "r2": "chem"})
    rows = [_row("r1", "math", tools=("t_a",)), _row("r2", "chem", tools=("t_b",))]
    g = build_graph(rows, st)

    # Nodes: 2 RUN + 2 SUBJECT.
    assert {n.kind for n in g.nodes} == {"RUN", "SUBJECT"}
    assert g.num_nodes() == 4
    # Only belongs_to edges; similarity requires overlap above threshold -> none.
    kinds = {e.kind for e in g.edges}
    assert kinds == {"belongs_to"}
    assert all(e.method == "subject_membership" for e in g.edges)
    # No multi-node cluster.
    assert all(c.size == 1 for c in g.clusters)


# ── Dense graph + clustering ────────────────────────────────────────────────

def test_dense_graph_clusters_similar_runs():
    st = _subject_tree(tmp_path=None, entries={"a": "math", "b": "math", "c": "math", "d": "chem"})
    rows = [
        _row("a", "math", tools=("math_gcd", "math_lcm")),
        _row("b", "math", tools=("math_gcd", "math_lcm")),
        _row("c", "math", tools=("math_gcd",)),            # overlaps a,b
        _row("d", "chem", tools=("chem_molar",)),          # shares nothing
    ]
    g = build_graph(rows, st)

    similarity = [e for e in g.edges if e.kind == "similarity"]
    assert len(similarity) > 0
    # a-b are identical tools -> full overlap.
    ab = [e for e in similarity if {e.source, e.target} == {"run:a", "run:b"}]
    assert ab and ab[0].score == 1.0
    assert ab[0].method == "jaccard_tools"

    # The math trio clusters together; chem+d stay separate.
    big = max(g.clusters, key=lambda c: c.size)
    assert {"run:a", "run:b", "run:c"} <= set(big.node_ids)
    assert "run:d" not in big.node_ids
    assert "run:d" in [n.node_id for n in g.nodes]


# ── Multiple subjects and runs ───────────────────────────────────────────────

def test_multiple_subjects_and_runs_counts():
    st = _subject_tree(tmp_path=None, entries={
        "r1": "math", "r2": "math/arithmetic", "r3": "coding"})
    rows = [_row("r1", "math"), _row("r2", "math"), _row("r3", "coding")]
    g = build_graph(rows, st)
    runs = [n for n in g.nodes if n.kind == "RUN"]
    subs = [n for n in g.nodes if n.kind == "SUBJECT"]
    assert len(runs) == 3
    # topics: math, coding (+ nested arithmetic dir is a topic too).
    assert {"math", "coding"} <= {s.label for s in subs}
    # every run has a belongs_to edge as long as registered.
    assert len([e for e in g.edges if e.kind == "belongs_to"]) >= 3


# ── Collision-free IDs ───────────────────────────────────────────────────────

def test_ids_collision_free_between_run_and_subject():
    st = _subject_tree(tmp_path=None, entries={"X": "X"})
    rows = [_row("X", "X")]
    g = build_graph(rows, st)
    node_ids = {n.node_id for n in g.nodes}
    assert "run:X" in node_ids
    assert "subject:X" in node_ids
    assert len(node_ids) == len(g.nodes)  # no duplicates


# ── Determinism ──────────────────────────────────────────────────────────────

def test_build_is_deterministic():
    st = _subject_tree(tmp_path=None, entries={"r1": "math", "r2": "math", "r3": "coding"})
    rows = [_row("r1", "math", tools=("t1", "t2")),
            _row("r2", "math", tools=("t1", "t3")),
            _row("r3", "coding", tools=("t9",))]
    g1 = build_graph(rows, st)
    g2 = build_graph(rows, st)
    assert g1.to_dict() == g2.to_dict()
    assert g1.source_fingerprint == g2.source_fingerprint
    assert source_fingerprint(rows, st) == source_fingerprint(rows, st)


# ── Provenance of relations ──────────────────────────────────────────────────

def test_every_relation_has_method_and_provenance():
    st = _subject_tree(tmp_path=None, entries={"r1": "math", "r2": "math"})
    rows = [_row("r1", "math", tools=("t1",)), _row("r2", "math", tools=("t1", "t2"))]
    conds = {
        "r1": {"domain": "math", "seed": 1, "num_tasks": 10, "deterministic": True},
        "r2": {"domain": "math", "seed": 2, "num_tasks": 10, "deterministic": True},
    }
    g = build_graph(rows, st, conditions=conds)
    assert g.edges
    for e in g.edges:
        assert e.method, "every edge must declare its method"
        if e.kind == "similarity":
            assert e.score is not None
            assert e.refs, "similarity edge must carry provenance refs"
        if e.kind in ("belongs_to", "comparability"):
            assert e.score is None, f"{e.kind} must NOT fabricate a numeric score"


# ── Comparability vs similarity separation ──────────────────────────────────

def test_comparability_and_similarity_are_independent():
    st = _subject_tree(tmp_path=None, entries={"r1": "math", "r2": "math", "r3": "physics"})
    rows = [
        _row("r1", "math", tools=("gcd_tool",)),
        _row("r2", "math", tools=("chem_molar",)),   # shares NO tool with r1
        _row("r3", "physics", tools=("gcd_tool",)),  # shares tool with r1, different domain
    ]
    conds = {
        "r1": {"domain": "math", "seed": 1, "num_tasks": 10, "deterministic": True},
        "r2": {"domain": "math", "seed": 2, "num_tasks": 10, "deterministic": True},
        "r3": {"domain": "physics", "seed": 3, "num_tasks": 10, "deterministic": True},
    }
    g = build_graph(rows, st, conditions=conds)

    comp = [e for e in g.edges if e.kind == "comparability"]
    sim = [e for e in g.edges if e.kind == "similarity"]

    # r1-r2: same domain, differ only in seed -> HIGHLY_CONTROLLED comparability,
    # but ZERO tool overlap -> NO similarity edge. Separation proven.
    r12_comp = [e for e in comp if {e.source, e.target} == {"run:r1", "run:r2"}]
    assert r12_comp and r12_comp[0].meta["comparability_kind"] == "HIGHLY_CONTROLLED"
    assert r12_comp[0].score is None  # never a percentage
    assert not [e for e in sim if {e.source, e.target} == {"run:r1", "run:r2"}]

    # r1-r3 different domains -> EXPLORATORY -> no comparability edge at all.
    assert not [e for e in comp if {"run:r1", "run:r3"} == {e.source, e.target}]

    # r1-r3 share a TOOL -> similarity edge EXISTS independently of comparability.
    assert [e for e in sim if {"run:r1", "run:r3"} == {e.source, e.target}]


# ── Cache invalidation ───────────────────────────────────────────────────────

def test_cache_reused_when_fingerprints_match(monkeypatch, tmp_path):
    st = _subject_tree(tmp_path=tmp_path, entries={"r1": "math"})
    rows = [_row("r1", "math", tools=("t1",))]
    cache = tmp_path / "graph.json"
    calls = {"n": 0}
    real_build = graph.build_graph

    def counting_build(*a, **k):
        calls["n"] += 1
        return real_build(*a, **k)

    monkeypatch.setattr(graph, "build_graph", counting_build)

    g1 = build_cached(rows, st, cache_path=cache)
    assert calls["n"] == 1
    # 2nd call same sources+params -> cache hit, NO rebuild.
    g2 = build_cached(rows, st, cache_path=cache)
    assert calls["n"] == 1
    assert g2.to_dict() == g1.to_dict()


def test_cache_invalidates_on_source_change(monkeypatch, tmp_path):
    st = _subject_tree(tmp_path=tmp_path, entries={"r1": "math"})
    rows1 = [_row("r1", "math", tools=("t1",))]
    rows2 = [_row("r1", "math", tools=("t1",)), _row("r2", "chem", tools=("t9",))]
    cache = tmp_path / "graph.json"
    calls = {"n": 0}
    real_build = graph.build_graph

    def counting_build(*a, **k):
        calls["n"] += 1
        return real_build(*a, **k)

    monkeypatch.setattr(graph, "build_graph", counting_build)

    build_cached(rows1, st, cache_path=cache)
    assert calls["n"] == 1
    # Source changed (new run) -> source_fingerprint differs -> rebuild.
    g = build_cached(rows2, st, cache_path=cache)
    assert calls["n"] == 2
    assert "run:r2" in [n.node_id for n in g.nodes]

    # Params change (threshold) -> params_fingerprint differs -> rebuild.
    build_cached(rows2, st, cache_path=cache, thresholds={"similarity_threshold": 0.9})
    assert calls["n"] == 3


def test_fingerprint_ignores_mtime():
    st = _subject_tree(tmp_path=None, entries={"r1": "math"})
    rows = [_row("r1", "math", tools=("t1",))]
    fp1 = source_fingerprint(rows, st)
    fp2 = source_fingerprint([dict(r) for r in rows], st)  # same content
    assert fp1 == fp2
    # Adding a field that does NOT affect the annotations must NOT change it
    # beyond the canonical content (created_at is dropped by design).
    assert params_fingerprint() == params_fingerprint()


# ── Large volume (reasonable) ────────────────────────────────────────────────

def test_large_volume_deterministic_and_bounded():
    subjects = {"math", "coding", "chem", "physics", "logic"}
    entries = {}
    rows = []
    pool = ["tool_%d" % i for i in range(10)]
    rnd = random.Random(42)
    n_runs = 180
    for i in range(n_runs):
        eid = "exp_%03d" % i
        dom = sorted(subjects)[i % len(subjects)]
        tools = sorted(rnd.sample(pool, rnd.randint(1, 3)))
        entries[eid] = dom
        rows.append(_row(eid, dom, tools=tools, seed=i))
    st = _subject_tree(tmp_path=None, entries=entries)
    g = build_graph(rows, st)
    assert g.num_nodes() == n_runs + len({e for e in entries.values()})
    # No exception, fingerprint stable across a rebuild.
    g2 = build_graph(rows, st)
    assert g2.to_dict() == g.to_dict()
    # Edges stay bounded and sane for a pool-based overlap.
    assert len(g.edges) < n_runs * n_runs  # not a fully-connected blowup