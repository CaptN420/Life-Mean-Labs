"""Corrélation d'événements — explicite, probable, inconnue.

Aucune corrélation n'est inventée : chaque lien porte sa force et sa raison.
Le store n'est jamais modifié par la corrélation ; les liens sont calculés à
la demande pour l'analyse et l'affichage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .schemas import Correlation, EventType

# Fenêtres utilisées pour qualifier un lien *probable* (jamais certain)
MODEL_WINDOW_S = 180.0
TOOL_WINDOW_S = 600.0
SECURITY_WINDOW_S = 180.0


@dataclass
class Link:
    source_event: str
    target_event: str
    relation: str
    reason: str
    strength: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.source_event,
            "to": self.target_event,
            "relation": self.relation,
            "reason": self.reason,
            "strength": round(self.strength, 3),
        }


def session_key(ev: Dict[str, Any]) -> Optional[str]:
    """Clé de session observée, par ordre de préférence. Jamais fabriquée."""
    for key in ("session_id", "run_id", "conversation_id", "task_id", "request_id"):
        value = ev.get(key)
        if value:
            return f"{key}:{value}"
    return None


def group_sessions(events: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events:
        key = session_key(ev)
        if not key:
            continue
        groups.setdefault(key, []).append(ev)
    for key in groups:
        groups[key].sort(key=lambda e: (e.get("timestamp") or 0, e.get("event_id") or ""))
    return groups


def _is_pair(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[Tuple[str, str, float]]:
    """Retourne (relation, raison, force) si a->b forme un lien plausible."""
    ta, tb = a.get("event_type"), b.get("event_type")
    dt = float(b.get("timestamp") or 0) - float(a.get("timestamp") or 0)

    if a.get("model_call_id") and a.get("model_call_id") == b.get("model_call_id"):
        return Correlation.EXPLICIT.value, "model_call_id identique", 1.0
    if a.get("correlation_id") and a.get("correlation_id") == b.get("correlation_id"):
        return Correlation.EXPLICIT.value, "correlation_id identique", 1.0
    # Un task_id partagé prouve l'appartenance à la MÊME TÂCHE, pas un lien
    # causal entre les deux événements : « probable », jamais « explicite ».
    if a.get("task_id") and a.get("task_id") == b.get("task_id"):
        return Correlation.PROBABLE.value, "task_id identique, ordre temporel", 0.85
    if a.get("session_id") and a.get("session_id") == b.get("session_id"):
        return Correlation.PROBABLE.value, "session_id identique, ordre temporel", 0.7

    if ta == EventType.MODEL_REQUEST.value and tb == EventType.MODEL_RESPONSE.value:
        if 0 <= dt <= MODEL_WINDOW_S and (a.get("agent") in (None, b.get("agent"))):
            return Correlation.PROBABLE.value, f"requête->réponse en {dt:.1f}s", 0.6
    if ta == EventType.MODEL_RESPONSE.value and tb == EventType.TOOL_CALL.value:
        if 0 <= dt <= TOOL_WINDOW_S:
            return Correlation.PROBABLE.value, f"réponse->outil en {dt:.1f}s", 0.5
    if ta == EventType.TOOL_CALL.value and tb == EventType.TOOL_RESULT.value:
        same_tool = (a.get("metadata") or {}).get("tool") == (b.get("metadata") or {}).get("tool")
        if 0 <= dt <= TOOL_WINDOW_S and same_tool:
            return Correlation.PROBABLE.value, "même outil dans la fenêtre", 0.65
    if ta == EventType.SECURITY_REVIEW.value and tb in {
        EventType.SECURITY_APPROVE.value, EventType.SECURITY_DENY.value,
        EventType.SECURITY_ESCALATE.value,
    }:
        if 0 <= dt <= SECURITY_WINDOW_S:
            return Correlation.PROBABLE.value, f"revue->décision en {dt:.1f}s", 0.6
    return None


def build_links(events: List[Dict[str, Any]]) -> List[Link]:
    """Liens entre événements consécutifs d'une même session."""
    links: List[Link] = []
    for group in group_sessions(events).values():
        for a, b in zip(group, group[1:]):
            pair = _is_pair(a, b)
            if pair:
                relation, reason, strength = pair
                links.append(Link(a["event_id"], b["event_id"], relation, reason, strength))
    return links


def annotate(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Retourne une copie des événements avec ``link_to_previous``.

    Un événement sans lien n'obtient *aucune* relation : le champ reste vide,
    l'interface l'affiche comme non corrélé.
    """
    by_session = group_sessions(events)
    links_by_target: Dict[str, Link] = {}
    for group in by_session.values():
        for a, b in zip(group, group[1:]):
            pair = _is_pair(a, b)
            if pair:
                relation, reason, strength = pair
                links_by_target[b["event_id"]] = Link(
                    a["event_id"], b["event_id"], relation, reason, strength
                )
    out = []
    for ev in events:
        copy = dict(ev)
        link = links_by_target.get(ev.get("event_id"))
        copy["link_to_previous"] = link.to_dict() if link else None
        copy["confidence"] = float(ev.get("confidence") or 0.0)
        out.append(copy)
    return out


def correlation_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    links = build_links(events)
    explicit = sum(1 for l in links if l.relation == Correlation.EXPLICIT.value)
    probable = sum(1 for l in links if l.relation == Correlation.PROBABLE.value)
    orphan = sum(1 for ev in events if not session_key(ev))
    return {
        "events": len(events),
        "links_explicit": explicit,
        "links_probable": probable,
        "links_unknown": max(0, len(events) - 1 - explicit - probable),
        "events_without_session": orphan,
    }
