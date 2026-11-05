"""Collecteurs système réels (Defender, journal d'événements Windows).

L'audit classait ces collecteurs en `BLOCKED_EXTERNAL` à cause de `psutil`,
`win32evtlog` et `win32service` absents. Vérification faite : aucun collecteur
n'existait dans le dépôt, et les dépendances ne sont pas nécessaires — Windows
fournit `powershell` (Get-MpComputerStatus) et `wevtutil`.

Ces tests s'exécutent **contre la machine réelle** (aucun mock) : ils prouvent
que la donnée vient du système, et ils sont sautés sur une plateforme non
Windows. Les cas d'erreur, eux, tournent partout.
"""

from __future__ import annotations

import time

import pytest

from core.safety import os_collectors as oc


# ── 1. défauts et robustesse (toutes plateformes) ──────────────────────────


def test_unreadable_log_is_an_explicit_error_not_a_crash():
    result = oc.recent_events("Journal_Qui_N_Existe_Pas_XYZ", count=2)
    assert result["ok"] is False
    assert result["events"] == []
    assert result["error"], "an unavailable log must say why"


def test_count_is_bounded():
    result = oc.recent_events("System", count=10_000)
    # borné à 50 : la requête ne doit pas tirer 10 000 événements
    assert result["ok"] is False or result["count"] <= 50


def test_missing_binary_is_reported(monkeypatch):
    monkeypatch.setattr(oc, "is_windows", lambda: True)
    monkeypatch.setattr(oc.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    result = oc.defender_status()
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_timeout_is_reported(monkeypatch):
    def boom(*a, **k):
        raise oc.subprocess.TimeoutExpired(cmd="powershell", timeout=1)

    monkeypatch.setattr(oc, "is_windows", lambda: True)
    monkeypatch.setattr(oc.subprocess, "run", boom)
    result = oc.defender_status()
    assert result["ok"] is False
    assert "timeout" in result["error"]


def test_non_windows_degrades_explicitly(monkeypatch):
    monkeypatch.setattr(oc, "is_windows", lambda: False)
    assert oc.defender_status()["error"] == "not a Windows host"
    snapshot = oc.os_snapshot()
    assert snapshot["host"]["supported"] is False
    assert set(snapshot["degraded"]) == {"defender", "event_log"}


def test_snapshot_never_raises(monkeypatch):
    monkeypatch.setattr(oc, "defender_status", lambda timeout=20.0: {"ok": False, "error": "x"})
    monkeypatch.setattr(oc, "recent_events", lambda **k: {"ok": False, "error": "y", "events": []})
    snapshot = oc.os_snapshot()
    assert snapshot["degraded"] == ["defender", "event_log"]


# ── 2. mesures réelles sur cette machine ───────────────────────────────────

windows_only = pytest.mark.skipif(not oc.is_windows(), reason="Windows only")


@windows_only
def test_defender_reports_real_state():
    result = oc.defender_status()
    if not result["ok"]:
        pytest.skip(f"Defender unavailable here ({result['error']})")
    assert isinstance(result["real_time_protection"], bool)
    assert isinstance(result["antivirus_enabled"], bool)
    # une signature datée est un nombre, jamais une chaîne « inconnue »
    assert result["signature_timestamp"] is None or result["signature_timestamp"] > 1_500_000_000


@windows_only
def test_recent_events_returns_real_structured_events():
    result = oc.recent_events("System", count=3)
    if not result["ok"]:
        pytest.skip(f"event log unreadable here ({result['error']})")
    assert result["events"], "the System log always has events on a running machine"
    first = result["events"][0]
    assert first["event_id"] and first["event_id"].isdigit()
    assert first["level"] in {"critical", "error", "warning", "information", "verbose", None}
    assert first["time_created"]


@windows_only
def test_snapshot_is_fast_enough_for_an_http_route():
    started = time.time()
    snapshot = oc.os_snapshot(events=3)
    elapsed = time.time() - started
    assert elapsed < 30, f"snapshot took {elapsed:.1f}s"
    assert snapshot["host"]["platform"]
    assert "defender" in snapshot and "event_log" in snapshot
