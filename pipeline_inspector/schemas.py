"""Pipeline Inspector — schémas canoniques.

Un événement canonique = une ligne de log brute, normalisée, avec son
identifiant stable, sa source, son horodatage et son niveau de corrélation.

Règle : on ne fusionne jamais deux événements et on n'invente jamais une
corrélation. Si un identifiant manque, ``correlation`` vaut ``unknown``.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class EventType(str, Enum):
    """Vocabulaire canonique demandé par la spécification."""

    MODEL_REQUEST = "MODEL_REQUEST"
    MODEL_RESPONSE = "MODEL_RESPONSE"
    MODEL_STREAM_START = "MODEL_STREAM_START"
    MODEL_STREAM_END = "MODEL_STREAM_END"

    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"

    SECURITY_REVIEW = "SECURITY_REVIEW"
    SECURITY_APPROVE = "SECURITY_APPROVE"
    SECURITY_DENY = "SECURITY_DENY"
    SECURITY_ESCALATE = "SECURITY_ESCALATE"

    FILE_READ = "FILE_READ"
    FILE_PATCH = "FILE_PATCH"

    TEST_EXECUTION = "TEST_EXECUTION"
    TEST_RESULT = "TEST_RESULT"

    API_ERROR = "API_ERROR"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    PIPELINE_COMPLETE = "PIPELINE_COMPLETE"

    # Extensions explicites (nécessaires pour représenter le début d'un run et
    # la décision de routage ; documentées dans PIPELINE_ARCHITECTURE.md).
    PIPELINE_START = "PIPELINE_START"
    ROUTING_DECISION = "ROUTING_DECISION"
    AGENT_SELECTED = "AGENT_SELECTED"

    UNKNOWN = "UNKNOWN"


class Correlation(str, Enum):
    """Niveau de confiance de la relation entre événements."""

    EXPLICIT = "explicit"   # identifiant partagé présent dans les deux lignes
    PROBABLE = "probable"   # même session + fenêtre temporelle + type attendu
    UNKNOWN = "unknown"     # aucune preuve


@dataclass
class PipelineEvent:
    """Événement canonique, sérialisable et stable."""

    event_type: str
    source: str
    source_file: str
    source_line: int
    timestamp: float
    timestamp_iso: str = ""

    # Identifiants observés (jamais fabriqués)
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    model_call_id: Optional[str] = None
    run_id: Optional[str] = None

    # Contexte d'exécution
    agent: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    ok: Optional[bool] = None
    duration_ms: Optional[float] = None

    # Traçabilité
    correlation: str = Correlation.UNKNOWN.value
    confidence: float = 0.0
    raw_event_type: Optional[str] = None
    event_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp_iso:
            try:
                self.timestamp_iso = datetime.fromtimestamp(
                    self.timestamp, tz=timezone.utc
                ).isoformat()
            except (OverflowError, OSError, ValueError):
                self.timestamp_iso = ""
        if not self.event_id:
            self.event_id = self.compute_id()

    def compute_id(self) -> str:
        """Identifiant stable : même ligne brute -> même id, à chaque ingest."""
        seed = "|".join(
            [
                str(self.source),
                str(self.source_file),
                str(self.source_line),
                str(self.raw_event_type or self.event_type),
                str(self.timestamp),
                str(self.metadata.get("raw_id") or ""),
            ]
        )
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "timestamp": self.timestamp,
            "timestamp_iso": self.timestamp_iso,
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "model_call_id": self.model_call_id,
            "run_id": self.run_id,
            "agent": self.agent,
            "model": self.model,
            "status": self.status,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "correlation": self.correlation,
            "confidence": self.confidence,
            "raw_event_type": self.raw_event_type,
            "metadata": self.metadata,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PipelineEvent":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


def parse_timestamp(value: Any) -> Optional[float]:
    """Convertit epoch (s/ms) ou ISO-8601 en epoch secondes. None si illisible."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e11 else v
    text = str(value).strip()
    if not text:
        return None
    # epoch numérique sous forme de chaîne
    try:
        v = float(text)
        return v / 1000.0 if v > 1e11 else v
    except ValueError:
        pass
    iso = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def stable_event_id(source: str, relpath: str, line_no: int, raw: Any = None) -> str:
    """Hash stable partagé par les adapters."""
    blob = json.dumps(raw, sort_keys=True, default=str) if raw is not None else ""
    seed = f"{source}|{relpath}|{line_no}|{blob}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def utcnow() -> float:
    return time.time()
