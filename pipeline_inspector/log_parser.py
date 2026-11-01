"""Parseurs de logs — adapters non destructifs, lecture seule.

Chaque adapter :
- découvre ses fichiers sous une racine ;
- lit en flux, par offset croissant (ingestion incrémentale) ;
- normalise chaque ligne en ``PipelineEvent`` ;
- conserve la référence exacte (fichier + numéro de ligne) ;
- tolère les lignes malformées sans interrompre le fichier.

Aucun adapter n'écrit, ne déplace ni ne supprime un fichier source.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .redaction import redact_text, redact_value
from .schemas import EventType, PipelineEvent, parse_timestamp, stable_event_id


@dataclass
class ParseStats:
    """Compteurs d'une passe de parsing."""

    files_seen: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    records_read: int = 0  # événements normalisés (pas de comptage de lignes brutes)
    events_emitted: int = 0
    malformed_lines: int = 0
    bytes_read: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_seen": self.files_seen,
            "files_parsed": self.files_parsed,
            "files_skipped": self.files_skipped,
            "records_read": self.records_read,
            "events_emitted": self.events_emitted,
            "malformed_lines": self.malformed_lines,
            "bytes_read": self.bytes_read,
            "errors": self.errors[:20],
        }


@dataclass
class RecordContext:
    """Contexte d'une ligne brute pendant le parsing."""

    root: Path
    path: Path
    relpath: str
    line_no: int
    size: int
    mtime: float


class LogAdapter:
    """Interface commune. Un adapter = un format de log."""

    name = "base"
    description = ""

    def discover(self, root: Path) -> List[Path]:
        raise NotImplementedError

    def parse_file(
        self, path: Path, relpath: str, start_offset: int = 0
    ) -> Iterator[Tuple[PipelineEvent, int]]:
        """Yield ``(event, next_offset)``. ``next_offset`` suit la dernière
        ligne complète consommée."""
        raise NotImplementedError


# ── JSONL génériques ─────────────────────────────────────────────────────────


class JsonlAdapter(LogAdapter):
    """Lit un JSONL ligne par ligne, avec offset incrémental."""

    name = "jsonl"
    description = "JSON Lines générique"

    def discover(self, root: Path) -> List[Path]:
        return []

    def map_record(self, rec: Dict[str, Any], ctx: RecordContext) -> List[PipelineEvent]:
        return []

    def _read_lines(
        self, path: Path, start_offset: int
    ) -> Iterator[Tuple[int, str, int]]:
        """Yield ``(line_no, text, next_offset)`` pour les lignes complètes.

        ⚠️ Les offsets renvoyés sont ABSOLUS (position réelle dans le fichier).
        L'ancienne version faisait ``seek(start_offset)`` puis comptait ``pos``
        depuis 0 : les offsets renvoyés étaient donc *relatifs* au point de
        reprise. L'ingestion les enregistrait comme absolus → l'offset
        rétrécissait à chaque passe, la reprise repartait du mauvais endroit et
        la fin des gros fichiers était lue puis perdue. On relit ici depuis le
        début en sautant les lignes déjà consommées : coût linéaire (≈1 s pour
        85 Mo) mais offsets et numéros de ligne exacts.
        """
        with open(path, "rb") as fh:
            pos = 0
            line_no = 0
            while True:
                chunk = fh.readline()
                if not chunk:
                    break
                pos += len(chunk)
                line_no += 1
                if pos <= start_offset:
                    # ligne entièrement consommée lors d'une passe précédente
                    continue
                if not chunk.endswith(b"\n"):
                    # ligne partielle : on ne la consomme pas
                    break
                text = chunk.decode("utf-8", errors="replace").strip()
                if text:
                    yield line_no, text, pos

    def parse_file(
        self, path: Path, relpath: str, start_offset: int = 0
    ) -> Iterator[Tuple[PipelineEvent, int]]:
        size = path.stat().st_size
        mtime = path.stat().st_mtime
        for line_no, text, next_offset in self._read_lines(path, start_offset):
            ctx = RecordContext(path.parent, path, relpath, line_no, size, mtime)
            try:
                rec = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            for ev in self.map_record(rec, ctx):
                yield ev, next_offset


class CodeLabEventsAdapter(JsonlAdapter):
    """Événements structurés Code Lab (events.jsonl, schema v1.0)."""

    name = "code_lab_events"
    description = "code_lab_runs/*/logs/*/events.jsonl"

    MAP = {
        "TASK_RECEIVED": EventType.PIPELINE_START,
        "AGENT_STARTED": EventType.AGENT_SELECTED,
        "AGENT_RESPONSE": EventType.MODEL_RESPONSE,
        "FILE_MUTATION": EventType.FILE_PATCH,
        "TEST_RESULT": EventType.TEST_RESULT,
        "RUN_COMPLETED": EventType.PIPELINE_COMPLETE,
        "RUN_FAILED": EventType.PIPELINE_ERROR,
    }

    def discover(self, root: Path) -> List[Path]:
        base = root / "code_lab_runs"
        if not base.exists():
            return []
        return sorted(base.glob("*/logs/*/events.jsonl"))

    def map_record(self, rec: Dict[str, Any], ctx: RecordContext) -> List[PipelineEvent]:
        raw_type = str(rec.get("event_type") or "UNKNOWN")
        ev_type = self.MAP.get(raw_type, EventType.UNKNOWN).value
        ts = parse_timestamp(rec.get("timestamp") or rec.get("created_at")) or ctx.mtime

        status = rec.get("status") or rec.get("final_status")
        ok: Optional[bool] = None
        if isinstance(status, str):
            ok = status.lower() in {"passed", "success", "completed", "ok"}

        meta = redact_value({k: v for k, v in rec.items() if k not in {
            "event_type", "timestamp", "created_at", "event_id", "event_seq",
            "schema_version", "collection_contract_version", "run_id",
        }})
        meta["raw_id"] = rec.get("event_id") or f"{rec.get('run_id')}:{rec.get('event_seq')}"

        ev = PipelineEvent(
            event_type=ev_type,
            source=self.name,
            source_file=ctx.relpath,
            source_line=ctx.line_no,
            timestamp=ts,
            session_id=rec.get("run_id"),
            run_id=rec.get("run_id"),
            request_id=rec.get("model_call_id") or rec.get("attempt_id"),
            model_call_id=rec.get("model_call_id"),
            agent=rec.get("role"),
            model=rec.get("actual_model") or rec.get("configured_model"),
            status=status,
            ok=ok,
            raw_event_type=raw_type,
            metadata=meta,
            correlation="probable" if rec.get("run_id") else "unknown",
            confidence=0.7 if rec.get("run_id") else 0.0,
        )
        return [ev]


class TrajectoryAdapter(JsonlAdapter):
    """Trajectoires d'exécution Code Lab (raw/trajectory.jsonl)."""

    name = "code_lab_trajectory"
    description = "code_lab_runs/*/raw/trajectory.jsonl"

    def discover(self, root: Path) -> List[Path]:
        base = root / "code_lab_runs"
        if not base.exists():
            return []
        return sorted(base.glob("*/raw/trajectory.jsonl"))

    def map_record(self, rec: Dict[str, Any], ctx: RecordContext) -> List[PipelineEvent]:
        pytest_block = rec.get("pytest") if isinstance(rec.get("pytest"), dict) else None
        if not pytest_block:
            return []
        ts = ctx.mtime
        run_id = ctx.path.parent.parent.name if ctx.path.parent.name == "raw" else None
        iteration = rec.get("iteration")
        passed = bool(pytest_block.get("passed"))
        total = pytest_block.get("total")
        meta = redact_value({
            "iteration": iteration,
            "stage": rec.get("stage"),
            "command": pytest_block.get("command"),
            "returncode": pytest_block.get("returncode"),
            "total": total,
            "passed_count": pytest_block.get("passed_count"),
            "failures": pytest_block.get("failures"),
            "errors": pytest_block.get("errors"),
            "output": pytest_block.get("output"),
            "raw_id": f"{run_id}:iter{iteration}",
        })
        ev = PipelineEvent(
            event_type=EventType.TEST_RESULT.value,
            source=self.name,
            source_file=ctx.relpath,
            source_line=ctx.line_no,
            timestamp=ts,
            session_id=run_id,
            run_id=run_id,
            agent="pytest",
            status="passed" if passed else "failed",
            ok=passed,
            raw_event_type="TRAJECTORY_TEST",
            metadata=meta,
            correlation="probable" if run_id else "unknown",
            confidence=0.6 if run_id else 0.0,
        )
        return [ev]


class HermesAuditAdapter(JsonlAdapter):
    """Décisions de sécurité Hermes (audit_log.jsonl)."""

    name = "hermes_audit"
    description = "hermes-orchestrator/audit_log.jsonl"

    def discover(self, root: Path) -> List[Path]:
        candidates = [
            root / "hermes-orchestrator" / "audit_log.jsonl",
            root / "audit_log.jsonl",
        ]
        return [p for p in candidates if p.exists()]

    def map_record(self, rec: Dict[str, Any], ctx: RecordContext) -> List[PipelineEvent]:
        decision = str(rec.get("decision") or "").upper()
        mapping = {
            "ALLOW": EventType.SECURITY_APPROVE,
            "APPROVE": EventType.SECURITY_APPROVE,
            "DENY": EventType.SECURITY_DENY,
            "REJECT": EventType.SECURITY_DENY,
            "PENDING_APPROVAL": EventType.SECURITY_ESCALATE,
            "ESCALATE": EventType.SECURITY_ESCALATE,
        }
        ev_type = mapping.get(decision, EventType.SECURITY_REVIEW).value
        ts = parse_timestamp(rec.get("timestamp")) or ctx.mtime
        meta = redact_value({
            "operation": rec.get("operation"),
            "decision": decision or None,
            "reason": rec.get("reason"),
            "workspace_id": rec.get("workspace_id"),
            "details": rec.get("details"),
            "raw_id": rec.get("event_id"),
        })
        ev = PipelineEvent(
            event_type=ev_type,
            source=self.name,
            source_file=ctx.relpath,
            source_line=ctx.line_no,
            timestamp=ts,
            session_id=rec.get("correlation_id"),
            conversation_id=rec.get("correlation_id"),
            task_id=rec.get("task_id"),
            agent=rec.get("component"),
            status=decision or "REVIEW",
            ok=decision in {"ALLOW", "APPROVE"} if decision else None,
            raw_event_type=rec.get("operation") or "SECURITY",
            metadata=meta,
            correlation="explicit" if rec.get("correlation_id") else "unknown",
            confidence=1.0 if rec.get("correlation_id") else 0.0,
        )
        return [ev]


class CaptnExperiencesAdapter(JsonlAdapter):
    """Expériences CaptN (captn_experiences.jsonl) — tokens et latence."""

    name = "captn_experiences"
    description = "captn_runtime/captn_experiences.jsonl"

    def discover(self, root: Path) -> List[Path]:
        p = root / "captn_runtime" / "captn_experiences.jsonl"
        return [p] if p.exists() else []

    def map_record(self, rec: Dict[str, Any], ctx: RecordContext) -> List[PipelineEvent]:
        result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
        ts = parse_timestamp(rec.get("timestamp")) or ctx.mtime
        success = result.get("success")
        meta = redact_value({
            "tokens_input": result.get("tokens_input"),
            "tokens_output": result.get("tokens_output"),
            "cost_usd": result.get("cost_usd"),
            "context_reduction": result.get("context_reduction"),
            "compression_applied": result.get("compression_applied"),
            "memory_hits": result.get("memory_hits"),
            "error": result.get("error"),
            "query_preview": redact_text(str(rec.get("query") or ""), 300),
            "response_preview": redact_text(str(result.get("response") or ""), 300),
            "raw_id": rec.get("id"),
        })
        ev = PipelineEvent(
            event_type=EventType.MODEL_RESPONSE.value,
            source=self.name,
            source_file=ctx.relpath,
            source_line=ctx.line_no,
            timestamp=ts,
            session_id=rec.get("id"),
            request_id=rec.get("id"),
            agent="captn_runtime",
            model=result.get("model_used") or None,
            status="success" if success else "failed",
            ok=bool(success),
            duration_ms=float(result["latency_ms"]) if result.get("latency_ms") else None,
            raw_event_type="EXPERIENCE",
            metadata=meta,
            correlation="unknown",
            confidence=0.0,
        )
        return [ev]


class RawDebatesAdapter(JsonlAdapter):
    """Traces de génération débats/agents (data/raw_debates/*.jsonl).

    Un enregistrement = une exécution complète :
    routage -> outils -> validation -> réponse.
    """

    name = "raw_debates"
    description = "data/raw_debates/*.jsonl"

    def discover(self, root: Path) -> List[Path]:
        base = root / "data" / "raw_debates"
        if not base.exists():
            return []
        return sorted(base.glob("*.jsonl"))

    def map_record(self, rec: Dict[str, Any], ctx: RecordContext) -> List[PipelineEvent]:
        ts = parse_timestamp(rec.get("timestamp")) or ctx.mtime
        run_id = rec.get("run_id")
        task_id = rec.get("task_id")
        exp_id = rec.get("experiment_id")
        # session = cohorte d'expérience (regroupement honnête de plusieurs runs)
        session = exp_id or run_id or task_id
        out: List[PipelineEvent] = []

        base_meta = redact_value({
            "experiment_id": exp_id,
            "generation_id": rec.get("generation_id"),
            "domain": (rec.get("config") or {}).get("domain") if isinstance(rec.get("config"), dict) else None,
            "execution_mode": (rec.get("metadata") or {}).get("execution_mode") if isinstance(rec.get("metadata"), dict) else None,
            "raw_id": f"{run_id}:{task_id}",
        })

        def mk(ev_type: str, **kw: Any) -> PipelineEvent:
            meta = dict(base_meta)
            meta.update(redact_value(kw.pop("meta", {})))
            return PipelineEvent(
                event_type=ev_type,
                source=self.name,
                source_file=ctx.relpath,
                source_line=ctx.line_no,
                timestamp=kw.pop("timestamp", ts),
                session_id=session,
                run_id=run_id,
                task_id=task_id,
                raw_event_type=kw.pop("raw_type", ev_type),
                metadata=meta,
                correlation="probable" if session else "unknown",
                confidence=0.7 if session else 0.0,
                **kw,
            )

        out.append(mk(EventType.PIPELINE_START.value, raw_type="TASK_RECEIVED",
                      status="received", ok=None))

        routing = rec.get("routing_decision")
        if isinstance(routing, dict) and routing:
            out.append(mk(EventType.ROUTING_DECISION.value, raw_type="ROUTING_DECISION",
                          agent="router", status="selected",
                          meta={
                              "selected": routing.get("selected"),
                              "scores": routing.get("scores"),
                              "difficulty": routing.get("difficulty"),
                              "adaptive_top_k": routing.get("adaptive_top_k"),
                              "opposition_mode": routing.get("opposition_mode"),
                          }))

        for idx, worker in enumerate(rec.get("workers_used") or []):
            out.append(mk(EventType.AGENT_SELECTED.value, raw_type="WORKER_USED",
                          agent=str(worker), status="selected", ok=None,
                          meta={"worker": worker,
                                "raw_id": f"{run_id}:{task_id}:worker:{idx}:{worker}"}))

        for idx, tool in enumerate(rec.get("tools_used") or []):
            out.append(mk(EventType.TOOL_CALL.value, raw_type="TOOL_CALL",
                          agent="tool_worker", status="executed", ok=None,
                          meta={"tool": tool,
                                "raw_id": f"{run_id}:{task_id}:tool:{idx}:{tool}"}))

        validation = rec.get("validation_result")
        if isinstance(validation, dict) and validation:
            valid = validation.get("valid")
            out.append(mk(EventType.TEST_RESULT.value, raw_type="VALIDATION_RESULT",
                          agent="validator",
                          status="valid" if valid else "invalid",
                          ok=bool(valid),
                          meta={"method": validation.get("method"),
                                "score": validation.get("score"),
                                "error": validation.get("error")}))

        failed = bool(validation.get("valid") is False) if isinstance(validation, dict) else False
        out.append(mk(
            EventType.PIPELINE_ERROR.value if failed else EventType.PIPELINE_COMPLETE.value,
            raw_type="RUN_RESULT", status="failed" if failed else "completed", ok=not failed,
        ))
        return out


class TextLogAdapter(LogAdapter):
    """Journaux texte type `logging` Python (application.log/stdout.log)."""

    name = "text_log"
    description = "*.log au format 'date - logger - LEVEL - message'"

    LINE_RE = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+-\s+"
        r"(?P<logger>[\w\.\-]+)\s+-\s+(?P<level>[A-Z]+)\s+-\s+(?P<msg>.*)$"
    )
    GEN_RE = re.compile(r"GENERATION ID:\s*([\w\-]+)")
    MODEL_CALL_RE = re.compile(r"MODEL CALL #(\d+)\s*\(attempt\s*(\d+)\)")
    HTTP_RE = re.compile(r"HTTP Request:\s*(\w+)\s+(\S+)\s+\"(.*?)\"")
    DEBATE_STOP_RE = re.compile(r"Debate stopped after\s+(\d+)\s+turns")
    SAVED_RE = re.compile(r"Saved experiment\s+([\w\-]+)")
    TOOL_HINT_RE = re.compile(r"\b(tool|skill)\s+['\"]?([\w\-]+)['\"]?", re.I)

    def discover(self, root: Path) -> List[Path]:
        out: List[Path] = []
        base = root / "philosophical_council" / "logs"
        if base.exists():
            out.extend(sorted(base.glob("*.log")))
        return out

    def _classify(self, msg: str, level: str) -> Tuple[str, Optional[bool], Optional[str], Dict[str, Any]]:
        meta: Dict[str, Any] = {}
        if m := self.MODEL_CALL_RE.search(msg):
            meta.update({"call_index": int(m.group(1)), "attempt": int(m.group(2))})
            return EventType.MODEL_REQUEST.value, None, "started", meta
        if m := self.HTTP_RE.search(msg):
            meta.update({"method": m.group(1), "url": redact_text(m.group(2), 200),
                         "http_status": redact_text(m.group(3), 120)})
            ok = " 200 " in f" {m.group(3)} " or " 2" in m.group(3)[:4]
            return EventType.MODEL_RESPONSE.value, ok, "http_response", meta
        if m := self.DEBATE_STOP_RE.search(msg):
            meta["turns"] = int(m.group(1))
            return EventType.PIPELINE_COMPLETE.value, True, "stopped", meta
        if m := self.SAVED_RE.search(msg):
            meta["experiment_id"] = m.group(1)
            return EventType.PIPELINE_COMPLETE.value, True, "saved", meta
        if m := self.TOOL_HINT_RE.search(msg):
            meta["tool"] = m.group(2)
            return EventType.TOOL_CALL.value, None, "referenced", meta
        if level in {"ERROR", "CRITICAL"}:
            return EventType.API_ERROR.value, False, "error", meta
        if level == "WARNING":
            return EventType.PIPELINE_ERROR.value, False, "warning", meta
        return EventType.UNKNOWN.value, None, None, meta

    def parse_file(
        self, path: Path, relpath: str, start_offset: int = 0
    ) -> Iterator[Tuple[PipelineEvent, int]]:
        size = path.stat().st_size
        mtime = path.stat().st_mtime
        with open(path, "rb") as fh:
            fh.seek(start_offset)
            pos = start_offset
            line_no = 0
            gen_id: Optional[str] = None
            while True:
                chunk = fh.readline()
                if not chunk:
                    break
                pos += len(chunk)
                line_no += 1
                if not chunk.endswith(b"\n"):
                    break
                text = chunk.decode("utf-8", errors="replace").rstrip()
                m = self.LINE_RE.match(text)
                if not m:
                    continue
                if g := self.GEN_RE.search(m.group("msg")):
                    gen_id = g.group(1)
                ev_type, ok, status, meta = self._classify(m.group("msg"), m.group("level"))
                if ev_type == EventType.UNKNOWN.value:
                    continue
                meta = redact_value(meta)
                meta["level"] = m.group("level")
                meta["message"] = redact_text(m.group("msg"), 800)
                meta["logger"] = m.group("logger")
                meta["raw_id"] = f"{gen_id or ''}:{line_no}"
                ts = parse_timestamp(m.group("ts")) or mtime
                ev = PipelineEvent(
                    event_type=ev_type,
                    source=self.name,
                    source_file=relpath,
                    source_line=line_no,
                    timestamp=ts,
                    session_id=gen_id,
                    agent=m.group("logger"),
                    status=status,
                    ok=ok,
                    raw_event_type=m.group("level"),
                    metadata=meta,
                    correlation="probable" if gen_id else "unknown",
                    confidence=0.6 if gen_id else 0.3,
                )
                yield ev, pos


def default_adapters(root: Path) -> List[LogAdapter]:
    """Adapters activés par défaut, filtrés sur les fichiers réellement présents."""
    candidates: List[LogAdapter] = [
        CodeLabEventsAdapter(),
        TrajectoryAdapter(),
        HermesAuditAdapter(),
        CaptnExperiencesAdapter(),
        RawDebatesAdapter(),
        TextLogAdapter(),
    ]
    active = []
    for ad in candidates:
        try:
            if ad.discover(root):
                active.append(ad)
        except OSError:
            continue
    return active
