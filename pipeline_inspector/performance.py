"""Mesures de performance — uniquement ce qui est réellement mesuré.

Distinction explicite :
- métriques *modèle* : tokens, latence d'un appel, tokens/s ;
- métriques *pipeline* : durée d'une session, durée entre deux étapes,
  taux d'échec des runs.

Une valeur absente reste absente (``None``), jamais estimée.
"""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional

from .correlation import group_sessions
from .schemas import EventType


def _num(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def model_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Agrégats par modèle, à partir des MODEL_RESPONSE."""
    per_model: Dict[str, Dict[str, Any]] = {}
    for ev in events:
        if ev.get("event_type") != EventType.MODEL_RESPONSE.value:
            continue
        model = ev.get("model") or "unknown"
        meta = ev.get("metadata") or {}
        bucket = per_model.setdefault(model, {
            "calls": 0, "ok": 0, "failed": 0,
            "tokens_input": 0, "tokens_output": 0,
            "latency_ms_total": 0.0, "latency_samples": 0,
            "tokens_in_measured": 0, "tokens_out_measured": 0,
        })
        bucket["calls"] += 1
        if ev.get("ok") is True:
            bucket["ok"] += 1
        elif ev.get("ok") is False:
            bucket["failed"] += 1
        tin = _num(meta.get("tokens_input"))
        tout = _num(meta.get("tokens_output"))
        lat = _num(meta.get("latency_ms")) or _num(ev.get("duration_ms"))
        if tin is not None:
            bucket["tokens_input"] += int(tin)
            bucket["tokens_in_measured"] += 1
        if tout is not None:
            bucket["tokens_output"] += int(tout)
            bucket["tokens_out_measured"] += 1
        if lat is not None:
            bucket["latency_ms_total"] += lat
            bucket["latency_samples"] += 1

    for model, b in per_model.items():
        if b["latency_samples"]:
            b["latency_ms_avg"] = round(b["latency_ms_total"] / b["latency_samples"], 1)
            if b["tokens_out_measured"] and b["latency_ms_total"] > 0:
                b["tokens_per_second"] = round(
                    b["tokens_output"] / (b["latency_ms_total"] / 1000.0), 2
                )
        b["latency_ms_total"] = round(b["latency_ms_total"], 1)
    return per_model


def pipeline_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Durées de session, taux d'échec, tentatives."""
    sessions = group_sessions(events)
    durations: List[float] = []
    failed_sessions = 0
    completed_sessions = 0
    retries = 0
    for _key, group in sessions.items():
        if len(group) < 2:
            continue
        span = float(group[-1].get("timestamp") or 0) - float(group[0].get("timestamp") or 0)
        if span >= 0:
            durations.append(span)
        types = {e.get("event_type") for e in group}
        if EventType.PIPELINE_ERROR.value in types:
            failed_sessions += 1
        if EventType.PIPELINE_COMPLETE.value in types:
            completed_sessions += 1
        for e in group:
            if str(e.get("status") or "").lower() in {"retry", "retried"}:
                retries += 1

    total = len(sessions)
    return {
        "sessions": total,
        "sessions_with_span": len(durations),
        "session_duration_s_avg": round(mean(durations), 2) if durations else None,
        "session_duration_s_min": round(min(durations), 2) if durations else None,
        "session_duration_s_max": round(max(durations), 2) if durations else None,
        "sessions_failed": failed_sessions,
        "sessions_completed": completed_sessions,
        "failure_rate": round(failed_sessions / total, 3) if total else None,
        "retries_observed": retries,
        "note": "Les sessions sans identifiant partagé ne sont pas comptées.",
    }
