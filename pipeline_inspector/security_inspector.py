"""Inspection des décisions de sécurité.

Une réponse ``APPROVE`` n'est pas une preuve de sûreté : elle prouve qu'un
composant a autorisé. On distingue donc :
- demande de revue ;
- décision (approve / deny / escalate) ;
- exécution observée ;
- résultat.

Les incohérences sont signalées avec leur niveau de certitude, jamais
transformées en accusation automatique.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from .schemas import EventType

SECURITY_TYPES = {
    EventType.SECURITY_REVIEW.value,
    EventType.SECURITY_APPROVE.value,
    EventType.SECURITY_DENY.value,
    EventType.SECURITY_ESCALATE.value,
}
EXECUTION_TYPES = {
    EventType.TOOL_CALL.value,
    EventType.FILE_PATCH.value,
    EventType.TOOL_RESULT.value,
    EventType.TEST_EXECUTION.value,
}


def _key(ev: Dict[str, Any]) -> Optional[str]:
    for k in ("task_id", "session_id", "conversation_id", "run_id"):
        if ev.get(k):
            return f"{k}:{ev[k]}"
    return None


def analyze(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions = [e for e in events if e.get("event_type") in SECURITY_TYPES]
    executions = [e for e in events if e.get("event_type") in EXECUTION_TYPES]

    by_decision = Counter(e.get("event_type") for e in decisions)
    by_operation = Counter((e.get("metadata") or {}).get("operation") for e in decisions)
    by_component = Counter(e.get("agent") for e in decisions)

    # Regroupement par clé observée, sans inférence
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for ev in decisions + executions:
        key = _key(ev)
        if key:
            by_key.setdefault(key, []).append(ev)

    inconsistencies: List[Dict[str, Any]] = []
    for key, group in by_key.items():
        group.sort(key=lambda e: e.get("timestamp") or 0)
        types = [e.get("event_type") for e in group]
        denied = EventType.SECURITY_DENY.value in types
        executed_after = False
        seen_deny = False
        for ev in group:
            if ev.get("event_type") == EventType.SECURITY_DENY.value:
                seen_deny = True
            elif seen_deny and ev.get("event_type") in EXECUTION_TYPES:
                executed_after = True
        if denied and executed_after:
            inconsistencies.append({
                "kind": "denied_but_executed",
                "key": key,
                "confidence": "probable",
                "detail": "Une décision DENY est suivie d'une exécution observée sur la même clé.",
                "events": [e.get("event_id") for e in group][:10],
            })
        approved = EventType.SECURITY_APPROVE.value in types
        if approved and not any(t in EXECUTION_TYPES for t in types):
            inconsistencies.append({
                "kind": "approved_without_execution",
                "key": key,
                "confidence": "certain" if key.startswith("task_id:") else "probable",
                "detail": "Décision APPROVE observée sans exécution associée sur la même clé.",
                "events": [e.get("event_id") for e in group][:10],
            })
        if EventType.SECURITY_REVIEW.value in types and not (
            approved or denied or EventType.SECURITY_ESCALATE.value in types
        ):
            inconsistencies.append({
                "kind": "review_without_decision",
                "key": key,
                "confidence": "certain",
                "detail": "Revue de sécurité sans décision enregistrée.",
                "events": [e.get("event_id") for e in group][:10],
            })

    # Décisions orphelines (aucune clé) : honnêtement non corrélées
    uncorrelated = sum(1 for e in decisions if not _key(e))

    timeline = [
        {
            "event_id": e.get("event_id"),
            "timestamp": e.get("timestamp_iso") or e.get("timestamp"),
            "decision": e.get("event_type"),
            "operation": (e.get("metadata") or {}).get("operation"),
            "reason": (e.get("metadata") or {}).get("reason"),
            "component": e.get("agent"),
            "task_id": e.get("task_id"),
            "correlation": e.get("correlation"),
            "confidence": e.get("confidence"),
        }
        for e in sorted(decisions, key=lambda x: x.get("timestamp") or 0)[:500]
    ]

    return {
        "total_decisions": len(decisions),
        "by_decision": dict(by_decision),
        "by_operation": {k: v for k, v in by_operation.items() if k},
        "by_component": {k: v for k, v in by_component.items() if k},
        "executions_observed": len(executions),
        "inconsistencies": inconsistencies,
        "inconsistency_count": len(inconsistencies),
        "decisions_without_correlation_key": uncorrelated,
        "timeline": timeline,
        "caveat": (
            "APPROVE ne prouve pas la sûreté de l'opération. "
            "Les liens sont explicites (même task_id) ou probables, jamais certains sans identifiant partagé."
        ),
    }
