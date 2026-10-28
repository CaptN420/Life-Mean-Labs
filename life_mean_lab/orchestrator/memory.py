"""CognitiveMemory — 4-level structured memory for orchestration.

Levels:
  WORKING   — temporary context of the current task (evacuated after completion)
  PROJECT   — architecture, conventions, dependencies, technical decisions
  EPISODIC  — attempts, errors, corrections from previous runs
  PROCEDURAL — strategies that proved effective

Design rules:
  - Retrieval is selective and bounded by context budget.
  - Entries have provenance (source run_id) and expiration.
  - Obsolete information is invalidated, not just hidden.
  - LLM outputs are never considered automatically reliable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Life_mean.Orchestrator.Memory")


# ── Memory entry ─────────────────────────────────────────────────────────────


@dataclass
class MemoryEntry:
    """A single memory entry with metadata for lifecycle management."""
    key: str
    category: str  # "working" | "project" | "episodic" | "procedural"
    content: str
    source_run_id: str = ""
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    expires_at: Optional[float] = None  # None = permanent (project/procedural)
    tags: List[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        self.accessed_at = time.time()
        self.access_count += 1


# ── Memory level stores ──────────────────────────────────────────────────────


class CognitiveMemory:
    """4-level structured memory for the cognitive orchestrator.

    Each level has different lifetime and retrieval characteristics:
      - Working:   transient, cleared after task completion
      - Project:   persistent, updated incrementally
      - Episodic:  append-only, pruned by age/count
      - Procedural: persistent, validated before reuse
    """

    # Default expiration for working memory (1 hour).
    _WORKING_TTL_SECONDS = 3600
    # Max episodic entries before pruning.
    _EPISODIC_MAX = 500
    # Max tokens to retrieve in a single recall.
    _RETRIEVAL_TOKEN_BUDGET = 2048

    def __init__(self, project_name: str = "default") -> None:
        self.project_name = project_name
        self._stores: Dict[str, List[MemoryEntry]] = {
            "working": [],
            "project": [],
            "episodic": [],
            "procedural": [],
        }

    # ── Write ──────────────────────────────────────────────────────────────

    def store(self, category: str, key: str, content: str,
              source_run_id: str = "", tags: Optional[List[str]] = None) -> None:
        """Store a memory entry in the specified level."""
        if category not in self._stores:
            logger.warning("Unknown memory category '%s', storing as 'project'", category)
            category = "project"

        # Check for duplicate key in same category (overwrite with newer content).
        existing = self._find(key, category)
        if existing is not None:
            existing.content = content
            existing.tags = tags or []
            existing.touch()
            return

        entry = MemoryEntry(
            key=key,
            category=category,
            content=content,
            source_run_id=source_run_id,
            tags=tags or [],
        )
        # Working memory expires after TTL.
        if category == "working":
            entry.expires_at = time.time() + self._WORKING_TTL_SECONDS
        self._stores[category].append(entry)
        logger.debug("Stored memory [%s] key='%s'", category, key)

    # ── Read ───────────────────────────────────────────────────────────────

    def recall(self, category: str, query: str = "",
               max_tokens: int = _RETRIEVAL_TOKEN_BUDGET) -> List[MemoryEntry]:
        """Recall relevant entries from a memory level.

        Returns entries sorted by recency and access count, bounded by tokens.
        """
        if category not in self._stores:
            return []

        # Expire old entries.
        self._prune(category)

        entries = self._stores[category]
        if not entries:
            return []

        # Filter by query (simple substring match on content/keys/tags).
        if query:
            matched = []
            query_lower = query.lower()
            for e in entries:
                if (query_lower in e.key.lower() or
                    query_lower in e.content.lower() or
                    any(query_lower in t.lower() for t in e.tags)):
                    matched.append(e)
            entries = matched or entries

        # Sort by recency + access count.
        sorted_entries = sorted(
            entries,
            key=lambda e: (e.accessed_at, e.access_count),
            reverse=True,
        )

        # Bound by token budget.
        result = []
        token_count = 0
        for e in sorted_entries:
            est_tokens = len(e.content.split()) * 1.3
            if token_count + est_tokens > max_tokens:
                break
            e.touch()
            result.append(e)
            token_count += est_tokens

        return result

    def recall_all(self, category: str) -> List[MemoryEntry]:
        """Recall all entries from a level (no query filter, no budget)."""
        if category not in self._stores:
            return []
        self._prune(category)
        return sorted(
            self._stores[category],
            key=lambda e: e.accessed_at,
            reverse=True,
        )

    # ── Project memory helpers ─────────────────────────────────────────────

    def store_architecture_decision(self, decision: str, rationale: str,
                                    source_run_id: str = "") -> None:
        """Convenience: store a project architecture decision."""
        content = f"DECISION: {decision}\nRATIONALE: {rationale}"
        self.store("project", f"arch-{len(self._stores['project'])+1}", content,
                   source_run_id=source_run_id, tags=["architecture", "decision"])

    def store_convention(self, convention: str, source_run_id: str = "") -> None:
        """Convenience: store a project convention."""
        self.store("project", f"conv-{len(self._stores['project'])+1}", convention,
                   source_run_id=source_run_id, tags=["convention"])

    def store_episode(self, run_id: str, outcome: str, error: Optional[str] = None,
                      strategy_used: str = "") -> None:
        """Convenience: store an episodic entry from a completed run."""
        content = f"RUN {run_id}: {outcome}"
        if error:
            content += f"\nERROR: {error}"
        if strategy_used:
            content += f"\nSTRATEGY: {strategy_used}"
        self.store("episodic", f"ep-{run_id}", content, source_run_id=run_id,
                   tags=["episode", outcome.lower()])

    def store_proven_strategy(self, strategy: str, success_rate: float,
                              context: str = "") -> None:
        """Convenience: store a procedural memory about a successful strategy."""
        content = f"STRATEGY '{strategy}': success_rate={success_rate:.2%}"
        if context:
            content += f"\nCONTEXT: {context}"
        self.store("procedural", f"proc-{strategy}", content,
                   tags=["procedural", "strategy"])

    # ── Working memory lifecycle ───────────────────────────────────────────

    def clear_working(self) -> int:
        """Clear all working memory. Returns count of entries cleared."""
        count = len(self._stores["working"])
        self._stores["working"] = []
        logger.debug("Cleared %d working memory entries", count)
        return count

    # ── Utilities ──────────────────────────────────────────────────────────

    def _find(self, key: str, category: str) -> Optional[MemoryEntry]:
        for e in self._stores.get(category, []):
            if e.key == key:
                return e
        return None

    def _prune(self, category: str) -> None:
        """Remove expired entries and cap episodic count."""
        if category not in self._stores:
            return
        before = len(self._stores[category])
        if category == "episodic":
            # Keep only the newest _EPISODIC_MAX entries.
            sorted_entries = sorted(
                self._stores[category],
                key=lambda e: e.created_at,
                reverse=True,
            )
            self._stores[category] = sorted_entries[:self._EPISODIC_MAX]
        else:
            self._stores[category] = [
                e for e in self._stores[category] if not e.is_expired
            ]
        pruned = before - len(self._stores[category])
        if pruned > 0:
            logger.debug("Pruned %d expired entries from '%s'", pruned, category)

    def summary(self) -> Dict[str, Any]:
        """Return a compact summary of memory state."""
        return {
            level: {
                "count": len(entries),
                "keys": [e.key for e in entries[:5]],
            }
            for level, entries in self._stores.items()
        }
