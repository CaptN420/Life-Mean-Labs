"""Packages API — the catalogue, inspection and double validation, at handler level.

Before this API the readers worked but no user could reach them: `/api/packages`
returned 404 and the dashboard had no notion of a package. These tests pin the
new surface, and pin the rule that kept the audit honest: opening a ZIP is not
validation, and two readers must be reported separately.
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from experiments.packages_api import (
    PackagePathError,
    PackagesApiMixin,
    inspect_package,
    packages_root,
    resolve_package,
)

REPO = Path(__file__).resolve().parents[1]
SHIPPED = sorted((REPO / "lmpack").glob("*.lmpack"))


class _FakeHandler(PackagesApiMixin):
    def __init__(self):
        self._json = None
        self._code = None
        self._err = None
        self._err_code = None

    def _send_json(self, data):
        self._code = 200
        self._json = data

    def _send_error(self, status, message, code="error", request_id=None):
        self._code = status
        self._err = message
        self._err_code = code


def _fixture_pack(tmp_path: Path, name: str = "FIXTURE", agents: int = 2) -> Path:
    """Independent regression fixture — never rely on the shipped packs alone."""
    path = tmp_path / "fixture.lmpack"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "name": name, "version": "0.0.1", "format_version": "1.0",
            "agents": [f"a{i}" for i in range(agents)], "workflows": [], "experimental": True,
        }))
        for i in range(agents):
            zf.writestr(f"agents/a{i}.json", json.dumps({
                "id": f"a{i}", "name": f"AGENT {i}", "persona": "general",
                "role": f"role {i}", "provider": "lm-studio",
                "system_prompt": f"You are agent {i}. Refuse to invent results.",
            }))
        zf.writestr("README.txt", "fixture pack")
    return path


# ── catalogue ───────────────────────────────────────────────────────────────


def test_list_reports_the_shipped_packs_as_valid():
    handler = _FakeHandler()
    handler._packages_list()
    payload = handler._json

    assert payload["exists"] is True
    assert payload["total"] >= 2
    assert payload["valid_count"] == payload["total"], payload

    for entry in payload["packages"]:
        assert entry["readable"] is True      # the ZIP opens
        assert entry["valid"] is True         # ...and a reader accepts it
        assert entry["agents_count"] == 11
        assert entry["errors"] == []


def test_list_does_not_confuse_readable_with_valid(tmp_path, monkeypatch):
    """A ZIP that opens but carries no agents must not be reported as valid."""
    bad = tmp_path / "emptyish.lmpack"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"name": "EMPTY"}))
        zf.writestr("notes.txt", "nothing here")

    monkeypatch.setenv("LIFE_MEAN_PACKAGES_DIR", str(tmp_path))
    handler = _FakeHandler()
    handler._packages_list()

    entry = next(p for p in handler._json["packages"] if p["file"] == "emptyish.lmpack")
    assert entry["readable"] is True
    assert entry["valid"] is False
    assert handler._json["valid_count"] == 0


# ── inspection ─────────────────────────────────────────────────────────────


def test_inspect_returns_agents_with_redacted_previews():
    path = resolve_package(SHIPPED[0].name)
    detail = inspect_package(path)

    assert detail["agents_count"] == 11
    assert all(a.get("id") for a in detail["agents"])
    assert all(a["prompt_chars"] > 0 for a in detail["agents"])
    assert all(len(a["prompt_preview"]) <= 200 for a in detail["agents"])
    assert detail["verdicts"]["studio"]["ok"] is True
    assert detail["valid"] is True


def test_inspect_keeps_both_verdicts_separate():
    detail = inspect_package(resolve_package(SHIPPED[0].name))
    assert set(detail["verdicts"]) == {"studio", "core"}
    # both agree today, and the payload says so two ways, not one merged boolean
    assert detail["verdicts"]["studio"]["ok"] is True
    assert detail["verdicts"]["core"]["ok"] is True


def test_inspect_reads_readme_txt_of_studio_packs():
    detail = inspect_package(resolve_package(SHIPPED[0].name))
    assert detail["readme_preview"].strip()


# ── confinement des chemins ────────────────────────────────────────────────


@pytest.mark.parametrize("bad", [
    "../requirements.txt",
    "../../.env",
    "C:/Windows/win.ini",
    "/etc/passwd",
    "subdir/../../outside.lmpack",
    "",
])
def test_path_escaping_is_refused(bad):
    with pytest.raises(PackagePathError):
        resolve_package(bad)


def test_unknown_package_is_a_404_not_an_empty_payload():
    handler = _FakeHandler()
    handler._packages_inspect("does_not_exist.lmpack")
    assert handler._code == 404
    assert handler._err_code == "package_not_found"


# ── validation à la demande ────────────────────────────────────────────────


def test_validate_endpoint_agrees_and_reports_agreement():
    handler = _FakeHandler()
    handler._packages_validate({"path": SHIPPED[0].name})
    assert handler._code == 200
    payload = handler._json
    assert payload["valid"] is True
    assert payload["agreement"] is True
    assert payload["verdicts"]["core"]["persona_count"] == 11


def test_validate_rejects_traversal_with_404():
    handler = _FakeHandler()
    handler._packages_validate({"path": "../../.env"})
    assert handler._code == 404
    assert handler._err_code == "package_not_found"


def test_fixture_pack_is_validated_independently_of_shipped_ones(tmp_path, monkeypatch):
    _fixture_pack(tmp_path)
    monkeypatch.setenv("LIFE_MEAN_PACKAGES_DIR", str(tmp_path))

    handler = _FakeHandler()
    handler._packages_validate({"path": "fixture.lmpack"})
    payload = handler._json
    assert payload["valid"] is True
    assert payload["verdicts"]["studio"]["agents_count"] == 2
    assert payload["verdicts"]["core"]["persona_count"] == 2
    assert packages_root() == tmp_path.resolve()


# ── import dans le registre Studio ─────────────────────────────────────────


@pytest.fixture
def studio_db(tmp_path, monkeypatch):
    """Isolated Studio registry — never the developer's real database."""
    db = tmp_path / "studio.db"
    monkeypatch.setenv("LIFE_MEAN_STUDIO_DB", str(db))
    PackagesApiMixin._studio_storage = None
    yield db
    PackagesApiMixin._studio_storage = None


def _agent_count(db: Path) -> int:
    import sqlite3

    with sqlite3.connect(str(db)) as conn:
        return conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]


def test_import_creates_agents_and_reports_the_database(studio_db):
    handler = _FakeHandler()
    handler._packages_import({"path": SHIPPED[0].name})

    assert handler._code == 200
    payload = handler._json
    assert payload["success"] is True
    assert payload["agents_imported"] == 11
    assert payload["conflicts"] == []
    assert payload["database"].endswith("studio.db")
    assert _agent_count(studio_db) == 11


def test_second_import_is_refused_and_creates_no_duplicate(studio_db):
    """The bug this pins: create_agent() mints a UUID, so the old id-based
    conflict check never matched and re-importing doubled the registry."""
    handler = _FakeHandler()
    handler._packages_import({"path": SHIPPED[0].name})
    handler._packages_import({"path": SHIPPED[0].name})

    payload = handler._json
    assert payload["success"] is False
    assert payload["agents_imported"] == 0
    assert len(payload["conflicts"]) == 11
    assert "already present" in payload["message"]
    assert _agent_count(studio_db) == 11


def test_import_refuses_paths_outside_the_packages_root(studio_db):
    handler = _FakeHandler()
    handler._packages_import({"path": "../../.env"})
    assert handler._code == 404
    assert handler._err_code == "package_not_found"
    assert not studio_db.exists() or _agent_count(studio_db) == 0
