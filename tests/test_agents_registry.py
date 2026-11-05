"""Agent registry API — the endpoints that used to lie.

Two behaviours are pinned here because they were both fake:

1. ``GET /api/agents`` returned four hardcoded templates while imported agents
   sat in SQLite, invisible to the UI.
2. ``POST /api/agents`` minted a random id, answered ``status: "created"`` and
   persisted nothing — the UI then alerted "Agent created".

Now every answer is read back from the database before it is sent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from experiments.dashboard import DashboardHandler
from experiments.packages_api import (
    PackagesApiMixin,
    reset_studio_storage,
    studio_db_path,
)

REPO = Path(__file__).resolve().parents[1]
SHIPPED = sorted((REPO / "lmpack").glob("*.lmpack"))


class _Handler:
    """Handler surface without a socket: just the three agent endpoints."""

    _agents_list = DashboardHandler._agents_list
    _agents_create = DashboardHandler._agents_create
    _agents_toggle = DashboardHandler._agents_toggle
    _packages_import = PackagesApiMixin._packages_import
    _storage = PackagesApiMixin._storage

    def __init__(self):
        self.code = None
        self.json = None
        self.error = None
        self.error_code = None

    def _send_json(self, data):
        self.code = 200
        self.json = data

    def _send_error(self, status, message, code="error", request_id=None):
        self.code = status
        self.error = message
        self.error_code = code


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolated registry; the developer's real database is never touched."""
    path = tmp_path / "studio.db"
    monkeypatch.setenv("LIFE_MEAN_STUDIO_DB", str(path))
    reset_studio_storage()
    yield path
    reset_studio_storage()


def _count(db: Path) -> int:
    """Agents on disk, or 0 when the database was never created."""
    if not db.exists():
        return 0
    with sqlite3.connect(str(db)) as conn:
        try:
            return conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        except sqlite3.OperationalError:  # table absent = nothing stored
            return 0


# ── lecture ─────────────────────────────────────────────────────────────────


def test_empty_registry_is_reported_as_empty_not_as_templates(db):
    handler = _Handler()
    handler._agents_list()

    assert handler.code == 200
    payload = handler.json
    assert payload["source"] == "studio_registry"
    assert payload["total"] == 0
    assert payload["agents"] == []
    assert payload["database"].endswith("studio.db")


def test_imported_agents_are_visible_in_the_registry(db):
    importer = _Handler()
    importer._packages_import({"path": SHIPPED[0].name})
    assert importer.json["success"] is True

    handler = _Handler()
    handler._agents_list()
    payload = handler.json

    assert payload["total"] == 11
    assert payload["enabled_count"] == 11
    names = [a["name"] for a in payload["agents"]]
    assert "PARACELSUS" in names
    assert sum(payload["personas"].values()) == 11
    # legacy field kept so the existing Agent Builder UI still renders
    assert all("type" in a and a["type"] == a["persona"] for a in payload["agents"])
    assert all(a["prompt_chars"] > 0 for a in payload["agents"])
    # The pack's 'role' used to be dropped, leaving 11 identical "general" cards.
    roles = {a["name"]: a["description"] for a in payload["agents"]}
    assert roles["PARACELSUS"] == "Transformation"
    assert roles["AGRIPPA"] == "Correspondances"


# ── écriture ────────────────────────────────────────────────────────────────


def test_create_persists_and_reads_back(db):
    handler = _Handler()
    handler._agents_create({
        "name": "VERIFIER",
        "system_prompt": "Refuse any claim you cannot reproduce.",
        "persona": "verification",
        "provider": "lm-studio",
    })

    assert handler.code == 200
    payload = handler.json
    assert payload["persisted"] is True and payload["verified"] is True
    assert payload["name"] == "VERIFIER"
    assert _count(db) == 1

    listing = _Handler()
    listing._agents_list()
    assert [a["name"] for a in listing.json["agents"]] == ["VERIFIER"]


def test_create_never_fakes_success_on_a_duplicate_name(db):
    first = _Handler()
    first._agents_create({"name": "VERIFIER", "system_prompt": "x"})
    assert first.code == 200

    second = _Handler()
    second._agents_create({"name": "verifier", "system_prompt": "y"})
    assert second.code == 409
    assert second.error_code == "agent_exists"
    assert _count(db) == 1


def test_create_requires_a_prompt(db):
    handler = _Handler()
    handler._agents_create({"name": "EMPTY"})
    assert handler.code == 400
    assert handler.error_code == "invalid"
    assert _count(db) == 0


# ── activation ──────────────────────────────────────────────────────────────


def test_toggle_disables_and_verifies_from_storage(db):
    created = _Handler()
    created._agents_create({"name": "VERIFIER", "system_prompt": "x"})
    agent_id = created.json["id"]

    handler = _Handler()
    handler._agents_toggle(agent_id, {"enabled": False})

    assert handler.code == 200
    assert handler.json["enabled"] is False
    assert handler.json["verified"] is True

    with sqlite3.connect(str(db)) as conn:
        enabled = conn.execute("SELECT enabled FROM agents WHERE id = ?", (agent_id,)).fetchone()[0]
    assert enabled == 0


def test_toggle_rejects_unknown_agent_and_bad_payload(db):
    created = _Handler()
    created._agents_create({"name": "VERIFIER", "system_prompt": "x"})
    agent_id = created.json["id"]

    missing = _Handler()
    missing._agents_toggle("does-not-exist", {"enabled": False})
    assert missing.code == 404
    assert missing.error_code == "agent_not_found"

    bad = _Handler()
    bad._agents_toggle(agent_id, {"enabled": "no"})
    assert bad.code == 400
    assert bad.error_code == "invalid"


def test_database_path_is_reported(db):
    assert studio_db_path() == db.resolve()
