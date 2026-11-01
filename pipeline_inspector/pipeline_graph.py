"""Graphe du pipeline — construit à partir des transitions observées.

Le schéma de la spécification (USER REQUEST → AGENT → ROUTING → LLM → TOOL →
SECURITY → RESULT → VALIDATION → RESPONSE) est conservé comme *hypothèse*
(documentation et comparaison), mais le graphe renvoyé est **uniquement**
composé des transitions réellement vues dans les logs.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .correlation import group_sessions

HYPOTHESIS_STAGES = [
    "PIPELINE_START",
    "AGENT_SELECTED",
    "ROUTING_DECISION",
    "MODEL_REQUEST",
    "MODEL_RESPONSE",
    "TOOL_CALL",
    "TOOL_RESULT",
    "SECURITY_REVIEW",
    "SECURITY_APPROVE",
    "EXECUTION_RESULT",
    "TEST_RESULT",
    "PIPELINE_COMPLETE",
]

# Étapes de la spec qui n'ont aucun équivalent observé direct
HYPOTHESIS_LABELS = {
    "PIPELINE_START": "USER REQUEST",
    "AGENT_SELECTED": "HERMES AGENT",
    "ROUTING_DECISION": "MODEL ROUTING",
    "MODEL_REQUEST": "LOCAL LLM (request)",
    "MODEL_RESPONSE": "LOCAL LLM (response)",
    "TOOL_CALL": "TOOL EXECUTION",
    "TOOL_RESULT": "EXECUTION RESULT",
    "SECURITY_REVIEW": "SECURITY REVIEW",
    "SECURITY_APPROVE": "SECURITY DECISION",
    "TEST_RESULT": "VALIDATION",
    "PIPELINE_COMPLETE": "FINAL RESPONSE",
}


def build_graph(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Nœuds + arêtes pondérés, issus des enchaînements observés."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[tuple, Dict[str, Any]] = {}

    for ev in events:
        t = ev.get("event_type") or "UNKNOWN"
        node = nodes.setdefault(t, {"id": t, "count": 0, "ok": 0, "fail": 0, "sources": set()})
        node["count"] += 1
        if ev.get("ok") is True:
            node["ok"] += 1
        elif ev.get("ok") is False:
            node["fail"] += 1
        if ev.get("source"):
            node["sources"].add(ev["source"])

    for group in group_sessions(events).values():
        for a, b in zip(group, group[1:]):
            ta, tb = a.get("event_type"), b.get("event_type")
            if not ta or not tb or ta == tb:
                continue
            key = (ta, tb)
            edge = edges.setdefault(key, {"from": ta, "to": tb, "count": 0, "examples": []})
            edge["count"] += 1
            if len(edge["examples"]) < 3:
                edge["examples"].append({
                    "session": b.get("session_id") or b.get("run_id"),
                    "timestamp": b.get("timestamp_iso"),
                })

    observed = set(nodes)
    return {
        "nodes": [
            {
                "id": n["id"],
                "label": HYPOTHESIS_LABELS.get(n["id"], n["id"]),
                "count": n["count"],
                "ok": n["ok"],
                "fail": n["fail"],
                "sources": sorted(n["sources"]),
                "in_hypothesis": n["id"] in HYPOTHESIS_STAGES,
            }
            for n in sorted(nodes.values(), key=lambda x: -x["count"])
        ],
        "edges": sorted(
            [
                {"from": e["from"], "to": e["to"], "count": e["count"], "examples": e["examples"]}
                for e in edges.values()
            ],
            key=lambda x: -x["count"],
        )[:200],
        "observed_stages": sorted(observed),
        "hypothesis_stages": HYPOTHESIS_STAGES,
        "hypothesis_only": [s for s in HYPOTHESIS_STAGES if s not in observed],
        "observed_not_in_hypothesis": sorted(s for s in observed if s not in HYPOTHESIS_STAGES),
    }
