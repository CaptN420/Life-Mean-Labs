"""Journal d'usage runtime — observation réelle, pas déduction depuis les logs.

Pourquoi : le Feature Pool n'« observait » l'usage qu'en relisant des journaux
déjà ingérés. Résultat mesuré : 14 fonctionnalités observées sur 989, et un
chiffre qui dépendait de ce que l'ingestion avait bien voulu conserver.

Ce module enregistre ce qui **s'exécute réellement** : à chaque tâche, le runner
écrit une ligne par worker et par outil effectivement utilisés. Le fichier est
append-only (JSONL), borné en lecture, et chaque enregistrement porte son
expérience, sa tâche et son horodatage — de quoi remonter à la preuve.

Rien n'est inventé : une ligne n'est écrite que si l'exécution a eu lieu. Un
échec d'écriture est journalisé et jamais propagé à l'exécution.

Convention sur ``ok`` : ``None`` signifie « exécuté, résultat consigné
ailleurs » (les traces `ValidationRule` portent le verdict). Un booléen n'est
écrit que lorsqu'il est réellement connu — on ne fabrique pas un succès.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("experiments.usage_recorder")

SCHEMA = "life-mean-usage/1"


def usage_dir() -> Path:
    env = os.environ.get("LIFE_MEAN_USAGE_DIR")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "data" / "usage"


class FeatureUsageRecorder:
    """Append-only JSONL recorder of runtime usage."""

    def __init__(self, directory: Optional[Path] = None, filename: str = "feature_usage.jsonl") -> None:
        self.directory = Path(directory) if directory else usage_dir()
        self.path = self.directory / filename
        self.last_error: str = ""
        self._written = 0

    # ── écriture ───────────────────────────────────────────────────────────
    def record(
        self,
        kind: str,
        name: str,
        experiment_id: str = "",
        task_id: str = "",
        ok: Optional[bool] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Ajoute une ligne d'usage. Renvoie False (et explique) en cas d'échec."""
        if not name:
            self.last_error = "empty name"
            return False
        entry = {
            "schema": SCHEMA,
            "timestamp": time.time(),
            "kind": kind,
            "name": name,
            "experiment_id": experiment_id,
            "task_id": task_id,
            "ok": ok,
        }
        if extra:
            entry["extra"] = extra
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
            self._written += 1
            self.last_error = ""
            return True
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.error("could not append usage record to %s: %s", self.path, exc)
            return False

    # ── lecture ────────────────────────────────────────────────────────────
    def read(self, limit: int = 50000) -> List[Dict[str, Any]]:
        """Dernières ``limit`` lignes valides (les lignes abîmées sont ignorées)."""
        if not self.path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        skipped = 0
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        skipped += 1
                        continue
                    if item.get("schema") != SCHEMA or not item.get("name"):
                        skipped += 1
                        continue
                    entries.append(item)
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.error("could not read %s: %s", self.path, exc)
            return []
        if skipped:
            logger.warning("ignored %d unreadable usage line(s) in %s", skipped, self.path)
        return entries[-limit:]

    def describe(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "records_written_this_session": self._written,
            "last_error": self.last_error,
        }
