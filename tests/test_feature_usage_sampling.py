"""Usage observé des fonctionnalités : l'échantillon doit être représentatif.

Constat mesuré sur la base réelle (837 054 événements) : l'onglet Feature Usage
annonçait « 2 fonctionnalités observées sur 989 » alors que 272 740 appels
d'outils et 31 agents distincts existaient dans la base.

Cause : `PipelineInspector.features()` ne lisait que les N événements les plus
récents **par type**. Sur cette base, les 5 005 événements les plus récents
venaient tous d'un seul producteur (`captn_experiences`), donc les 815 991
événements `raw_debates` — ceux qui portent `tool_worker`, `math_validation_worker`,
`math_gcd`, etc. — n'étaient jamais lus.

Ce fichier pin l'échantillonnage stratifié et sa couverture déclarée.
"""

from __future__ import annotations

import time

import pytest

from pathlib import Path

from pipeline_inspector.event_store import EventStore
from pipeline_inspector.schemas import EventType, PipelineEvent
from pipeline_inspector.studio_interface import PipelineInspector


def _ev(i, agent, source="raw_debates", event_type="TOOL_CALL", ts=None):
    return PipelineEvent(
        event_id=f"ev_{i:05d}",
        event_type=event_type,
        timestamp=ts if ts is not None else 1_700_000_000 + i,
        source=source,
        source_file="probe.jsonl",
        source_line=i,
        agent=agent,
        status="executed",
        raw_event_type=event_type,
        metadata={"tool": "math_gcd"},
    )


REPO_ROOT = Path(__file__).resolve().parent.parent


def _seed(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = EventStore(db_path)
    events = []
    i = 0
    # un producteur récent qui écrase la fenêtre (comme captn_experiences)
    for _ in range(400):
        events.append(_ev(i, "captn_runtime", source="captn_experiences",
                          event_type=EventType.MODEL_RESPONSE.value, ts=1_800_000_000 + i))
        i += 1
    # les vraies populations plus anciennes
    for agent in ("tool_worker", "math_validation_worker", "router"):
        for _ in range(50):
            events.append(_ev(i, agent, ts=1_700_000_000 + i))
            i += 1
    store.insert_events(events)
    return store


# ── 1. l'agrégat ───────────────────────────────────────────────────────────


def test_distinct_values_counts_each_population(tmp_path):
    store = _seed(tmp_path / "probe.db")
    rows = store.distinct_values("agent", event_types=[EventType.TOOL_CALL.value], limit=10)

    values = {r["value"]: r["events"] for r in rows}
    assert values["tool_worker"] == 50
    assert values["math_validation_worker"] == 50
    assert values["router"] == 50
    assert "captn_runtime" not in values  # MODEL_RESPONSE n'est pas dans le filtre


def test_distinct_values_refuses_an_unknown_column(tmp_path):
    store = _seed(tmp_path / "probe.db")
    with pytest.raises(ValueError, match="not groupable"):
        store.distinct_values("metadata_json; DROP TABLE events")


# ── 2. l'échantillonnage stratifié ─────────────────────────────────────────


def test_stratified_sample_reads_beyond_the_recent_window(tmp_path):
    db = tmp_path / "probe.db"
    _seed(db)
    inspector = PipelineInspector(REPO_ROOT, db_path=db)
    events, coverage = inspector._stratified_events(
        [EventType.TOOL_CALL.value, EventType.MODEL_RESPONSE.value], per_group=10, max_groups=10
    )

    agents = {e.get("agent") for e in events}
    assert {"tool_worker", "math_validation_worker", "router"} <= agents, agents
    assert "captn_runtime" in agents
    assert coverage["groups_sampled"] >= 4
    assert coverage["per_group_limit"] == 10
    assert coverage["truncated"] is True
    assert "stratified" in coverage["strategy"]


def test_features_reports_more_than_the_recent_producer(tmp_path):
    """Le rapport complet doit voir les workers, pas seulement le dernier producteur."""
    db = tmp_path / "probe.db"
    _seed(db)
    # le pont lit le Feature Pool du vrai dépôt ; seule la base est temporaire
    payload = PipelineInspector(REPO_ROOT, db_path=db).features()

    observed = {row["name"] for row in payload["rows"]}
    assert "ToolWorker" in observed, observed
    assert payload["features_observed"] > 1
    assert payload["coverage"]["per_group_limit"] == 300
    assert payload["features_loaded"] >= 900
    assert payload["coverage"]["note"].startswith("Compte un usage observé")


def test_coverage_is_declared_not_implied(tmp_path):
    db = tmp_path / "probe.db"
    _seed(db)
    # le pont lit le Feature Pool du vrai dépôt ; seule la base est temporaire
    payload = PipelineInspector(REPO_ROOT, db_path=db).features()
    coverage = payload["coverage"]

    assert coverage["events_sampled"] >= 1
    assert coverage["events_in_sampled_populations"] >= coverage["events_sampled"]
    assert isinstance(coverage["truncated"], bool)
    assert coverage["window"]
