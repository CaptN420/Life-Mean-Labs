"""Génération des rapports Markdown — jamais d'écrasement.

Chaque exécution crée un dossier horodaté sous ``reports/pipeline/``.
Si un fichier du même nom existe déjà (même seconde), un suffixe est ajouté.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPORTS = [
    "PIPELINE_ARCHITECTURE.md",
    "PIPELINE_EVENT_INVENTORY.md",
    "PIPELINE_SECURITY_REPORT.md",
    "PIPELINE_PERFORMANCE_REPORT.md",
    "PIPELINE_ERRORS.md",
    "FEATURE_POOL_PIPELINE_MAP.md",
    "IMPLEMENTATION_STATUS.md",
]


def _now_tag() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def _table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return "_Aucune donnée observée._\n"
    head = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join(["---"] * len(columns)) + "|"
    body = []
    for row in rows:
        cells = []
        for c in columns:
            value = row.get(c)
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value)
            cells.append(str(value if value is not None else "—").replace("|", "/"))
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep] + body) + "\n"


class ReportGenerator:
    """Assemble les rapports à partir des analyses déjà calculées."""

    def __init__(self, project_root: str | Path, out_dir: Optional[str | Path] = None):
        self.root = Path(project_root)
        # Priorité : argument explicite > variable d'environnement > dossier
        # inscriptible. Le conteneur monte /app en lecture seule : on écrit donc
        # sous ``data/`` (volume Docker persistant), jamais à la racine du code.
        env_dir = os.environ.get("PIPELINE_REPORTS_DIR")
        if out_dir:
            self.out_dir = Path(out_dir)
        elif env_dir:
            self.out_dir = Path(env_dir)
        else:
            self.out_dir = self.root / "data" / "pipeline_reports"

    def generate(
        self,
        stats: Dict[str, Any],
        events: List[Dict[str, Any]],
        graph: Dict[str, Any],
        security: Dict[str, Any],
        performance: Dict[str, Any],
        errors: Dict[str, Any],
        features: Dict[str, Any],
        sources: Dict[str, Any],
        implementation: Dict[str, Any],
    ) -> Dict[str, str]:
        run_dir = self.out_dir / _now_tag()
        run_dir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, str] = {}

        written["PIPELINE_ARCHITECTURE.md"] = self._architecture(
            run_dir, stats, graph, sources, implementation
        )
        written["PIPELINE_EVENT_INVENTORY.md"] = self._inventory(run_dir, stats, events)
        written["PIPELINE_SECURITY_REPORT.md"] = self._security(run_dir, security)
        written["PIPELINE_PERFORMANCE_REPORT.md"] = self._performance(run_dir, performance)
        written["PIPELINE_ERRORS.md"] = self._errors(run_dir, errors)
        written["FEATURE_POOL_PIPELINE_MAP.md"] = self._features(run_dir, features)
        written["IMPLEMENTATION_STATUS.md"] = self._status(run_dir, implementation, stats)
        return written

    # ── helpers ────────────────────────────────────────────────────────────
    def _write(self, run_dir: Path, name: str, body: str) -> str:
        path = _unique(run_dir / name)
        header = (
            f"<!-- généré par pipeline_inspector le "
            f"{datetime.now(tz=timezone.utc).isoformat()} -->\n"
            "<!-- données locales uniquement — secrets masqués -->\n\n"
        )
        path.write_text(header + body, encoding="utf-8")
        return str(path)

    # ── documents ──────────────────────────────────────────────────────────
    def _architecture(self, run_dir, stats, graph, sources, impl) -> str:
        lines = [
            "# Pipeline Architecture (observée)\n",
            "## 1. Hypothèse vs réalité\n",
            "Le schéma de la spécification est une hypothèse. Le graphe ci-dessous "
            "est construit uniquement à partir des transitions réellement observées.\n",
            "```\n" + " → ".join(graph.get("hypothesis_stages", [])) + "\n```\n",
            "### Étapes de l'hypothèse jamais observées\n",
            *[f"- `{s}`" for s in graph.get("hypothesis_only", [])],
            "\n### Étapes observées hors hypothèse\n",
            *[f"- `{s}`" for s in graph.get("observed_not_in_hypothesis", [])],
            "\n## 2. Nœuds observés\n",
            _table(graph.get("nodes", []), ["id", "label", "count", "ok", "fail", "sources"]),
            "\n## 3. Transitions observées (top 40)\n",
            _table(graph.get("edges", [])[:40], ["from", "to", "count"]),
            "\n## 4. Sources de logs\n",
            _table(
                [{"source": k, "files": v.get("files"), "description": v.get("description")}
                 for k, v in sources.items()],
                ["source", "files", "description"],
            ),
            "\n## 5. État d'implémentation\n",
            _table(impl.get("components", []), ["component", "discovered", "implemented", "tested", "integrated"]),
            f"\n**Total événements analysés :** {stats.get('total_events', 0)}  \n",
            f"**Sessions :** {stats.get('sessions', 0)}\n",
        ]
        return self._write(run_dir, "PIPELINE_ARCHITECTURE.md", "\n".join(lines))

    def _inventory(self, run_dir, stats, events) -> str:
        by_type: Dict[str, int] = stats.get("by_type", {}) or {}
        rows = [{"event_type": k, "count": v} for k, v in sorted(by_type.items(), key=lambda x: -x[1])]
        return self._write(
            run_dir, "PIPELINE_EVENT_INVENTORY.md",
            "# Pipeline Event Inventory\n\n"
            f"Événements indexés : **{stats.get('total_events', 0)}**\n\n"
            "## Répartition par type\n\n" + _table(rows, ["event_type", "count"]) +
            "\n## Répartition par source\n\n" +
            _table([{"source": k, "count": v} for k, v in (stats.get("by_source") or {}).items()],
                   ["source", "count"]) +
            "\n## Derniers événements\n\n" +
            _table(events[-30:], ["timestamp_iso", "event_type", "source", "agent", "status"]),
        )

    def _security(self, run_dir, security) -> str:
        lines = [
            "# Pipeline Security Report\n",
            "> Une décision `APPROVE` n'est pas une preuve de sûreté.\n",
            f"- Décisions observées : **{security.get('total_decisions', 0)}**",
            f"- Exécutions observées : **{security.get('executions_observed', 0)}**",
            f"- Incohérences détectées : **{security.get('inconsistency_count', 0)}**",
            f"- Décisions sans clé de corrélation : **{security.get('decisions_without_correlation_key', 0)}**\n",
            "## Décisions par type\n",
            _table([{"decision": k, "count": v} for k, v in (security.get("by_decision") or {}).items()],
                   ["decision", "count"]),
            "\n## Incohérences\n",
            _table(security.get("inconsistencies", [])[:50], ["kind", "key", "confidence", "detail"]),
            "\n## Chronologie (200 premières)\n",
            _table(security.get("timeline", [])[:200],
                   ["timestamp", "decision", "operation", "component", "correlation"]),
            f"\n_{security.get('caveat', '')}_\n",
        ]
        return self._write(run_dir, "PIPELINE_SECURITY_REPORT.md", "\n".join(lines))

    def _performance(self, run_dir, perf) -> str:
        models = perf.get("models", {})
        rows = [dict(model=k, **v) for k, v in models.items()]
        return self._write(
            run_dir, "PIPELINE_PERFORMANCE_REPORT.md",
            "# Pipeline Performance Report\n\n"
            "## Métriques modèle (mesurées uniquement)\n\n" +
            _table(rows, ["model", "calls", "ok", "failed", "tokens_input", "tokens_output",
                          "latency_ms_avg", "tokens_per_second"]) +
            "\n## Métriques pipeline\n\n" +
            _table([{"metric": k, "value": v} for k, v in (perf.get("pipeline") or {}).items()],
                   ["metric", "value"]),
        )

    def _errors(self, run_dir, errors) -> str:
        return self._write(
            run_dir, "PIPELINE_ERRORS.md",
            "# Pipeline Errors\n\n"
            f"Total erreurs observées : **{errors.get('total_errors', 0)}**\n\n"
            "## Par classification\n\n" +
            _table([{"code": k, "count": v} for k, v in (errors.get("by_code") or {}).items()],
                   ["code", "count"]) +
            "\n## Recommandations (non appliquées)\n\n" +
            "\n".join(f"- {r}" for r in errors.get("recommendations", [])) +
            "\n\n## Échantillons\n\n" +
            _table(errors.get("samples", []), ["timestamp", "code", "source", "message"]),
        )

    def _features(self, run_dir, features) -> str:
        return self._write(
            run_dir, "FEATURE_POOL_PIPELINE_MAP.md",
            "# Feature Pool ↔ Pipeline Map\n\n"
            f"- Features chargées : **{features.get('features_loaded', 0)}** "
            f"(`{features.get('feature_pool_source')}`)\n"
            f"- Features observées dans les logs : **{features.get('features_observed', 0)}**\n"
            f"- Non observées : **{features.get('features_not_observed', 0)}**\n\n"
            "> Usage observé ≠ validation. Aucun statut Feature Pool n'a été modifié.\n\n"
            "## Détail\n\n" +
            _table(features.get("rows", []),
                   ["feature_id", "name", "status", "observed_events", "observed_ok",
                    "observed_fail", "observed_via"]) +
            "\n## Entités non mappées (top 40)\n\n" +
            _table(features.get("unmapped_entities", [])[:40], ["entity", "events"]),
        )

    def _status(self, run_dir, impl, stats) -> str:
        rows = impl.get("components", [])
        lines = [
            "# Implementation Status\n",
            f"_Généré le {datetime.now(tz=timezone.utc).isoformat()}_\n",
            "| Composant | Découvert | Implémenté | Testé | Intégré | Action suivante |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                f"| {r.get('component','')} | {r.get('discovered','—')} | "
                f"{r.get('implemented','—')} | {r.get('tested','—')} | "
                f"{r.get('integrated','—')} | {r.get('next_action','—')} |"
            )
        lines += [
            "\n## Chiffres de la passe\n",
            f"- Sessions analysées : **{stats.get('sessions', 0)}**",
            f"- Événements identifiés : **{stats.get('total_events', 0)}**",
        ]
        return self._write(run_dir, "IMPLEMENTATION_STATUS.md", "\n".join(lines))

    # ── export JSON ────────────────────────────────────────────────────────
    def export_json(self, payload: Dict[str, Any], name: str = "pipeline_export.json") -> str:
        run_dir = self.out_dir / _now_tag()
        run_dir.mkdir(parents=True, exist_ok=True)
        path = _unique(run_dir / name)
        path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        return str(path)
