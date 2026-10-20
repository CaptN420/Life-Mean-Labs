"""Compare — Cluster Graph (CG1): deterministic graph model over the lab runs.

Reusable model that both the Tree and the Graph views consume. It builds
TYPE NODES (SUBJECT / RUN) and THREE SEPARATE edge categories from the data
that already exists, deterministic-only (no LLM, no RAW writes):

- **belongs_to**   : a RUN belongs to a SUBJECT        (SubjectTree membership)
- **similarity**   : measurable overlap between feature sets (tools, workers)
                     and between subject run-sets (Jaccard). Numeric score.
- **comparability** : whether two runs share experimental conditions that make
                     a comparison meaningful (REUSES ``compare_pair``). NEVER
                     converted into a similarity percentage; carries the raw
                     ``ComparabilityKind`` + reason as metadata instead.

Clusters: simple deterministic connected components over the similarity edges
above a documented threshold (no heavy libraries, no community algorithms).

Cache: keyed by an ALGORITHM version + a SOURCE fingerprint (SHA-256 over the
annotations that actually matter, NOT file mtimes) + a PARAMS fingerprint.
Recompute happens if and only if one of those changes; otherwise the cached
graph is reused. Reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from compare.models import RunMetrics
from compare.comparability import compare_pair, ComparabilityKind
from compare.subjects import SubjectTree

# ── Constants ─────────────────────────────────────────────────────────────────

GRAPH_VERSION = "cg1-1.0"
ALGORITHM = "connected-components"
DEFAULT_THRESHOLDS = {"similarity_threshold": 0.2}
# Comparability levels that actually make a comparison meaningful. EXPLORATORY
# and NOT_DIRECTLY_COMPARABLE pairs are NOT emitted (honest: no misleading edge).
_COMPARABLE_KINDS = {
    ComparabilityKind.HIGHLY_CONTROLLED,
    ComparabilityKind.PARTIALLY_CONTROLLED,
}


class ClusterGraphError(RuntimeError):
    """Raised for an invalid graph build/cache operation."""


# ── Model ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Node:
    node_id: str            # stable, namespaced: "run:<eid>" | "subject:<path>"
    kind: str               # "RUN" | "SUBJECT"
    label: str
    subject: str            # subject path ("" when unknown for a run)
    refs: List[str] = field(default_factory=list)   # provenance: RAW path, tree root
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "subject": self.subject,
            "refs": sorted(self.refs),
            "meta": self.meta,
        }


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str               # "belongs_to" | "similarity" | "comparability"
    method: str             # e.g. "subject_membership" | "jaccard_tools" ...
    score: Optional[float]  # Only meaningful for similarity (None elsewhere).
    meta: Dict[str, Any] = field(default_factory=dict)
    refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "method": self.method,
            "score": self.score,
            "meta": self.meta,
            "refs": sorted(self.refs),
        }


@dataclass(frozen=True)
class Cluster:
    cluster_id: str
    node_ids: List[str]     # sorted
    edges: List[Edge]       # similarity edges inside the cluster
    size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "node_ids": list(self.node_ids),
            "edges": [e.to_dict() for e in self.edges],
            "size": self.size,
        }


@dataclass
class ClusterGraph:
    version: str
    algorithm: str
    thresholds: Dict[str, float]
    source_fingerprint: str
    params_fingerprint: str
    nodes: List[Node]
    edges: List[Edge]
    clusters: List[Cluster]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "algorithm": self.algorithm,
            "thresholds": dict(self.thresholds),
            "source_fingerprint": self.source_fingerprint,
            "params_fingerprint": self.params_fingerprint,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "clusters": [c.to_dict() for c in self.clusters],
        }

    def num_nodes(self) -> int:
        return len(self.nodes)

    def num_edges(self) -> int:
        return len(self.edges)


# ── Fingerprints (cache invalidation, NOT mtime-based) ───────────────────────

def _canonical(value: Any) -> str:
    """Deterministic canonical serialization (sorted keys / lists)."""
    if isinstance(value, dict):
        return json.dumps(
            {k: _canonical(v) for k, v in sorted(value.items())},
            sort_keys=True, separators=(",", ":"))
    if isinstance(value, (list, tuple)):
        return json.dumps([_canonical(v) for v in sorted(_homogenize(value))],
                          sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _homogenize(values: Sequence[Any]) -> List[Any]:
    """Normalise mixed types so sorting never raises (str-ify non-strings)."""
    out = []
    for v in values:
        out.append(v if isinstance(v, (str, int, float)) else str(v))
    return out


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def params_fingerprint(version: str = GRAPH_VERSION,
                       algorithm: str = ALGORITHM,
                       thresholds: Optional[Dict[str, float]] = None) -> str:
    """Fingerprint over the algorithm settings (reproducible invalidation)."""
    th = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    return _sha256(_canonical({"version": version, "algorithm": algorithm,
                               "thresholds": th}))


def source_fingerprint(rows: Sequence[Dict[str, Any]],
                       subjects: SubjectTree,
                       conditions: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """SHA-256 over the run annotations + subject membership, NOT file mtimes.

    Deterministic: rows sorted by experiment_id, all lists/dicts canonicalized.
    """
    conds = conditions or {}
    entries = []
    for row in rows:
        eid = str(row.get("experiment_id", ""))
        topic = subjects.subject_of(eid)
        entries.append({
            "experiment_id": eid,
            "run_id": str(row.get("run_id", "") or ""),
            "subject": topic or "",
            "domain": str(row.get("subject") or row.get("domain") or ""),
            "generator_strategy": str(row.get("generator_strategy") or ""),
            "execution_mode": str(row.get("execution_mode") or ""),
            "seed": row.get("seed"),
            "tools": sorted(_homogenize(row.get("tools") or [])),
            "workers": sorted(_homogenize(row.get("workers") or [])),
            "condition": conds.get(eid, {}),
        })
    entries.sort(key=lambda e: e["experiment_id"])
    return _sha256(_canonical(entries))


def _raw_ref(eid: str) -> str:
    return f"data/raw_debates/{eid}.jsonl"


# ── Build ─────────────────────────────────────────────────────────────────────

def _nodes(rows: Sequence[Dict[str, Any]], subjects: SubjectTree
           ) -> Dict[str, Node]:
    """Build RUN + SUBJECT nodes with stable, collision-free IDs."""
    nodes: Dict[str, Node] = {}
    for row in sorted(rows, key=lambda r: str(r.get("experiment_id", ""))):
        eid = str(row.get("experiment_id", ""))
        topic = subjects.subject_of(eid) or ""
        node_id = f"run:{eid}"
        nodes[node_id] = Node(
            node_id=node_id,
            kind="RUN",
            label=eid,
            subject=topic,
            refs=[_raw_ref(eid)],
            meta={
                "domain": str(row.get("subject") or row.get("domain") or ""),
                "execution_mode": str(row.get("execution_mode") or ""),
                "generator_strategy": str(row.get("generator_strategy") or ""),
                "seed": row.get("seed"),
                "num_tasks": row.get("num_tasks", 0),
                "num_passed": row.get("num_passed", 0),
                "num_failed": row.get("num_failed", 0),
                "success_rate": float(row.get("success_rate", 0.0)),
            },
        )
    # SUBJECT nodes from the tree (flattened), sorted for determinism.
    for topic in sorted(subjects.topics()):
        subject_path = _subject_key(topic)
        nodes[f"subject:{subject_path}"] = Node(
            node_id=f"subject:{subject_path}",
            kind="SUBJECT",
            label=topic,
            subject=subject_path,
            refs=[str(subjects.root)] if subjects.tree() else [],
            meta={"num_runs": len(subjects.experiment_ids(topic))},
        )
    return nodes


def _subject_key(topic: str) -> str:
    """Stable key for a subject path (slash-joined to avoid '' ambiguity)."""
    return topic.strip("/") or "_root_"


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _overlap_edges(rows: Sequence[Dict[str, Any]],
                   threshold: float) -> List[Edge]:
    """RUN↔RUN similarity edges per feature set (tools, workers)."""
    edges: List[Edge] = []
    rs = sorted(rows, key=lambda r: str(r.get("experiment_id", "")))
    n = len(rs)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = rs[i], rs[j]
            aid, bid = str(a["experiment_id"]), str(b["experiment_id"])
            at = sorted(_homogenize(a.get("tools") or []))
            bt = sorted(_homogenize(b.get("tools") or []))
            t = _jaccard(at, bt)
            if t >= threshold and t > 0.0:
                edges.append(Edge(f"run:{aid}", f"run:{bid}", "similarity",
                                  "jaccard_tools", score=round(t, 6),
                                  refs=[_raw_ref(aid), _raw_ref(bid)]))
            aw = sorted(_homogenize(a.get("workers") or []))
            bw = sorted(_homogenize(b.get("workers") or []))
            w = _jaccard(aw, bw)
            if w >= threshold and w > 0.0:
                edges.append(Edge(f"run:{aid}", f"run:{bid}", "similarity",
                                  "jaccard_workers", score=round(w, 6),
                                  refs=[_raw_ref(aid), _raw_ref(bid)]))
    return edges


def _subject_overlap_edges(rows: Sequence[Dict[str, Any]],
                           subjects: SubjectTree,
                           threshold: float) -> List[Edge]:
    """SUBJECT↔SUBJECT similarity = Jaccard over each subject's run sets."""
    edges: List[Edge] = []
    topics = sorted(subjects.topics())
    for i in range(len(topics)):
        ida = subjects.experiment_ids(topics[i])
        sa = set(ida)
        for j in range(i + 1, len(topics)):
            sb = set(subjects.experiment_ids(topics[j]))
            inter = len(sa & sb)
            union = len(sa | sb)
            if union == 0:
                continue
            score = inter / union
            if score >= threshold and score > 0.0:
                edges.append(Edge(
                    f"subject:{_subject_key(topics[i])}",
                    f"subject:{_subject_key(topics[j])}",
                    "similarity", "jaccard_run_overlap", score=round(score, 6),
                    refs=[str(subjects.root)],
                ))
    return edges


def _belongs_edges(rows: Sequence[Dict[str, Any]],
                   subjects: SubjectTree) -> List[Edge]:
    edges: List[Edge] = []
    for row in sorted(rows, key=lambda r: str(r.get("experiment_id", ""))):
        eid = str(row.get("experiment_id", ""))
        topic = subjects.subject_of(eid)
        if topic:
            # SUBJECT nodes are TOP-LEVEL topics (SubjectTree.topics()), so
            # a RUN in a nested subject points at its top-level topic node to
            # keep every edge's target inside the node set (no dangling).
            top = topic.split("/")[0]
            edges.append(Edge(f"run:{eid}", f"subject:{_subject_key(top)}",
                              "belongs_to", "subject_membership", score=None,
                              refs=[_raw_ref(eid)],
                              meta={"subject": topic}))
    return edges


def _comparability_edges(rows: Sequence[Dict[str, Any]],
                         conditions: Optional[Dict[str, Dict[str, Any]]]
                         ) -> List[Edge]:
    """RUN↔RUN comparability via the REAL compare_pair (reused, not reinvented).

    Emitted ONLY for HIGHLY_CONTROLLED / PARTIALLY_CONTROLLED. NO numeric
    score — the ComparabilityKind + reason ride in meta (never a percentage).
    """
    conds = conditions or {}
    metrics: Dict[str, RunMetrics] = {}
    for row in rows:
        eid = str(row.get("experiment_id", ""))
        cond = conds.get(eid)
        if cond is None:
            continue  # insufficient condition snapshot -> no comparability claim
        metrics[eid] = RunMetrics(
            experiment_id=eid,
            run_id=str(row.get("run_id", "") or ""),
            condition=dict(cond),
        )
    edges: List[Edge] = []
    for a in sorted(metrics):
        for b in sorted(metrics):
            if a >= b:
                continue
            outcome = compare_pair(metrics[a], metrics[b])
            if outcome.comparability not in _COMPARABLE_KINDS:
                continue
            edges.append(Edge(
                f"run:{a}", f"run:{b}", "comparability",
                "comparability_kind", score=None,
                meta={"comparability_kind": outcome.comparability,
                      "common_variables": dict(outcome.common_variables),
                      "changed_variables": dict(outcome.changed_variables),
                      "reason": outcome.reason},
                refs=[_raw_ref(a), _raw_ref(b)],
            ))
    return edges


def _connected_components(edges: Sequence[Edge], node_ids: Sequence[str]
                          ) -> List[List[str]]:
    """Union-find over the *similarity* edges (documented, deterministic)."""
    parent = {nid: nid for nid in node_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for e in edges:
        if e.kind == "similarity" and e.source in parent and e.target in parent:
            union(e.source, e.target)
    comp_map: Dict[str, List[str]] = {}
    for nid in node_ids:
        comp_map.setdefault(find(nid), []).append(nid)
    comps = [sorted(members) for members in comp_map.values()]
    # Deterministic ordering (components are already sorted lists of ids).
    return sorted(comps)


def _clusters(comps: Sequence[Sequence[str]],
              edges: Sequence[Edge]) -> List[Cluster]:
    by_kind = [e for e in edges if e.kind == "similarity"]
    out: List[Cluster] = []
    for comp in comps:
        members = set(comp)
        inside = [e for e in by_kind if e.source in members and e.target in members]
        out.append(Cluster(
            cluster_id=f"cluster:{sorted(comp)[0]}",
            node_ids=sorted(comp),
            edges=inside,
            size=len(comp),
        ))
    return sorted(out, key=lambda c: c.cluster_id)


def build_graph(rows: Sequence[Dict[str, Any]],
                subjects: SubjectTree,
                conditions: Optional[Dict[str, Dict[str, Any]]] = None,
                version: str = GRAPH_VERSION,
                algorithm: str = ALGORITHM,
                thresholds: Optional[Dict[str, float]] = None) -> ClusterGraph:
    """Build the deterministic cluster graph from existing data (read-only)."""
    th = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    similarity_threshold = float(th.get("similarity_threshold", 0.2))

    nodes = _nodes(rows, subjects)
    node_ids = sorted(nodes)

    if not rows and not subjects.topics():
        cluster_list: List[Cluster] = []
        edges: List[Edge] = []
    else:
        edges = (
            _belongs_edges(rows, subjects)
            + _overlap_edges(rows, similarity_threshold)
            + _subject_overlap_edges(rows, subjects, similarity_threshold)
            + _comparability_edges(rows, conditions)
        )
        cluster_list = _clusters(_connected_components(edges, node_ids), edges)

    return ClusterGraph(
        version=version,
        algorithm=algorithm,
        thresholds=th,
        source_fingerprint=source_fingerprint(rows, subjects, conditions),
        params_fingerprint=params_fingerprint(version, algorithm, th),
        nodes=list(nodes.values()),
        edges=edges,
        clusters=cluster_list,
    )


# ── Cache (fingerprint-keyed, mtime-independent) ─────────────────────────────

def save_graph(graph: ClusterGraph, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = graph.to_dict()
    payload["_meta"] = {"saved_by": "CG1", "format": "cluster_graph"}
    tmp = path.with_suffix(".graph.json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_graph(path: Path) -> Optional[ClusterGraph]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _from_payload(payload)


def _from_payload(payload: Dict[str, Any]) -> ClusterGraph:
    nodes = [Node(**{k: n[k] for k in ("node_id", "kind", "label", "subject",
                                       "refs", "meta")}) for n in payload.get("nodes", [])]
    edges = [Edge(source=e["source"], target=e["target"], kind=e["kind"],
                  method=e["method"], score=e.get("score"),
                  meta=e.get("meta", {}), refs=e.get("refs", []))
             for e in payload.get("edges", [])]
    clusters = [Cluster(cluster_id=c["cluster_id"], node_ids=c["node_ids"],
                        edges=[Edge(**{k: ed.get(k) for k in
                                       ("source", "target", "kind", "method")},
                                score=ed.get("score"), meta=ed.get("meta", {}),
                                refs=ed.get("refs", [])) for ed in c.get("edges", [])],
                        size=c["size"])
                for c in payload.get("clusters", [])]
    return ClusterGraph(
        version=payload.get("version", GRAPH_VERSION),
        algorithm=payload.get("algorithm", ALGORITHM),
        thresholds=payload.get("thresholds", dict(DEFAULT_THRESHOLDS)),
        source_fingerprint=payload.get("source_fingerprint", ""),
        params_fingerprint=payload.get("params_fingerprint", ""),
        nodes=nodes, edges=edges, clusters=clusters,
    )


def build_cached(rows: Sequence[Dict[str, Any]],
                 subjects: SubjectTree,
                 conditions: Optional[Dict[str, Dict[str, Any]]] = None,
                 cache_path: Optional[Path] = None,
                 version: str = GRAPH_VERSION,
                 algorithm: str = ALGORITHM,
                 thresholds: Optional[Dict[str, float]] = None,
                 force: bool = False) -> ClusterGraph:
    """Return the cached graph if fingerprints match, else rebuild + save.

    Invalidation is reproducible: identical sources+params -> identical graph,
    regardless of file modification times.
    """
    src_fp = source_fingerprint(rows, subjects, conditions)
    prm_fp = params_fingerprint(version, algorithm, thresholds)
    if not force and cache_path is not None:
        cached = load_graph(cache_path)
        if cached is not None \
                and cached.source_fingerprint == src_fp \
                and cached.params_fingerprint == prm_fp:
            return cached
    graph = build_graph(rows, subjects, conditions, version, algorithm, thresholds)
    if cache_path is not None:
        save_graph(graph, cache_path)
    return graph