"""Le journal d'usage couvre aussi les agents de débat.

Le pipeline déterministe enregistrait déjà ce qui s'exécute (`ToolWorker` +
l'outil détecté). Les débats multi-agents, eux, ne laissaient aucune trace
d'usage : les personas et les modèles réellement sollicités étaient invisibles du
compteur « fonctionnalités observées ».

Règle appliquée ici : une ligne par (agent, modèle) ayant produit **au moins un
tour avec du contenu**. Un persona muet (tour rejeté par le garde de répétition)
n'est pas compté — sinon le journal mesurerait le casting, pas l'exécution.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from experiments.autopilot import AutoPilot
from experiments.usage_recorder import FeatureUsageRecorder
from tests.test_debate_engine_integration import _build_real_engine, _task


def test_debate_agents_that_spoke_are_recorded(tmp_path):
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    records: List[Dict[str, Any]] = []
    autopilot.usage_sink = records.append

    results = autopilot.run_experiment(experiment_id, [_task()], {"temperature": 0.8})
    assert results, "the stubbed debate must produce a result"

    agents = [r for r in records if r["kind"] == "agent"]
    assert agents, "a debate that produced turns must record who spoke"
    assert all(a["name"] for a in agents)
    assert all(a["extra"].get("task_id") for a in agents)
    # le nom enregistré est un persona, pas un id interne
    assert all(len(a["name"]) > 1 for a in agents)
    # (agent, modèle) unique : un persona qui parle 3 fois n'est compté qu'une fois
    keys = [(a["name"], a["extra"].get("model")) for a in agents]
    assert len(keys) == len(set(keys))


def test_silent_personas_are_not_counted(tmp_path):
    autopilot, experiment_id, engine = _build_real_engine(tmp_path)
    records: List[Dict[str, Any]] = []
    autopilot.usage_sink = records.append
    autopilot.run_experiment(experiment_id, [_task()], {"temperature": 0.8})

    spoken = {
        (getattr(t, "speaker", "") or "").strip().lower()
        for t in engine.turn_manager.get_all_turns()
        if (t.response or "").strip()
    }
    recorded = {r["name"].strip().lower() for r in records if r["kind"] == "agent"}
    assert recorded <= spoken, f"recorded without content: {recorded - spoken}"


def test_without_a_sink_a_debate_still_runs(tmp_path):
    autopilot, experiment_id, _engine = _build_real_engine(tmp_path)
    assert autopilot.usage_sink is None
    results = autopilot.run_experiment(experiment_id, [_task()], {"temperature": 0.8})
    assert results, "telemetry must never be required to run a debate"


def test_a_failing_sink_never_breaks_the_debate(tmp_path, caplog):
    autopilot, experiment_id, _engine = _build_real_engine(tmp_path)

    def boom(_item):
        raise RuntimeError("sink exploded")

    autopilot.usage_sink = boom
    results = autopilot.run_experiment(experiment_id, [_task()], {"temperature": 0.8})
    assert results


def test_records_reach_the_journal_file(tmp_path, monkeypatch):
    """Bout en bout : sink -> FeatureUsageRecorder -> fichier JSONL."""
    usage_dir = tmp_path / "usage"
    recorder = FeatureUsageRecorder(usage_dir)
    autopilot, experiment_id, _engine = _build_real_engine(tmp_path)

    def sink(item):
        recorder.record(
            str(item.get("kind", "")), str(item.get("name", "")),
            experiment_id=experiment_id,
            task_id=str((item.get("extra") or {}).get("task_id", "")),
            ok=item.get("ok"),
        )

    autopilot.usage_sink = sink
    autopilot.run_experiment(experiment_id, [_task()], {"temperature": 0.8})

    entries = recorder.read()
    assert entries, "the journal must contain the debate agents"
    assert all(e["experiment_id"] == experiment_id for e in entries)
    assert {e["kind"] for e in entries} == {"agent"}
