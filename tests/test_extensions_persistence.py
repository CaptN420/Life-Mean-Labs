"""Self-extension registries (P5): discovery vs activation, and real persistence.

Two problems were reported as a bare ``total: 0``:

1. the tool registry was empty while 60 deterministic tools exist in
   ``library/tools`` and are used by ToolWorker every run;
2. the registries were memory-only, so ``POST /api/extensions/tools`` answered
   ``status: "proposed"`` and everything disappeared on restart.

The contract pinned here: discovery is reported separately from activation, and
a mutation that cannot be stored is reported as a failure, never as success.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from life_mean_extensions.api import ExtensionsApiMixin
from life_mean_extensions.pipeline import create_extension_layer
from life_mean_extensions.store import SCHEMA, ExtensionStore


class _Handler(ExtensionsApiMixin):
    def __init__(self):
        self.extension_layer = None
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
def ext_dir(tmp_path, monkeypatch):
    directory = tmp_path / "extensions"
    monkeypatch.setenv("LIFE_MEAN_EXTENSIONS_DIR", str(directory))
    # generated tool stubs must not land in the repository's sandbox/
    monkeypatch.setenv("LIFE_MEAN_SANDBOX_DIR", str(tmp_path / "sandbox_tools"))
    return directory


# ── 1. découverte ≠ activation ──────────────────────────────────────────────


def test_tool_list_shows_the_real_catalog_separately(ext_dir):
    handler = _Handler()
    handler._extensions_tools_list()

    assert handler.code == 200
    payload = handler.json

    # the registry itself is genuinely empty: nothing was proposed/approved
    assert payload["stats"]["total"] == 0
    assert payload["all"] == []

    # ...but the tools that actually exist are visible
    assert payload["catalog_total"] >= 50, payload["catalog_total"]
    names = {t["name"] for t in payload["catalog"]}
    assert "chemistry_molar_mass" in names
    assert all(t["in_registry"] is False for t in payload["catalog"])
    assert "découvrir n'est pas activer" in payload["note"]


def test_skills_list_states_where_it_looked(ext_dir):
    handler = _Handler()
    handler._extensions_skills_list()

    payload = handler.json
    assert payload["stats"]["total"] == 0
    assert payload["sources_checked"], "the empty answer must say what was checked"
    assert "le total 0 est réel" in payload["note"]


# ── 2. persistance réelle ──────────────────────────────────────────────────


def test_proposed_tool_survives_a_new_layer(ext_dir):
    handler = _Handler()
    handler._extensions_tool_create({
        "description": "Compute the volume of a sphere",
        "input_schema": {"radius": "float"},
    })

    assert handler.code == 200, handler.error
    assert handler.json["persisted"] is True
    tool_id = handler.json["tool_id"]

    stored = json.loads((ext_dir / "registries.json").read_text(encoding="utf-8"))
    assert stored["schema"] == SCHEMA
    assert [t["id"] for t in stored["tools"]] == [tool_id]

    # a fresh layer (i.e. after a restart) sees it again
    layer = create_extension_layer()
    assert layer["restored"]["tools"] == 1
    assert layer["tool_registry"].get(tool_id) is not None

    listing = _Handler()
    listing._extensions_tools_list()
    assert [t["id"] for t in listing.json["all"]] == [tool_id]


def test_approval_is_durable(ext_dir):
    created = _Handler()
    created._extensions_tool_create({"description": "Area of a triangle"})
    tool_id = created.json["tool_id"]

    approved = _Handler()
    approved._extensions_tool_approve(tool_id, {"by": "human", "note": "ok"})
    assert approved.code == 200, approved.error
    assert approved.json["persisted"] is True

    layer = create_extension_layer()
    tool = layer["tool_registry"].get(tool_id)
    assert tool is not None and tool.status.value == "approved"
    assert tool.approved_by == "human"


def test_two_distinct_proposals_do_not_collide(ext_dir):
    """Hand-made proposals used to share one id and overwrite each other."""
    first = _Handler()
    first._extensions_tool_create({"description": "Volume of a sphere"})
    second = _Handler()
    second._extensions_tool_create({"description": "Area of a triangle"})

    assert first.json["tool_id"] != second.json["tool_id"]

    listing = _Handler()
    listing._extensions_tools_list()
    assert len(listing.json["all"]) == 2


def test_previous_state_is_kept_as_a_backup(ext_dir):
    first = _Handler()
    first._extensions_tool_create({"description": "One"})
    second = _Handler()
    second._extensions_tool_create({"description": "Two"})

    backups = list(ext_dir.glob("registries.json.bak"))
    assert backups, "the previous file must be kept, not overwritten in place"
    assert "One" in backups[0].read_text(encoding="utf-8")


# ── 3. un échec d'écriture ne devient pas un succès ────────────────────────


def test_unwritable_store_is_reported_as_a_failure(tmp_path, monkeypatch):
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("LIFE_MEAN_EXTENSIONS_DIR", str(blocker / "extensions"))
    monkeypatch.setenv("LIFE_MEAN_SANDBOX_DIR", str(tmp_path / "sandbox_tools"))

    handler = _Handler()
    handler._extensions_tool_create({"description": "Cannot be stored"})

    assert handler.code == 500
    assert handler.error_code == "persistence_failed"
    assert "NOT persisted" in handler.error
    assert "restart" in handler.error


def test_unwritable_sandbox_returns_an_error_not_a_dropped_connection(tmp_path, monkeypatch):
    """The read-only image made every proposal raise EROFS out of the handler."""
    blocker = tmp_path / "ro"
    blocker.write_text("file, not a directory", encoding="utf-8")
    monkeypatch.setenv("LIFE_MEAN_SANDBOX_DIR", str(blocker / "tools"))
    monkeypatch.setenv("LIFE_MEAN_EXTENSIONS_DIR", str(tmp_path / "extensions"))

    handler = _Handler()
    handler._extensions_tool_create({"description": "Sandbox cannot be created"})

    assert handler.code == 500
    assert handler.error_code == "proposal_failed"
    assert "Sandbox cannot be created" not in (handler.error or "")  # no fake success payload
    assert handler.json is None


# ── 4. fichier abîmé ───────────────────────────────────────────────────────


def test_corrupt_store_is_reported_and_does_not_crash(ext_dir):
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / "registries.json").write_text("{not json", encoding="utf-8")

    layer = create_extension_layer()
    assert layer["restored"] == {"skills": 0, "tools": 0}
    assert layer["store"].last_error, "an unreadable store must say why it is empty"

    handler = _Handler()
    handler._extensions_tools_list()
    assert handler.code == 200
    assert handler.json["storage"]["last_error"]


def test_unknown_schema_is_refused(ext_dir):
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / "registries.json").write_text(
        json.dumps({"schema": "something/9", "tools": [{"id": "x"}]}), encoding="utf-8"
    )
    store = ExtensionStore(ext_dir)
    assert store.load() == {}
    assert "unknown schema" in store.last_error


# ── 5. routage des actions (approve / activate / disable) ───────────────────


def test_action_paths_are_matched_by_the_extension_router():
    """The old regex matched only /tools/<id>, so /approve fell through to 404."""
    assert ExtensionsApiMixin.match_extension_id("/api/extensions/tools/abc") == ("tools", "abc")
    assert ExtensionsApiMixin.match_extension_id("/api/extensions/tools/abc/approve") == ("tools", "abc")
    assert ExtensionsApiMixin.match_extension_id("/api/extensions/skills/s1/activate") == ("skills", "s1")
    assert ExtensionsApiMixin.match_extension_id("/api/extensions/skills/s1/disable") == ("skills", "s1")
    # unrelated paths still do not match
    assert ExtensionsApiMixin.match_extension_id("/api/extensions/tools/abc/unknown") is None
    assert ExtensionsApiMixin.match_extension_id("/api/packages") is None
