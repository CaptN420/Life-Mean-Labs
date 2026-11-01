"""Tests unitaires — parser, store, corrélation, analyses, masquage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline_inspector.correlation import annotate, build_links, correlation_summary
from pipeline_inspector.error_analyzer import analyze as analyze_errors
from pipeline_inspector.event_store import EventStore
from pipeline_inspector.feature_pool_bridge import FeaturePoolBridge, normalize_name
from pipeline_inspector.ingest import PipelineIngestor
from pipeline_inspector.log_parser import (
    CodeLabEventsAdapter,
    HermesAuditAdapter,
    JsonlAdapter,
    ParseStats,
    RawDebatesAdapter,
    RecordContext,
    TextLogAdapter,
    default_adapters,
)
from pipeline_inspector.performance import model_metrics, pipeline_metrics
from pipeline_inspector.pipeline_graph import build_graph
from pipeline_inspector.redaction import redact_text, redact_value
from pipeline_inspector.schemas import EventType, PipelineEvent, parse_timestamp
from pipeline_inspector.security_inspector import analyze as analyze_security


# ── fixtures ────────────────────────────────────────────────────────────────
def _write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    _write_jsonl(tmp_path / "code_lab_runs" / "run1" / "logs" / "run1" / "events.jsonl", [
        {"event_type": "TASK_RECEIVED", "run_id": "run1", "event_seq": 0, "event_id": "e0",
         "timestamp": "2026-10-01T10:00:00+00:00", "prompt": "hello", "schema_version": "1.0",
         "collection_contract_version": "v0"},
        {"event_type": "AGENT_STARTED", "run_id": "run1", "event_seq": 1, "event_id": "e1",
         "timestamp": "2026-10-01T10:00:01+00:00", "role": "PLANNER", "schema_version": "1.0",
         "collection_contract_version": "v0"},
        {"event_type": "AGENT_RESPONSE", "run_id": "run1", "event_seq": 2, "event_id": "e2",
         "timestamp": "2026-10-01T10:00:02+00:00", "role": "PLANNER",
         "actual_model": "kwaipilot_kat-coder-v2.5-dev", "model_call_id": "mc1",
         "schema_version": "1.0", "collection_contract_version": "v0"},
        {"event_type": "FILE_MUTATION", "run_id": "run1", "event_seq": 3, "event_id": "e3",
         "timestamp": "2026-10-01T10:00:03+00:00", "path": "a.py", "operation": "created",
         "schema_version": "1.0", "collection_contract_version": "v0"},
        {"event_type": "TEST_RESULT", "run_id": "run1", "event_seq": 4, "event_id": "e4",
         "timestamp": "2026-10-01T10:00:04+00:00", "status": "failed",
         "schema_version": "1.0", "collection_contract_version": "v0"},
        {"event_type": "RUN_FAILED", "run_id": "run1", "event_seq": 5, "event_id": "e5",
         "timestamp": "2026-10-01T10:00:05+00:00", "error_type": "TEST_FAILURE",
         "schema_version": "1.0", "collection_contract_version": "v0"},
    ])
    _write_jsonl(tmp_path / "hermes-orchestrator" / "audit_log.jsonl", [
        {"correlation_id": "corr1", "task_id": "task1", "operation": "EXECUTE",
         "decision": "DENY", "reason": "dangerous", "component": "SecurityGateAdapter",
         "event_id": "a1", "timestamp": "2026-10-01T10:00:06Z"},
        {"correlation_id": "corr2", "task_id": "task2", "operation": "APPROVE",
         "decision": "ALLOW", "reason": "ok", "component": "SecurityGateAdapter",
         "event_id": "a2", "timestamp": "2026-10-01T10:00:07Z"},
    ])
    _write_jsonl(tmp_path / "captn_runtime" / "captn_experiences.jsonl", [
        {"id": "EXP-1", "query": "q", "timestamp": 1793000000.0,
         "result": {"success": True, "model_used": "m1", "tokens_input": 10,
                    "tokens_output": 20, "latency_ms": 1000.0, "error": None}},
    ])
    _write_jsonl(tmp_path / "data" / "raw_debates" / "exp_0.jsonl", [
        {"run_id": "run_x", "task_id": "task_x", "experiment_id": "exp_0",
         "timestamp": 1793000100.0,
         "routing_decision": {"selected": ["math_validation_worker"], "scores": {"math_validation_worker": 9.0}},
         "workers_used": ["math_validation_worker"], "tools_used": ["math_gcd", "math_lcm"],
         "validation_result": {"valid": True, "score": 1.0, "method": "deterministic", "error": None},
         "metadata": {"execution_mode": "deterministic"}},
    ])
    logs = tmp_path / "philosophical_council" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "application.log").write_text(
        "2026-10-01 10:00:00,000 - philosophical_council.core.debate_engine - INFO - GENERATION ID: gen-1 | CALL TYPE: initial\n"
        "2026-10-01 10:00:00,100 - philosophical_council.core.debate_engine - INFO - MODEL CALL #1 (attempt 0)\n"
        "2026-10-01 10:00:01,100 - httpx - INFO - HTTP Request: POST http://localhost:1234/v1/chat/completions \"HTTP/1.1 200 OK\"\n"
        "2026-10-01 10:00:02,000 - philosophical_council.core.debate_state - INFO - Debate stopped after 2 turns\n"
        "2026-10-01 10:00:03,000 - x - ERROR - LLM call failed: Error code: 401 - invalid api key sk-abcdef1234567890xyz\n",
        encoding="utf-8",
    )
    _write_jsonl(tmp_path / ".feature_pool_report.json", [])  # placeholder non lu (liste vide)
    return tmp_path


# ── schemas / redaction ─────────────────────────────────────────────────────
def test_parse_timestamp_formats():
    assert parse_timestamp("2026-10-01T10:00:00Z") is not None
    assert parse_timestamp(1793000000.0) == 1793000000.0
    assert parse_timestamp(1793000000000) == 1793000000.0
    assert parse_timestamp("not-a-date") is None
    assert parse_timestamp(None) is None


def test_redaction_masks_secrets_and_paths():
    text = "key sk-abcdef1234567890xyz and C:\\Users\\bob\\secret.py"
    out = redact_text(text)
    assert "sk-abcdef" not in out
    assert "bob" not in out
    assert "***REDACTED***" in out or "sk-***" in out


def test_redaction_masks_short_passwords_and_keys():
    """Régression : `password=hunter2` (7 car.) passait en clair."""
    text = "password=hunter2 AKIAABCDEFGHIJKLMNOP clé=abcdef"
    out = redact_text(text)
    assert "hunter2" not in out
    assert "AKIAABCDEFGHIJKLMNOP" not in out
    assert out.count("***REDACTED***") >= 2


def test_redaction_payload_nested():
    payload = {"api_key": "sk-xyz1234567890abc", "nested": {"token": "abc"}, "ok": 1}
    out = redact_value(payload)
    assert out["api_key"] == "***REDACTED***"
    assert out["nested"]["token"] == "***REDACTED***"
    assert out["ok"] == 1


def test_event_id_is_stable():
    kw = dict(event_type="TOOL_CALL", source="s", source_file="f", source_line=3, timestamp=1.0)
    a = PipelineEvent(**kw)
    b = PipelineEvent(**kw)
    assert a.event_id == b.event_id


# ── parsers ─────────────────────────────────────────────────────────────────
def test_code_lab_adapter_maps_types(project):
    ad = CodeLabEventsAdapter()
    files = ad.discover(project)
    assert len(files) == 1
    evs = [e for e, _ in ad.parse_file(files[0], "code_lab_runs/run1/logs/run1/events.jsonl")]
    types = [e.event_type for e in evs]
    assert EventType.PIPELINE_START.value in types
    assert EventType.MODEL_RESPONSE.value in types
    assert EventType.FILE_PATCH.value in types
    assert EventType.TEST_RESULT.value in types
    assert EventType.PIPELINE_ERROR.value in types


def test_hermes_adapter_decisions(project):
    ad = HermesAuditAdapter()
    f = ad.discover(project)[0]
    evs = [e for e, _ in ad.parse_file(f, "hermes-orchestrator/audit_log.jsonl")]
    assert {e.event_type for e in evs} == {EventType.SECURITY_DENY.value, EventType.SECURITY_APPROVE.value}


def test_text_adapter_parses_and_redacts(project):
    ad = TextLogAdapter()
    f = ad.discover(project)[0]
    evs = [e for e, _ in ad.parse_file(f, "philosophical_council/logs/application.log")]
    types = [e.event_type for e in evs]
    assert EventType.MODEL_REQUEST.value in types
    assert EventType.MODEL_RESPONSE.value in types
    assert EventType.PIPELINE_COMPLETE.value in types
    assert EventType.API_ERROR.value in types
    assert all("sk-abcdef" not in json.dumps(e.metadata) for e in evs)


def test_raw_debates_emits_full_chain(project):
    ad = RawDebatesAdapter()
    f = ad.discover(project)[0]
    evs = [e for e, _ in ad.parse_file(f, "data/raw_debates/exp_0.jsonl")]
    types = [e.event_type for e in evs]
    assert types[0] == EventType.PIPELINE_START.value
    assert EventType.ROUTING_DECISION.value in types
    assert types.count(EventType.TOOL_CALL.value) == 2
    assert EventType.TEST_RESULT.value in types
    assert types[-1] == EventType.PIPELINE_COMPLETE.value
    # chaque outil a un id distinct (pas de collision de doublons)
    tool_ids = [e.event_id for e in evs if e.event_type == EventType.TOOL_CALL.value]
    assert len(set(tool_ids)) == 2


def test_parser_tolerates_malformed_and_partial(tmp_path: Path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"a": 1}\nnot-json\n{"b": 2}\n{"partial": ', encoding="utf-8")

    class Dummy(JsonlAdapter):
        name = "dummy"
        def discover(self, root): return [p]
        def map_record(self, rec, ctx):
            return [PipelineEvent(
                event_type=EventType.UNKNOWN.value, source=self.name,
                source_file=ctx.relpath, source_line=ctx.line_no, timestamp=1.0,
                metadata={"raw_id": str(rec.get("a") or rec.get("b"))},
            )]

    evs = [e for e, _ in Dummy().parse_file(p, "bad.jsonl")]
    assert len(evs) == 2  # 2 lignes complètes, 1 malformée, 1 partielle ignorées


# ── store ───────────────────────────────────────────────────────────────────
def test_store_dedupes_and_filters(tmp_path: Path):
    store = EventStore(tmp_path / "e.db")
    ev = PipelineEvent(event_type="TOOL_CALL", source="s", source_file="f", source_line=1, timestamp=2.0)
    assert store.insert_events([ev]) == 1
    assert store.insert_events([ev]) == 0  # doublon ignoré
    assert store.count_events() == 1
    assert len(store.query(event_types=["TOOL_CALL"])) == 1
    assert store.query(event_types=["MODEL_RESPONSE"]) == []


def test_store_ingest_state_roundtrip(tmp_path: Path):
    store = EventStore(tmp_path / "e.db")
    assert store.get_ingest_state("f") is None
    store.set_ingest_state("f", 100, 1.5, 100, 3, 2, 2.0)
    st = store.get_ingest_state("f")
    assert st["offset"] == 100 and st["events"] == 2


# ── ingestion incrémentale ──────────────────────────────────────────────────
def test_store_ingest_state_truncated_roundtrip(tmp_path: Path):
    """Le drapeau `truncated` doit survivre à un aller-retour SQLite."""
    store = EventStore(tmp_path / "t.db")
    store.set_ingest_state("cap.jsonl", 500, 2.0, 120, 3, 3, 3.0, truncated=True)
    st = store.get_ingest_state("cap.jsonl")
    assert st["truncated"] == 1
    store.set_ingest_state("cap.jsonl", 500, 2.0, 500, 10, 10, 4.0, truncated=False)
    assert store.get_ingest_state("cap.jsonl")["truncated"] == 0


def test_ingestor_resumes_after_per_file_cap(tmp_path: Path):
    """Un fichier plafonné ne doit jamais être marqué consommé.

    Régression : l'état enregistrait size == st_size sans drapeau, si bien que
    la passe suivante le comptait comme « déjà ingéré » et perdait tout le
    reste du fichier en silence.
    """
    from pipeline_inspector.log_parser import LogAdapter

    root = tmp_path / "proj"
    log = root / "logs" / "big.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"n": i}) for i in range(10)]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    offsets, pos = [], 0
    for line in lines:
        pos += len(line.encode("utf-8")) + 1
        offsets.append(pos)

    class Cap(LogAdapter):
        name = "cap"
        description = "adapter de test"

        def discover(self, root: Path):
            return [log]

        def parse_file(self, path: Path, relpath: str, start_offset: int = 0):
            for i, off in enumerate(offsets):
                if off <= start_offset:
                    continue
                yield (
                    PipelineEvent(
                        event_id=f"cap-{i}",
                        event_type=EventType.PIPELINE_START.value,
                        timestamp=float(i),
                        source="cap",
                        source_file=relpath,
                        source_line=i + 1,
                    ),
                    off,
                )

    store = EventStore(tmp_path / "cap.db")
    ing = PipelineIngestor(root, store, [Cap()], max_records_per_file=4)

    r1 = ing.run()
    assert r1.added == 4
    state = store.get_ingest_state("logs/big.jsonl")
    assert state["truncated"] == 1
    assert r1.to_dict()["bytes_read"] > 0, "bytes_read doit refléter les octets examinés"

    r2 = ing.run()
    assert r2.added > 0, "la passe suivante doit reprendre, pas sauter le fichier"
    assert r2.to_dict()["files_skipped"] == 0
    assert store.count_events() > 4


def test_resume_offsets_are_absolute(tmp_path: Path):
    """Régression : les offsets renvoyés doivent être ABSOLUS après reprise.

    L'ancienne implémentation faisait `seek(start_offset)` puis comptait `pos`
    depuis 0, ce qui renvoyait des offsets relatifs ; l'ingestion les stockait
    comme absolus et la reprise repartait du mauvais endroit (fin de fichier
    perdue sur les gros logs).
    """
    class One(JsonlAdapter):
        name = "one"

        def map_record(self, rec, ctx):
            return [
                PipelineEvent(
                    event_id=f"one-{ctx.line_no}",
                    event_type=EventType.PIPELINE_START.value,
                    timestamp=float(ctx.line_no),
                    source="one",
                    source_file=ctx.relpath,
                    source_line=ctx.line_no,
                )
            ]

    path = tmp_path / "n.jsonl"
    lines = [json.dumps({"i": i}) for i in range(6)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    size = path.stat().st_size

    adapter = One()
    all_events = list(adapter.parse_file(path, "n.jsonl", 0))
    assert [ev.source_line for ev, _ in all_events] == [1, 2, 3, 4, 5, 6]
    assert all_events[-1][1] == size

    cut = all_events[2][1]  # fin de la ligne 3
    resumed = list(adapter.parse_file(path, "n.jsonl", cut))
    assert [ev.source_line for ev, _ in resumed] == [4, 5, 6]
    assert all(off > cut for _, off in resumed), "offsets doivent être absolus"
    assert resumed[-1][1] == size
    assert not any(ev.source_line <= 3 for ev, _ in resumed)


def test_ingestor_incremental_no_duplicates(project, tmp_path: Path):
    store = EventStore(tmp_path / "ing.db")
    ing = PipelineIngestor(project, store, default_adapters(project))
    r1 = ing.run()
    assert r1.added > 0
    total = store.count_events()
    r2 = ing.run()
    assert r2.added == 0
    assert store.count_events() == total
    # fichier modifié -> nouveaux événements seulement
    with open(project / "hermes-orchestrator" / "audit_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"correlation_id": "corr3", "task_id": "task3", "operation": "EXECUTE",
                             "decision": "ALLOW", "reason": "new", "component": "SecurityGateAdapter",
                             "event_id": "a3", "timestamp": "2026-10-01T10:00:08Z"}) + "\n")
    r3 = ing.run()
    assert r3.added >= 1
    assert store.count_events() > total


# ── corrélation ─────────────────────────────────────────────────────────────
def _mk(event_id, etype, ts, **kw):
    d = {"event_id": event_id, "event_type": etype, "timestamp": ts}
    d.update(kw)
    return d


def test_correlation_explicit_and_unknown():
    evs = [
        _mk("1", "MODEL_REQUEST", 10.0, session_id="s1"),
        _mk("2", "MODEL_RESPONSE", 11.0, session_id="s1", model_call_id="m1"),
        _mk("3", "TOOL_CALL", 12.0),  # sans session
    ]
    links = build_links(evs)
    assert any(l.relation == "probable" for l in links)
    summary = correlation_summary(evs)
    assert summary["events_without_session"] == 1
    annotated = annotate(evs)
    assert annotated[0]["link_to_previous"] is None
    assert annotated[2]["link_to_previous"] is None


def test_correlation_ambiguous_keeps_unknown():
    evs = [_mk("1", "TOOL_CALL", 10.0), _mk("2", "MODEL_REQUEST", 11.0)]
    annotated = annotate(evs)
    assert all(a["link_to_previous"] is None for a in annotated)


# ── graphe / perf / sécurité / erreurs ──────────────────────────────────────
def test_graph_built_from_observed_only():
    evs = [
        _mk("1", "PIPELINE_START", 1.0, session_id="s"),
        _mk("2", "MODEL_REQUEST", 2.0, session_id="s"),
        _mk("3", "MODEL_RESPONSE", 3.0, session_id="s", ok=True),
        _mk("4", "PIPELINE_COMPLETE", 4.0, session_id="s", ok=True),
    ]
    g = build_graph(evs)
    assert {n["id"] for n in g["nodes"]} == {"PIPELINE_START", "MODEL_REQUEST", "MODEL_RESPONSE", "PIPELINE_COMPLETE"}
    assert g["edges"][0]["count"] == 1
    assert "TOOL_CALL" in g["hypothesis_only"]


def test_performance_only_measured_values():
    evs = [
        _mk("1", "MODEL_RESPONSE", 1.0, model="m", ok=True,
            metadata={"tokens_input": 10, "tokens_output": 20, "latency_ms": 1000}),
        _mk("2", "MODEL_RESPONSE", 2.0, model="m", ok=False, metadata={}),
    ]
    m = model_metrics(evs)
    assert m["m"]["calls"] == 2 and m["m"]["failed"] == 1
    assert m["m"]["tokens_output"] == 20
    assert m["m"]["tokens_per_second"] == 20.0
    p = pipeline_metrics(evs)
    assert p["session_duration_s_avg"] is None  # pas d'identifiant de session


def test_security_detects_denied_but_executed():
    evs = [
        _mk("1", "SECURITY_REVIEW", 1.0, task_id="t1"),
        _mk("2", "SECURITY_DENY", 2.0, task_id="t1"),
        _mk("3", "TOOL_CALL", 3.0, task_id="t1", metadata={"tool": "terminal"}),
    ]
    s = analyze_security(evs)
    kinds = {i["kind"] for i in s["inconsistencies"]}
    assert "denied_but_executed" in kinds


def test_security_approve_is_not_proof():
    evs = [_mk("1", "SECURITY_APPROVE", 1.0, task_id="t2")]
    s = analyze_security(evs)
    assert s["total_decisions"] == 1
    assert "approved_without_execution" in {i["kind"] for i in s["inconsistencies"]}
    assert "APPROVE" in s["caveat"]


def test_error_classification():
    evs = [
        _mk("1", "API_ERROR", 1.0, ok=False, metadata={"message": "Error code: 401 - invalid api key"}),
        _mk("2", "PIPELINE_ERROR", 2.0, ok=False, metadata={"message": "No module named 'pytest'"}),
        _mk("3", "PIPELINE_ERROR", 3.0, ok=False, metadata={"raw_event_type": "RUN_RESULT"}),
    ]
    e = analyze_errors(evs)
    codes = e["by_code"]
    assert codes.get("AUTH_INVALID") == 1
    assert codes.get("MISSING_DEPENDENCY") == 1
    assert codes.get("VALIDATION_FAILED") == 1
    assert e["recommendations"]


# ── Feature Pool bridge ─────────────────────────────────────────────────────
def test_feature_bridge_maps_and_never_validates(tmp_path: Path):
    report = {
        "features": [
            {"id": "feat_agents_ToolWorker", "name": "ToolWorker", "category": "agents",
             "status": "BLOCKED", "integration_status": "NOT_STARTED", "test_paths": []},
        ]
    }
    (tmp_path / ".feature_pool_report.json").write_text(json.dumps(report), encoding="utf-8")
    bridge = FeaturePoolBridge(tmp_path)
    assert bridge.map_entity("tool_worker") == "feat_agents_ToolWorker"
    usage = bridge.usage([_mk("1", "TOOL_CALL", 1.0, agent="tool_worker", ok=True)])
    row = usage["rows"][0]
    assert row["observed_events"] == 1
    assert row["status"] == "BLOCKED"  # statut inchangé
    assert "≠ validation" in row["note"]


def test_normalize_name():
    assert normalize_name("MathValidationWorker") == normalize_name("math_validation_worker")


# ── dashboard payloads ──────────────────────────────────────────────────────
def test_inspector_end_to_end_payloads(project, tmp_path: Path):
    from pipeline_inspector.studio_interface import PipelineInspector

    insp = PipelineInspector(project, db_path=tmp_path / "pi.db")
    insp.ingest()
    assert insp.stats()["total_events"] > 0
    assert insp.sessions() is not None
    assert insp.events(limit=5)
    g = insp.graph()
    assert g["nodes"] and "edges" in g
    s = insp.security()
    assert s["total_decisions"] >= 2
    p = insp.performance()
    assert "models" in p and "pipeline" in p
    e = insp.errors()
    assert e["total_errors"] >= 1
    f = insp.features()
    assert "rows" in f


def test_reports_never_overwrite(project, tmp_path: Path):
    from pipeline_inspector.studio_interface import PipelineInspector

    insp = PipelineInspector(project, db_path=tmp_path / "pi.db")
    insp.ingest()
    first = insp.generate_reports()
    second = insp.generate_reports()
    assert set(first) == set(second)
    assert first["IMPLEMENTATION_STATUS.md"] != second["IMPLEMENTATION_STATUS.md"]
    for path in first.values():
        assert Path(path).exists()
    for path in second.values():
        assert Path(path).exists()
