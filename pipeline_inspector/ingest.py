"""Orchestration de l'ingestion incrémentale.

Une passe :
1. découvre les fichiers via les adapters ;
2. pour chaque fichier, reprend à l'offset enregistré (sauf si la taille a
   diminué ou si ``full_rescan`` est demandé) ;
3. normalise en événements, déduplique par ``event_id`` dans SQLite ;
4. enregistre l'état (taille, mtime, offset) pour la prochaine passe.

Aucune écriture dans les fichiers source. Aucune suppression.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_store import EventStore
from .log_parser import LogAdapter, ParseStats, default_adapters
from .schemas import PipelineEvent


@dataclass
class IngestResult:
    stats: ParseStats
    added: int
    skipped_files: int
    duration_s: float
    run_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = self.stats.to_dict()
        d.update({
            "events_added": self.added,
            "files_skipped": self.skipped_files,
            "duration_s": round(self.duration_s, 3),
            "run_id": self.run_id,
        })
        return d


class PipelineIngestor:
    """Ingestion incrémentale des logs vers ``EventStore``."""

    def __init__(
        self,
        root: str | Path,
        store: EventStore,
        adapters: Optional[List[LogAdapter]] = None,
        max_records_per_file: int = 200_000,
    ):
        self.root = Path(root)
        self.store = store
        self.adapters = adapters if adapters is not None else default_adapters(self.root)
        self.max_records_per_file = max_records_per_file

    # ── découverte ────────────────────────────────────────────────────────
    def discover(self) -> Dict[str, List[Path]]:
        found: Dict[str, List[Path]] = {}
        for adapter in self.adapters:
            try:
                paths = adapter.discover(self.root)
            except OSError:
                paths = []
            if paths:
                found[adapter.name] = paths
        return found

    def _relpath(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    # ── passe principale ──────────────────────────────────────────────────
    def run(
        self,
        full_rescan: bool = False,
        adapter_names: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> IngestResult:
        started = time.time()
        stats = ParseStats()
        added = 0
        skipped = 0
        run_id: Optional[int] = None
        if not dry_run:
            run_id = self.store.begin_ingest_run(started)

        for adapter in self.adapters:
            if adapter_names and adapter.name not in adapter_names:
                continue
            try:
                paths = adapter.discover(self.root)
            except OSError as exc:
                stats.errors.append(f"{adapter.name}: {exc}")
                continue
            stats.files_seen += len(paths)
            for path in paths:
                try:
                    st = path.stat()
                except OSError as exc:
                    stats.errors.append(f"{self._relpath(path)}: {exc}")
                    stats.files_skipped += 1
                    skipped += 1
                    continue

                relpath = self._relpath(path)
                state = None if full_rescan else self.store.get_ingest_state(relpath)
                offset = 0
                if state and st.st_size >= int(state.get("size") or 0):
                    # Un fichier précédemment tronqué par le plafond par-fichier
                    # ne doit PAS être considéré comme consommé : on reprend à
                    # l'offset enregistré pour ingérer la suite.
                    already_done = (
                        int(state.get("size") or 0) == st.st_size
                        and float(state.get("mtime") or 0) == st.st_mtime
                        and not int(state.get("truncated") or 0)
                    )
                    if already_done:
                        stats.files_skipped += 1
                        skipped += 1
                        continue
                    offset = int(state.get("offset") or 0)
                elif state and st.st_size < int(state.get("size") or 0):
                    # fichier tronqué/rotationné : relire depuis le début
                    offset = 0

                count = 0
                capped = False
                next_offset = offset
                last_line = int((state or {}).get("last_line") or 0)
                batch: List[PipelineEvent] = []
                try:
                    for ev, off in adapter.parse_file(path, relpath, offset):
                        batch.append(ev)
                        next_offset = off
                        last_line = max(last_line, ev.source_line)
                        count += 1
                        stats.records_read += 1
                        if len(batch) >= 2000:
                            if not dry_run:
                                added += self.store.insert_events(batch)
                            stats.events_emitted += len(batch)
                            batch = []
                        if count >= self.max_records_per_file:
                            capped = True
                            stats.errors.append(
                                f"{relpath}: plafond {self.max_records_per_file} atteint "
                                f"(reprise à l'offset {next_offset})"
                            )
                            break
                except Exception as exc:  # fichier illisible / encodage exotique
                    stats.errors.append(f"{relpath}: {type(exc).__name__}: {exc}")
                if batch:
                    if not dry_run:
                        added += self.store.insert_events(batch)
                    stats.events_emitted += len(batch)
                stats.files_parsed += 1
                stats.bytes_read += st.st_size
                if not dry_run and st.st_size >= 0:
                    self.store.set_ingest_state(
                        relpath, st.st_size, st.st_mtime, next_offset,
                        last_line, count, time.time(), truncated=capped,
                    )

        duration = time.time() - started
        if run_id is not None:
            self.store.end_ingest_run(run_id, stats.to_dict(), time.time())
        return IngestResult(
            stats=stats, added=added, skipped_files=skipped,
            duration_s=duration, run_id=run_id,
        )
