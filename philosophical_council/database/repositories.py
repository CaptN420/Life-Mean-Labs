"""Database connection and repository layer."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@contextmanager
def connect(db_path: str):
    """Context manager yielding a sqlite3 connection with sane defaults."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class DebateRepository:
    """CRUD for the debates table."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def create_debate(self, topic: str) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO debates (topic, status, total_turns, current_round) VALUES (?, 'idle', 0, 0)",
                (topic,),
            )
            return int(cur.lastrowid)

    def get_debate(self, debate_id: int) -> Optional[dict[str, Any]]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM debates WHERE id = ?", (debate_id,)).fetchone()
            return dict(row) if row else None

    def update_status(self, debate_id: int, status: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE debates SET status = ?, current_round = current_round WHERE id = ?",
                (status, debate_id),
            )

    def increment_turns(self, debate_id: int, round_num: int) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE debates SET total_turns = total_turns + 1, current_round = ? WHERE id = ?",
                (round_num, debate_id),
            )

    def finish_debate(self, debate_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE debates SET status = 'finished', finished_at = ? WHERE id = ?",
                (now, debate_id),
            )

    def insert_agent(self, debate_id: int, role: str, name: str, system_prompt: str,
                     model: str, color: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO agents (debate_id, role, name, description, model, color_hex)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (debate_id, role, name, system_prompt, model, color),
            )


class TurnRepository:
    """CRUD for the turns table."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def insert_turn(
        self,
        debate_id: int,
        turn_id: int,
        round_num: int,
        speaker: str,
        speaker_role: str,
        response: str,
        moderator_question: Optional[str] = None,
        moderator_reason: Optional[str] = None,
        model: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        finish_reason: Optional[str] = None,
        was_truncated: bool = False,
        continuation_count: int = 0,
    ) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO turns (debate_id, turn_id, round, speaker, speaker_role,
                                   moderator_question, moderator_reason, response, model, duration_seconds,
                                   finish_reason, was_truncated, continuation_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    debate_id,
                    turn_id,
                    round_num,
                    speaker,
                    speaker_role,
                    moderator_question,
                    moderator_reason,
                    response,
                    model,
                    duration_seconds,
                    finish_reason,
                    1 if was_truncated else 0,
                    continuation_count,
                ),
            )
            return int(cur.lastrowid)

    def get_turns(self, debate_id: int, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM turns WHERE debate_id = ? ORDER BY turn_id ASC LIMIT ? OFFSET ?",
                (debate_id, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_total_turns(self, debate_id: int) -> int:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM turns WHERE debate_id = ?", (debate_id,)
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def search_turns(self, debate_id: int, query: str, limit: int = 50) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT * FROM turns
                   WHERE debate_id = ? AND (response LIKE ? OR moderator_question LIKE ? OR speaker LIKE ?)
                   ORDER BY turn_id ASC LIMIT ?""",
                (debate_id, pattern, pattern, pattern, limit),
            ).fetchall()
            return [dict(r) for r in rows]


class MemoryRepository:
    """CRUD for memory tables."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    # -- short-term --
    def save_short(self, debate_id: int, context: str, turn_range: Optional[str] = None) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO memory_short (debate_id, context, turn_range) VALUES (?, ?, ?)",
                (debate_id, context, turn_range),
            )

    def get_recent_short(self, debate_id: int, limit: int = 5) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_short WHERE debate_id = ? ORDER BY id DESC LIMIT ?",
                (debate_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # -- mid-term --
    def save_mid(self, debate_id: int, period: str, data: dict[str, Any]) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO memory_mid (debate_id, period, main_arguments, counter_arguments,
                                           agreements, disagreements, contradictions,
                                           important_questions, position_changes, unresolved_issues)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    debate_id,
                    period,
                    json.dumps(data.get("main_arguments", [])),
                    json.dumps(data.get("counter_arguments", [])),
                    json.dumps(data.get("agreements", [])),
                    json.dumps(data.get("disagreements", [])),
                    json.dumps(data.get("contradictions", [])),
                    json.dumps(data.get("important_questions", [])),
                    json.dumps(data.get("position_changes", [])),
                    json.dumps(data.get("unresolved_issues", [])),
                ),
            )

    def get_mid(self, debate_id: int) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_mid WHERE debate_id = ? ORDER BY id DESC", (debate_id,)
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                for key in ("main_arguments", "counter_arguments", "agreements", "disagreements",
                            "contradictions", "important_questions", "position_changes", "unresolved_issues"):
                    raw = d.get(key)
                    if raw:
                        try:
                            d[key] = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            pass
                out.append(d)
            return out

    # -- long-term --
    def save_long(self, debate_id: int, key: str, category: Optional[str], content: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO memory_long (debate_id, key, category, content)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(debate_id, key) DO UPDATE SET content = excluded.content, updated_at = datetime('now')""",
                (debate_id, key, category, content),
            )

    def get_long(self, debate_id: int) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_long WHERE debate_id = ? ORDER BY updated_at DESC", (debate_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_long_by_category(self, debate_id: int, category: str) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_long WHERE debate_id = ? AND category = ? ORDER BY updated_at DESC",
                (debate_id, category),
            ).fetchall()
            return [dict(r) for r in rows]


class ModeratorDecisionRepository:
    """Store moderator decisions."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def insert(self, debate_id: int, turn_id: int, round_num: int,
               selected_speaker: str, challenge: Optional[str], reason: Optional[str],
               question: Optional[str], detected_issues: Optional[str]) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO moderator_decisions (debate_id, turn_id, round, selected_speaker,
                                                    challenge, reason, question, detected_issues)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (debate_id, turn_id, round_num, selected_speaker, challenge, reason, question, detected_issues),
            )

    def get_recent(self, debate_id: int, limit: int = 20) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM moderator_decisions WHERE debate_id = ? ORDER BY id DESC LIMIT ?",
                (debate_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]


class EventRepository:
    """Store lifecycle events."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def insert(self, event_type: str, payload: Optional[dict[str, Any]] = None, debate_id: Optional[int] = None) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO events (debate_id, event_type, payload) VALUES (?, ?, ?)",
                (debate_id, event_type, json.dumps(payload) if payload else None),
            )

    def get_recent(self, debate_id: Optional[int] = None, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            if debate_id is not None:
                rows = conn.execute(
                    "SELECT * FROM events WHERE debate_id = ? ORDER BY id DESC LIMIT ?",
                    (debate_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
