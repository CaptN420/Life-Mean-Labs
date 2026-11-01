"""Stockage local des événements (SQLite, WAL, append-only).

- Base par défaut : ``data/pipeline_inspector.db`` (volume Docker persistant).
- Déduplication par ``event_id`` (clé primaire) : une ré-ingestion n'ajoute
  jamais de doublon.
- État d'ingestion par fichier (taille, mtime, offset) pour reprendre au bon
  endroit sans relire tout l'historique.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .redaction import redact_value
from .schemas import PipelineEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    timestamp       REAL NOT NULL,
    timestamp_iso   TEXT,
    source          TEXT NOT NULL,
    source_file     TEXT NOT NULL,
    source_line     INTEGER NOT NULL,
    session_id      TEXT,
    conversation_id TEXT,
    request_id      TEXT,
    task_id         TEXT,
    model_call_id   TEXT,
    run_id          TEXT,
    agent           TEXT,
    model           TEXT,
    status          TEXT,
    ok              INTEGER,
    duration_ms     REAL,
    correlation     TEXT NOT NULL DEFAULT 'unknown',
    confidence      REAL NOT NULL DEFAULT 0.0,
    raw_event_type  TEXT,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts        ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type      ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_session   ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_agent     ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_model     ON events(model);
CREATE INDEX IF NOT EXISTS idx_events_source    ON events(source);

CREATE TABLE IF NOT EXISTS ingest_state (
    path        TEXT PRIMARY KEY,
    size        INTEGER NOT NULL DEFAULT 0,
    mtime       REAL NOT NULL DEFAULT 0,
    offset      INTEGER NOT NULL DEFAULT 0,
    last_line   INTEGER NOT NULL DEFAULT 0,
    events      INTEGER NOT NULL DEFAULT 0,
    updated_at  REAL NOT NULL DEFAULT 0,
    truncated   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  REAL NOT NULL,
    finished_at REAL,
    stats_json  TEXT NOT NULL DEFAULT '{}'
);
"""


class EventStore:
    """Magasin d'événements thread-safe (connexion par opération)."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    # ── connexion ─────────────────────────────────────────────────────────
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            # Migration douce : les bases créées avant l'ajout de la colonne
            # `truncated` n'en disposent pas. Sans elle, un fichier tronqué par
            # le plafond par-fichier était marqué comme entièrement consommé
            # (size == st_size) et n'était plus JAMAIS relu → perte silencieuse
            # du reste du fichier.
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(ingest_state)")}
            if "truncated" not in cols:
                conn.execute(
                    "ALTER TABLE ingest_state ADD COLUMN truncated INTEGER NOT NULL DEFAULT 0"
                )

    # ── ingestion ─────────────────────────────────────────────────────────
    def get_ingest_state(self, path: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM ingest_state WHERE path = ?", (path,)
            ).fetchone()
        return dict(row) if row else None

    def set_ingest_state(
        self, path: str, size: int, mtime: float, offset: int,
        last_line: int, events: int, updated_at: float, truncated: bool = False,
    ) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO ingest_state(path,size,mtime,offset,last_line,events,updated_at,truncated)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(path) DO UPDATE SET
                     size=excluded.size, mtime=excluded.mtime, offset=excluded.offset,
                     last_line=excluded.last_line, events=excluded.events,
                     updated_at=excluded.updated_at, truncated=excluded.truncated""",
                (path, size, mtime, offset, last_line, events, updated_at, 1 if truncated else 0),
            )

    def insert_events(self, events: Iterable[PipelineEvent]) -> int:
        """Insère en ignorant les doublons. Retourne le nombre réellement ajouté."""
        added = 0
        with self._lock, self._conn() as conn:
            for ev in events:
                try:
                    cur = conn.execute(
                        """INSERT OR IGNORE INTO events (
                            event_id,event_type,timestamp,timestamp_iso,source,source_file,
                            source_line,session_id,conversation_id,request_id,task_id,
                            model_call_id,run_id,agent,model,status,ok,duration_ms,
                            correlation,confidence,raw_event_type,metadata_json
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            ev.event_id, ev.event_type, ev.timestamp, ev.timestamp_iso,
                            ev.source, ev.source_file, ev.source_line, ev.session_id,
                            ev.conversation_id, ev.request_id, ev.task_id,
                            ev.model_call_id, ev.run_id, ev.agent, ev.model, ev.status,
                            None if ev.ok is None else int(ev.ok), ev.duration_ms,
                            ev.correlation, ev.confidence, ev.raw_event_type,
                            json.dumps(redact_value(ev.metadata), default=str),
                        ),
                    )
                    added += 1 if cur.rowcount == 1 else 0
                except sqlite3.Error:
                    continue
        return added

    def begin_ingest_run(self, started_at: float) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO ingest_runs(started_at) VALUES (?)", (started_at,)
            )
            return int(cur.lastrowid)

    def end_ingest_run(self, run_id: int, stats: Dict[str, Any], finished_at: float) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE ingest_runs SET finished_at=?, stats_json=? WHERE id=?",
                (finished_at, json.dumps(stats, default=str), run_id),
            )

    # ── lecture ───────────────────────────────────────────────────────────
    def count_events(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def query(
        self,
        event_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        order: str = "asc",
    ) -> List[Dict[str, Any]]:
        where: List[str] = []
        params: List[Any] = []
        if event_types:
            where.append(f"event_type IN ({','.join('?' * len(event_types))})")
            params.extend(event_types)
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)
        if agent:
            where.append("agent = ?")
            params.append(agent)
        if model:
            where.append("model = ?")
            params.append(model)
        if source:
            where.append("source = ?")
            params.append(source)
        if status:
            where.append("status = ?")
            params.append(status)
        if since is not None:
            where.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            where.append("timestamp <= ?")
            params.append(until)
        if search:
            where.append("(metadata_json LIKE ? OR agent LIKE ? OR model LIKE ?)")
            params.extend([f"%{search}%"] * 3)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        direction = "DESC" if str(order).lower() == "desc" else "ASC"
        sql = (
            "SELECT * FROM events" + clause +
            f" ORDER BY timestamp {direction}, event_id LIMIT ? OFFSET ?"
        )
        params.extend([max(1, min(int(limit), 50000)), max(0, int(offset))])
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            try:
                d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
            except json.JSONDecodeError:
                d["metadata"] = {}
            d["ok"] = None if d.get("ok") is None else bool(d["ok"])
            out.append(d)
        return out

    def sessions(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Sessions = regroupement par session_id observé (jamais inventé)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT session_id,
                          MIN(timestamp) AS started_at,
                          MAX(timestamp) AS ended_at,
                          COUNT(*) AS events,
                          GROUP_CONCAT(DISTINCT source) AS sources,
                          GROUP_CONCAT(DISTINCT agent) AS agents,
                          GROUP_CONCAT(DISTINCT model) AS models,
                          SUM(CASE WHEN event_type='PIPELINE_ERROR' THEN 1 ELSE 0 END) AS errors,
                          SUM(CASE WHEN event_type='SECURITY_DENY' THEN 1 ELSE 0 END) AS denies,
                          SUM(CASE WHEN event_type='TEST_RESULT' AND ok=1 THEN 1 ELSE 0 END) AS tests_passed,
                          SUM(CASE WHEN event_type='TEST_RESULT' AND ok=0 THEN 1 ELSE 0 END) AS tests_failed
                   FROM events
                   WHERE session_id IS NOT NULL AND session_id != ''
                   GROUP BY session_id
                   ORDER BY started_at DESC
                   LIMIT ?""",
                (max(1, min(int(limit), 2000)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def distinct(self, column: str) -> List[str]:
        allowed = {"agent", "model", "source", "event_type", "status"}
        if column not in allowed:
            raise ValueError(f"colonne non autorisée: {column}")
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT {column} FROM events WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}"
            ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            by_type = dict(conn.execute(
                "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
            ).fetchall())
            by_source = dict(conn.execute(
                "SELECT source, COUNT(*) FROM events GROUP BY source"
            ).fetchall())
            sessions = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM events WHERE session_id IS NOT NULL AND session_id != ''"
            ).fetchone()[0]
            first = conn.execute("SELECT MIN(timestamp) FROM events").fetchone()[0]
            last = conn.execute("SELECT MAX(timestamp) FROM events").fetchone()[0]
        return {
            "total_events": total,
            "sessions": sessions,
            "by_type": by_type,
            "by_source": by_source,
            "first_timestamp": first,
            "last_timestamp": last,
        }

    def purge(self) -> None:
        """Vide le store (jamais appelé automatiquement)."""
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM ingest_state")
