"""Façade unique + mixin HTTP pour le dashboard.

``PipelineInspector`` est la seule porte d'entrée utilisée par l'UI.
``PipelineApiMixin`` fournit les méthodes appelées par ``experiments.dashboard``
(la classe handler y ajoute simplement le routage).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import correlation, error_analyzer, performance, pipeline_graph, security_inspector
from .event_store import EventStore
from .feature_pool_bridge import FeaturePoolBridge
from .ingest import IngestResult, PipelineIngestor
from .log_parser import default_adapters
from .report_generator import ReportGenerator


class PipelineInspector:
    """Point d'entrée : ingestion, lecture, analyses, rapports."""

    def __init__(
        self,
        project_root: str | Path,
        db_path: Optional[str | Path] = None,
        auto_ingest: bool = False,
    ):
        self.root = Path(project_root).resolve()
        self.db_path = Path(db_path) if db_path else self.root / "data" / "pipeline_inspector.db"
        self.store = EventStore(self.db_path)
        self.bridge = FeaturePoolBridge(self.root)
        self.reports = ReportGenerator(self.root)
        self._ingest_lock = threading.Lock()
        self._ingestor: Optional[PipelineIngestor] = None
        self.last_ingest: Optional[Dict[str, Any]] = None
        if auto_ingest:
            try:
                self.ingest()
            except Exception:
                pass

    # ── ingestion ─────────────────────────────────────────────────────────
    def ingestor(self) -> PipelineIngestor:
        if self._ingestor is None:
            self._ingestor = PipelineIngestor(self.root, self.store, default_adapters(self.root))
        return self._ingestor

    def ingest(self, full_rescan: bool = False, adapter_names: Optional[List[str]] = None) -> Dict[str, Any]:
        with self._ingest_lock:
            result: IngestResult = self.ingestor().run(
                full_rescan=full_rescan, adapter_names=adapter_names
            )
            self.last_ingest = result.to_dict()
            return self.last_ingest

    def sources(self) -> Dict[str, Dict[str, Any]]:
        found = self.ingestor().discover()
        return {
            name: {"files": len(paths), "description": next(
                (a.description for a in self.ingestor().adapters if a.name == name), ""
            )}
            for name, paths in found.items()
        }

    # ── lecture ───────────────────────────────────────────────────────────
    def events(self, limit: int = 200, **filters: Any) -> List[Dict[str, Any]]:
        raw = self.store.query(limit=limit, **filters)
        return correlation.annotate(raw)

    def sessions(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.store.sessions(limit=limit)

    def stats(self) -> Dict[str, Any]:
        base = self.store.stats()
        base["sources"] = self.sources()
        base["last_ingest"] = self.last_ingest
        base["feature_pool_source"] = self.bridge.source
        return base

    def _events_for(
        self,
        event_types: Optional[List[str]] = None,
        limit: int = 20000,
        ok_only_failures: bool = False,
    ) -> List[Dict[str, Any]]:
        """Échantillon des événements les plus récents pour un type donné.

        Les analyses portent sur une fenêtre explicite (les N derniers
        événements) afin de rester réactives sur de gros volumes.
        """
        events = self.store.query(event_types=event_types, limit=limit, order="desc")
        events.reverse()
        if ok_only_failures:
            events = [e for e in events if e.get("ok") is False]
        return events

    def _all_events(self, limit: int = 20000) -> List[Dict[str, Any]]:
        return self._events_for(limit=limit)

    # ── analyses ──────────────────────────────────────────────────────────
    @staticmethod
    def _sample(events: List[Dict[str, Any]], limit: int) -> Dict[str, Any]:
        """Décrit l'échantillon réellement analysé.

        Les analyses lisent les N événements les plus récents (réactivité sur
        de gros volumes). Sans cette mention, un compteur issu d'un
        échantillon serait lu comme un total exhaustif — c'est exactement le
        genre de fausse précision que le projet interdit.
        """
        return {
            "events_scanned": len(events),
            "limit": limit,
            "truncated": len(events) >= limit,
            "note": "analyse sur les {} derniers événements, pas sur la base entière".format(limit),
        }

    def graph(self) -> Dict[str, Any]:
        events = self._all_events()
        payload = pipeline_graph.build_graph(events)
        payload['sample'] = self._sample(events, 20000)
        return payload

    def security(self) -> Dict[str, Any]:
        from .schemas import EventType as _ET
        types = [_ET.SECURITY_REVIEW.value, _ET.SECURITY_APPROVE.value,
                 _ET.SECURITY_DENY.value, _ET.SECURITY_ESCALATE.value]
        events = self._events_for(event_types=types, limit=10000)
        # les exécutions aident à détecter les incohérences (deny puis exécution)
        events += self._events_for(
            event_types=[_ET.TOOL_CALL.value, _ET.FILE_PATCH.value, _ET.TOOL_RESULT.value],
            limit=10000,
        )
        payload = security_inspector.analyze(events)
        payload['sample'] = self._sample(events, 20000)
        return payload

    def performance(self) -> Dict[str, Any]:
        from .schemas import EventType as _ET
        events = self._events_for(event_types=[_ET.MODEL_RESPONSE.value], limit=20000)
        pipeline_view = self._all_events(limit=20000)
        return {"models": performance.model_metrics(events),
                "pipeline": performance.pipeline_metrics(pipeline_view),
                "sample": self._sample(events + pipeline_view, 40000)}

    def errors(self) -> Dict[str, Any]:
        from .schemas import EventType as _ET
        events = self._events_for(event_types=[_ET.API_ERROR.value], limit=20000)
        events += self._events_for(event_types=[_ET.PIPELINE_ERROR.value], limit=5000)
        payload = error_analyzer.analyze(events)
        payload['sample'] = self._sample(events, 25000)
        return payload

    def features(self) -> Dict[str, Any]:
        """Usage observé des fonctionnalités, échantillonné par population.

        L'ancienne version ne lisait que les N événements les plus récents par
        type. Sur une base réelle (837 k événements), la fenêtre récente était
        monopolisée par un seul producteur (5 005 événements `captn_experiences`)
        et le rapport annonçait « 2 fonctionnalités observées sur 989 » alors que
        272 k appels d'outils et 31 agents distincts existaient plus loin dans
        l'historique. Ce n'était pas un manque d'usage : c'était un échantillon
        non représentatif.
        """
        from .schemas import EventType as _ET

        types = [
            _ET.TOOL_CALL.value,
            _ET.AGENT_SELECTED.value,
            _ET.MODEL_RESPONSE.value,
            _ET.TEST_RESULT.value,
        ]
        events, coverage = self._stratified_events(types, per_group=300, max_groups=60)

        # Journal d'usage runtime : preuve directe de ce qui a tourné (les logs
        # ingérés ne contiennent que ce que l'ingestion a bien voulu garder).
        runtime_records: List[Dict[str, Any]] = []
        try:
            from experiments.usage_recorder import FeatureUsageRecorder
            runtime_records = FeatureUsageRecorder().read(limit=50000)
        except Exception as exc:  # noqa: BLE001 - l'absence de journal n'est pas une panne
            coverage["runtime_journal_error"] = f"{type(exc).__name__}: {exc}"
        coverage["runtime_records"] = len(runtime_records)

        payload = self.bridge.usage(events, runtime_records=runtime_records)
        payload['sample'] = self._sample(events, 35000)
        payload['coverage'] = coverage
        return payload

    def _stratified_events(
        self,
        event_types: List[str],
        per_group: int = 300,
        max_groups: int = 60,
    ) -> tuple:
        """Échantillon réparti sur les couples (source, agent) de la base.

        Chaque population reçoit le même quota, plafonné globalement. Le
        résultat porte sa couverture (`coverage`) pour qu'un compte ne soit
        jamais lu comme un total exhaustif.
        """
        agents = self.store.distinct_values("agent", event_types=event_types, limit=max_groups)
        # les événements sans agent restent visibles : ils sont échantillonnés
        # par source, sinon un producteur sans identité d'agent disparaît.
        sources = self.store.distinct_values("source", event_types=event_types, limit=max_groups)

        collected: Dict[str, Dict[str, Any]] = {}
        groups: List[Dict[str, Any]] = []

        for entry in agents:
            agent = entry["value"]
            batch = self.store.query(
                event_types=event_types, agent=agent, limit=per_group, order="desc"
            )
            groups.append({"agent": agent, "events_in_db": entry["events"], "sampled": len(batch)})
            for ev in batch:
                collected[ev["event_id"]] = ev

        for entry in sources:
            source = entry["value"]
            batch = self.store.query(
                event_types=event_types, source=source, limit=per_group, order="desc"
            )
            groups.append({"source": source, "events_in_db": entry["events"], "sampled": len(batch)})
            for ev in batch:
                collected[ev["event_id"]] = ev

        events = sorted(collected.values(), key=lambda e: e.get("timestamp") or 0)
        total_in_db = sum(g["events_in_db"] for g in groups)
        return events, {
            "strategy": "stratified par agent puis par source",
            "groups_sampled": len(groups),
            "per_group_limit": per_group,
            "events_sampled": len(events),
            "events_in_sampled_populations": total_in_db,
            "truncated": total_in_db > len(events),
            "window": f"{len(events)} événements répartis sur {len(groups)} populations",
            "note": (
                "Compte un usage observé sur un échantillon déclaré, jamais un "
                "total exhaustif ; aucune fonctionnalité n'est validée par ce compte."
            ),
            "groups": groups[:60],
        }

    def correlation_summary(self) -> Dict[str, Any]:
        return correlation.correlation_summary(self._all_events())

    # ── rapports ──────────────────────────────────────────────────────────
    def implementation_status(self) -> Dict[str, Any]:
        return {
            "components": [
                {"component": "LogParser (6 adapters)", "discovered": "oui",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Ajouter un adapter LM Studio natif si un fichier de log existe"},
                {"component": "EventStore (SQLite/WAL)", "discovered": "core/observability",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Rétention/compaction des vieux événements"},
                {"component": "Corrélation", "discovered": "code_lab.event_logger (ids)",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Ajouter model_call_id aux events debate_lab"},
                {"component": "Pipeline Graph", "discovered": "core/debate + code_lab",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Filtrer par session dans l'UI"},
                {"component": "Security Inspector", "discovered": "hermes-orchestrator/audit_log.jsonl",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Relier audit_log aux runs Code Lab via task_id"},
                {"component": "Performance Analyzer", "discovered": "captn_runtime experiences",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Instrumenter tokens/s dans code_lab events"},
                {"component": "Error Analyzer", "discovered": "runner.errors + logs",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Étendre les règles de classification"},
                {"component": "FeaturePoolBridge", "discovered": "feature_pool/",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Corriger les faux positifs BROKEN/BLOCKED (audit séparé)"},
                {"component": "Dashboard tab", "discovered": "experiments/ui/dashboard.html",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Graph interactif (SVG) au lieu de tableaux"},
                {"component": "Reports", "discovered": "docs/",
                 "implemented": "oui", "tested": "oui", "integrated": "oui",
                 "next_action": "Export PDF optionnel"},
            ],
            "generated_at": time.time(),
        }

    def generate_reports(self) -> Dict[str, str]:
        events = self.store.query(limit=20000)
        written = self.reports.generate(
            stats=self.store.stats(),
            events=events,
            graph=self.graph(),
            security=self.security(),
            performance=self.performance(),
            errors=self.errors(),
            features=self.features(),
            sources=self.sources(),
            implementation=self.implementation_status(),
        )
        self.last_ingest = self.last_ingest or {}
        return written

    def export(self) -> str:
        return self.reports.export_json({
            "stats": self.stats(),
            "graph": self.graph(),
            "security": self.security(),
            "performance": self.performance(),
            "errors": self.errors(),
            "features": self.features(),
        })


class PipelineApiMixin:
    """Mixin pour ``experiments.dashboard.DashboardHandler``.

    Fournit ``_pipeline_inspector()`` et les méthodes renvoyant des dicts.
    Le routage HTTP est ajouté côté handler.
    """

    _pipeline_singleton: Optional[PipelineInspector] = None
    _pipeline_lock = threading.Lock()

    def pipeline_inspector(self, auto_ingest: bool = False) -> PipelineInspector:
        cls = type(self)
        with cls._pipeline_lock:
            if cls._pipeline_singleton is None:
                cls._pipeline_singleton = PipelineInspector(
                    project_root=Path(__file__).resolve().parent.parent,
                    auto_ingest=auto_ingest,
                )
            return cls._pipeline_singleton

    # Méthodes appelées par le handler ────────────────────────────────────
    def pipeline_stats(self) -> Dict[str, Any]:
        return self.pipeline_inspector().stats()

    def pipeline_ingest(self, full_rescan: bool = False) -> Dict[str, Any]:
        return self.pipeline_inspector().ingest(full_rescan=full_rescan)

    def pipeline_sessions(self, limit: int = 200) -> Dict[str, Any]:
        return {"sessions": self.pipeline_inspector().sessions(limit=limit)}

    def pipeline_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        def _int(name: str, default: int) -> int:
            try:
                return int(params.get(name, default))
            except (TypeError, ValueError):
                return default
        filters = {
            "event_types": params.get("types") or None,
            "session_id": params.get("session") or None,
            "agent": params.get("agent") or None,
            "model": params.get("model") or None,
            "source": params.get("source") or None,
            "status": params.get("status") or None,
            "search": params.get("q") or None,
        }
        events = self.pipeline_inspector().events(
            limit=_int("limit", 200), offset=_int("offset", 0),
            order=params.get("order", "asc"), **filters,
        )
        return {"events": events, "count": len(events)}

    def pipeline_graph(self) -> Dict[str, Any]:
        return self.pipeline_inspector().graph()

    def pipeline_security(self) -> Dict[str, Any]:
        return self.pipeline_inspector().security()

    def pipeline_performance(self) -> Dict[str, Any]:
        return self.pipeline_inspector().performance()

    def pipeline_errors(self) -> Dict[str, Any]:
        return self.pipeline_inspector().errors()

    def pipeline_features(self) -> Dict[str, Any]:
        return self.pipeline_inspector().features()

    def pipeline_reports(self) -> Dict[str, Any]:
        return {"written": self.pipeline_inspector().generate_reports()}

    def pipeline_export(self) -> Dict[str, Any]:
        return {"path": self.pipeline_inspector().export()}
