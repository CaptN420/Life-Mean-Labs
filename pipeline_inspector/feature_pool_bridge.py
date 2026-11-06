"""Pont Pipeline Inspector ↔ Feature Pool.

Objectif : relier les événements observés aux fonctionnalités enregistrées,
sans jamais modifier un statut du Feature Pool.

La fréquence d'utilisation n'est PAS une preuve de qualité : elle est
présentée séparément des statuts de validation existants.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def normalize_name(name: str) -> str:
    """Normalise pour comparer 'MathValidationWorker' / 'math_validation_worker'."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


class FeaturePoolBridge:
    """Lecture seule du Feature Pool + comptage d'usage observé."""

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root)
        self._features: Dict[str, Dict[str, Any]] = {}
        self._index: Dict[str, str] = {}
        self.source: str = "none"
        self.generated_at: Optional[str] = None
        self.load()

    # ── chargement ─────────────────────────────────────────────────────────
    def load(self) -> int:
        """Charge le rapport le plus RÉCENT parmi les emplacements connus.

        Les exports du Feature Pool s'appellent historiquement
        ``.feature_pool_report.json`` ou ``feature_pool_report.json`` selon la
        version ; un ancien fichier pouvait donc masquer un rapport fraîchement
        régénéré (statuts BROKEN/BLOCKED périmés). On ne supprime rien : on
        retient simplement le fichier modifié le plus récemment.
        """
        candidates = [
            self.root / ".feature_pool_report.json",
            self.root / "feature_pool_report.json",
            self.root / "feature_pool_full_report.json",
            self.root / "feature_pool" / "registry.json",
        ]
        candidates = [c for c in candidates if c.exists()]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates:
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            feats = data.get("features") if isinstance(data, dict) else data
            if not isinstance(feats, list):
                continue
            self._features.clear()
            self._index.clear()
            for f in feats:
                if not isinstance(f, dict) or not f.get("id"):
                    continue
                self._features[f["id"]] = f
                self._index[normalize_name(f.get("name") or f["id"])] = f["id"]
            self.source = str(candidate.relative_to(self.root))
            self.generated_at = datetime.fromtimestamp(
                candidate.stat().st_mtime, tz=timezone.utc
            ).isoformat(timespec="seconds")
            return len(self._features)
        return 0

    # ── mapping ────────────────────────────────────────────────────────────
    def map_entity(self, entity: Optional[str]) -> Optional[str]:
        if not entity:
            return None
        key = normalize_name(entity)
        if key in self._index:
            return self._index[key]
        # Tolérance : suffixe/préfixe évident (worker/agent). Les DEUX côtés
        # doivent être assez longs : sans le garde sur `candidate_key`, une
        # fonctionnalité nommée « C » (ou tout nom court) était retournée pour
        # n'importe quelle entité la contenant — `math_gcd` comptait comme usage
        # de la feature « C ».
        for candidate_key, fid in self._index.items():
            if (len(key) >= 6 and len(candidate_key) >= 6
                    and (key in candidate_key or candidate_key in key)):
                return fid
        return None

    def usage(
        self,
        events: Iterable[Dict[str, Any]],
        runtime_records: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        per_feature: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "events": 0, "ok": 0, "fail": 0,
            "first_seen": None, "last_seen": None,
            "observed_via": set(), "event_types": set(),
        })
        unmapped = defaultdict(int)
        total_events = 0
        for ev in events:
            total_events += 1
            entities = []
            if ev.get("agent"):
                entities.append(("agent", ev["agent"]))
            meta = ev.get("metadata") or {}
            if meta.get("tool"):
                entities.append(("tool", meta["tool"]))
            if meta.get("role"):
                entities.append(("role", meta["role"]))
            for kind, name in entities:
                fid = self.map_entity(name)
                if not fid:
                    unmapped[f"{kind}:{name}"] += 1
                    continue
                b = per_feature[fid]
                b["events"] += 1
                b["observed_via"].add(kind)
                b["event_types"].add(ev.get("event_type"))
                if ev.get("ok") is True:
                    b["ok"] += 1
                elif ev.get("ok") is False:
                    b["fail"] += 1
                ts = ev.get("timestamp")
                if ts is not None:
                    if b["first_seen"] is None or ts < b["first_seen"]:
                        b["first_seen"] = ts
                    if b["last_seen"] is None or ts > b["last_seen"]:
                        b["last_seen"] = ts

        # ── usage runtime (journal d'exécution) ──────────────────────────
        # Une ligne = un composant qui a réellement tourné. C'est une preuve
        # d'usage plus directe que la relecture de logs, et elle ne dépend pas
        # de ce que l'ingestion a conservé.
        runtime_count = 0
        runtime_ok = 0
        runtime_fail = 0
        for rec in runtime_records or []:
            runtime_count += 1
            name = str(rec.get("name") or "")
            fid = self.map_entity(name) if name else None
            if not fid:
                unmapped[f"runtime:{name}"] += 1
                continue
            b = per_feature[fid]
            b["events"] += 1  # une exécution compte comme un événement d'usage
            b["observed_via"].add("runtime")
            b["event_types"].add("RUNTIME_USAGE")
            if rec.get("ok") is True:
                b["ok"] += 1
                runtime_ok += 1
            elif rec.get("ok") is False:
                b["fail"] += 1
                runtime_fail += 1
            ts = rec.get("timestamp")
            if ts is not None:
                if b["first_seen"] is None or ts < b["first_seen"]:
                    b["first_seen"] = ts
                if b["last_seen"] is None or ts > b["last_seen"]:
                    b["last_seen"] = ts

        rows = []
        for fid, b in per_feature.items():
            feat = self._features.get(fid, {})
            rows.append({
                "feature_id": fid,
                "name": feat.get("name"),
                "category": feat.get("category"),
                "status": feat.get("status"),                 # statut existant, inchangé
                "integration_status": feat.get("integration_status"),
                "observed_events": b["events"],
                "observed_ok": b["ok"],
                "observed_fail": b["fail"],
                "observed_via": sorted(b["observed_via"]),
                "event_types": sorted(t for t in b["event_types"] if t),
                "first_seen": b["first_seen"],
                "last_seen": b["last_seen"],
                "test_paths": feat.get("test_paths") or [],
                "locations": [loc.get("path") for loc in (feat.get("locations") or [])],
                "note": "Usage observé ≠ validation. Statut Feature Pool non modifié.",
            })
        rows.sort(key=lambda r: -r["observed_events"])
        return {
            "features_loaded": len(self._features),
            "feature_pool_source": self.source,
            "features_observed": len(rows),
            "features_not_observed": max(0, len(self._features) - len(rows)),
            "total_events_scanned": total_events,
            "usage_sources": {
                "logs": {
                    "events_scanned": total_events,
                    "features_observed": sum(1 for b in per_feature.values() if "agent" in b["observed_via"] or "tool" in b["observed_via"] or "role" in b["observed_via"]),
                },
                "runtime": {
                    "records": runtime_count,
                    "ok": runtime_ok,
                    "fail": runtime_fail,
                    "features_observed": sum(1 for b in per_feature.values() if "runtime" in b["observed_via"]),
                },
            },
            "rows": rows[:300],
            "unmapped_entities": sorted(
                [{"entity": k, "events": v} for k, v in unmapped.items()],
                key=lambda x: -x["events"],
            )[:100],
            "caveat": (
                "Le pont ne valide aucune fonctionnalité. Il constate une utilisation. "
                "Un événement réussi n'est pas une preuve de qualité."
            ),
        }

    def inventory(self) -> List[Dict[str, Any]]:
        return [
            {
                "feature_id": fid,
                "name": f.get("name"),
                "category": f.get("category"),
                "status": f.get("status"),
                "integration_status": f.get("integration_status"),
            }
            for fid, f in self._features.items()
        ]
