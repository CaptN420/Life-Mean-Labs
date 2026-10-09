"""SQLite schema for Philosophical Council."""

from __future__ import annotations

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS debates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic          TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'idle',
    total_turns     INTEGER NOT NULL DEFAULT 0,
    current_round   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS turns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id       INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    turn_id         INTEGER NOT NULL,
    round           INTEGER NOT NULL,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    speaker         TEXT NOT NULL,
    speaker_role    TEXT NOT NULL,
    moderator_question   TEXT,
    moderator_reason   TEXT,
    response        TEXT NOT NULL,
    model           TEXT,
    duration_seconds REAL,
    finish_reason   TEXT,
    was_truncated   INTEGER DEFAULT 0,
    continuation_count INTEGER DEFAULT 0,
    FOREIGN KEY (debate_id) REFERENCES debates(id)
);

CREATE INDEX IF NOT EXISTS idx_turns_debate ON turns(debate_id);
CREATE INDEX IF NOT EXISTS idx_turns_debate_round ON turns(debate_id, round);
CREATE INDEX IF NOT EXISTS idx_turns_debate_turn ON turns(debate_id, turn_id);

CREATE TABLE IF NOT EXISTS memory_short (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id   INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    snapshot_at TEXT NOT NULL DEFAULT (datetime('now')),
    context     TEXT NOT NULL,
    turn_range  TEXT,
    FOREIGN KEY (debate_id) REFERENCES debates(id)
);

CREATE TABLE IF NOT EXISTS memory_mid (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id       INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    period          TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    main_arguments  TEXT,
    counter_arguments TEXT,
    agreements      TEXT,
    disagreements   TEXT,
    contradictions  TEXT,
    important_questions TEXT,
    position_changes TEXT,
    unresolved_issues TEXT,
    FOREIGN KEY (debate_id) REFERENCES debates(id)
);

CREATE INDEX IF NOT EXISTS idx_memory_mid_debate ON memory_mid(debate_id);

CREATE TABLE IF NOT EXISTS memory_long (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id       INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    key             TEXT NOT NULL,
    category        TEXT,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(debate_id, key),
    FOREIGN KEY (debate_id) REFERENCES debates(id)
);

CREATE INDEX IF NOT EXISTS idx_memory_long_debate ON memory_long(debate_id);
CREATE INDEX IF NOT EXISTS idx_memory_long_key ON memory_long(debate_id, key);

CREATE TABLE IF NOT EXISTS moderator_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id       INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    turn_id         INTEGER NOT NULL,
    round           INTEGER NOT NULL,
    selected_speaker TEXT NOT NULL,
    challenge       TEXT,
    reason          TEXT,
    question        TEXT,
    detected_issues TEXT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (debate_id) REFERENCES debates(id)
);

CREATE INDEX IF NOT EXISTS idx_moderator_decisions_debate ON moderator_decisions(debate_id);

CREATE TABLE IF NOT EXISTS agents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id       INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    model           TEXT,
    color_hex       TEXT,
    FOREIGN KEY (debate_id) REFERENCES debates(id)
);

CREATE INDEX IF NOT EXISTS idx_agents_debate ON agents(debate_id);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id       INTEGER,
    event_type      TEXT NOT NULL,
    payload         TEXT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_debate ON events(debate_id);
"""


def get_schema_sql() -> str:
    """Return the full schema DDL."""
    return SCHEMA_SQL
