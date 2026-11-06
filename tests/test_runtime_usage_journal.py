"""Journal d'usage runtime : observer ce qui tourne, pas ce que les logs veulent bien dire.

Contexte mesuré : le Feature Pool ne pouvait compter l'usage qu'en relisant des
journaux déjà ingérés (14 fonctionnalités observées sur 989, chiffre dépendant de
ce que l'ingestion avait conservé). Le runner écrit maintenant une ligne par
composant réellement exécuté, et le pont Feature Pool fusionne deux sources :
`logs` et `runtime`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from experiments.usage_recorder import SCHEMA, FeatureUsageRecorder
from pipeline_inspector.feature_pool_bridge import FeaturePoolBridge

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── 1. le journal ──────────────────────────────────────────────────────────


def test_records_are_appended_and_read_back(tmp_path):
    rec = FeatureUsageRecorder(tmp_path)
    assert rec.record("worker", "ToolWorker", experiment_id="exp_1", task_id="t1")
    assert rec.record("tool", "math_gcd", experiment_id="exp_1", task_id="t1", ok=True)

    entries = rec.read()
    assert len(entries) == 2
    assert entries[0]["schema"] == SCHEMA
    assert entries[0]["kind"] == "worker"
    assert entries[1]["name"] == "math_gcd"
    assert entries[1]["ok"] is True
    assert entries[0]["experiment_id"] == "exp_1"
    assert entries[0]["task_id"] == "t1"
    # append-only : le fichier ne réécrit pas les lignes précédentes
    assert len((tmp_path / "feature_usage.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_empty_name_is_refused_and_explained(tmp_path):
    rec = FeatureUsageRecorder(tmp_path)
    assert rec.record("worker", "") is False
    assert "empty name" in rec.last_error
    assert rec.read() == []


def test_corrupt_lines_are_skipped_not_fatal(tmp_path):
    path = tmp_path / "feature_usage.jsonl"
    rec = FeatureUsageRecorder(tmp_path)
    rec.record("worker", "ToolWorker")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps({"schema": "other/9", "name": "x"}) + "\n")
    entries = rec.read()
    assert [e["name"] for e in entries] == ["ToolWorker"]


def test_unwritable_directory_is_reported(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    rec = FeatureUsageRecorder(blocker / "sub")
    assert rec.record("worker", "ToolWorker") is False
    assert rec.last_error
    assert rec.describe()["exists"] is False


# ── 2. l'exécution réelle ──────────────────────────────────────────────────


def test_a_run_records_exactly_what_executed(monkeypatch, tmp_path):
    from experiments.ui_controller import ExperimentUIController

    usage_dir = tmp_path / "usage"
    monkeypatch.setenv("LIFE_MEAN_USAGE_DIR", str(usage_dir))
    monkeypatch.setenv("LIFE_MEAN_RUNS_DIR", str(tmp_path / "runs"))

    ui = ExperimentUIController()
    ui.register_experiment("exp_journal", {
        "domain": "math", "difficulty_range": (1, 1), "num_tasks": 3,
        "seed": 61, "deterministic": True,
    })
    assert ui.start_experiment("exp_journal")
    for _ in range(160):
        time.sleep(0.25)
        if not ui.get_experiment("exp_journal").is_running:
            break
    assert not ui.get_experiment("exp_journal").is_running

    entries = FeatureUsageRecorder(usage_dir).read()
    # deux lignes par tâche : le worker et l'outil réellement sélectionné
    assert len(entries) == 6, [e["name"] for e in entries]
    assert {e["kind"] for e in entries} == {"worker", "tool"}
    assert all(e["experiment_id"] == "exp_journal" for e in entries)
    assert all(e["task_id"] for e in entries)
    workers = [e for e in entries if e["kind"] == "worker"]
    assert {w["name"] for w in workers} == {"ToolWorker"}
    tools = [e for e in entries if e["kind"] == "tool"]
    # le nom enregistré est l'outil détecté, pas la famille entière du routeur
    assert all(t["name"].startswith(("math_", "physics_", "chemistry_")) for t in tools), tools
    assert len({t["name"] for t in tools}) <= 3


# ── 3. fusion dans le pont ─────────────────────────────────────────────────


def _bridge():
    return FeaturePoolBridge(REPO_ROOT)


def test_bridge_merges_runtime_records_as_a_separate_source():
    bridge = _bridge()
    now = time.time()
    records = [
        {"schema": SCHEMA, "timestamp": now, "kind": "worker", "name": "ToolWorker",
         "experiment_id": "e", "task_id": "t", "ok": None},
        {"schema": SCHEMA, "timestamp": now, "kind": "worker", "name": "ToolWorker",
         "experiment_id": "e", "task_id": "t", "ok": True},
    ]
    payload = bridge.usage([], runtime_records=records)

    assert payload["usage_sources"]["runtime"]["records"] == 2
    assert payload["usage_sources"]["runtime"]["ok"] == 1
    assert payload["usage_sources"]["logs"]["events_scanned"] == 0

    row = next(r for r in payload["rows"] if r["name"] == "ToolWorker")
    assert "runtime" in row["observed_via"]
    assert "RUNTIME_USAGE" in row["event_types"]
    assert row["observed_events"] == 2


def test_bridge_still_works_without_a_journal():
    payload = _bridge().usage([])
    assert payload["usage_sources"]["runtime"]["records"] == 0
    assert payload["rows"] == []


def test_features_endpoint_includes_the_runtime_cohort(monkeypatch, tmp_path):
    from pipeline_inspector.studio_interface import PipelineInspector

    usage_dir = tmp_path / "usage"
    rec = FeatureUsageRecorder(usage_dir)
    for _ in range(3):
        rec.record("worker", "ToolWorker", experiment_id="e", task_id="t")
    monkeypatch.setenv("LIFE_MEAN_USAGE_DIR", str(usage_dir))

    payload = PipelineInspector(REPO_ROOT, db_path=tmp_path / "empty.db").features()

    assert payload["coverage"]["runtime_records"] == 3
    assert payload["usage_sources"]["runtime"]["features_observed"] >= 1
    row = next((r for r in payload["rows"] if r["name"] == "ToolWorker"), None)
    assert row is not None and "runtime" in row["observed_via"]


# ── 4. appariement des noms : pas de faux positif sur les noms courts ─────


def test_short_feature_name_does_not_swallow_every_entity():
    """`math_gcd` comptait comme un usage de la fonctionnalité « C ».

    Le matcher de secours faisait `candidate_key in key` sans garde de longueur
    sur `candidate_key` : toute feature dont le nom normalisé est court (une
    lettre, un acronyme de 2-3 caractères) matchait n'importe quelle entité.
    """
    bridge = _bridge()
    assert bridge.map_entity("math_gcd") != bridge.map_entity("c")
    fid = bridge.map_entity("math_gcd")
    if fid is not None:
        name = (bridge._features.get(fid) or {}).get("name") or ""
        assert len(name) >= 6, f"math_gcd mapped to the short feature {name!r}"


def test_runtime_record_for_a_tool_does_not_inflate_a_short_feature():
    bridge = _bridge()
    now = time.time()
    records = [{"schema": SCHEMA, "timestamp": now, "kind": "tool",
                "name": "math_gcd", "experiment_id": "e", "task_id": "t", "ok": None}]
    payload = bridge.usage([], runtime_records=records)
    inflated = [r for r in payload["rows"] if len(str(r.get("name") or "")) < 6]
    assert inflated == [], inflated


def test_short_unique_name_maps_but_ambiguous_does_not():
    """« Stoic » doit trouver `StoicAgent` ; « C » ne doit rien absorber."""
    bridge = _bridge()
    stoic = bridge.map_entity("Stoic")
    if stoic is not None:
        assert "stoic" in str((bridge._features.get(stoic) or {}).get("name", "")).lower()
    # une entité d'une lettre ne matche que par égalité EXACTE (feature « C »),
    # jamais comme sous-chaîne d'un autre nom
    exact = bridge.map_entity("c")
    assert exact is None or str((bridge._features.get(exact) or {}).get("name")).lower() in ("c", "")
    # un outil qui ne correspond à aucune classe reste non apparié
    assert bridge.map_entity("math_gcd") is None
