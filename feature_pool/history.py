"""FeaturePool history — audit trail and change tracking."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import Feature, HistoryEntry


class HistoryTracker:
    """Tracks changes to features over time."""

    def __init__(self, registry):
        self.registry = registry
        self._entries: Dict[str, List[HistoryEntry]] = {}

    def record(
        self,
        feature_id: str,
        action: str,
        actor: str = "system",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a history entry for a feature."""
        entry = HistoryEntry(
            timestamp=datetime.now(),
            action=action,
            actor=actor,
            details=details or {},
        )
        
        if feature_id not in self._entries:
            self._entries[feature_id] = []
        
        self._entries[feature_id].append(entry)
        
        # Also update the feature's own history
        feature = self.registry.get(feature_id)
        if feature:
            feature.add_history(action, actor, details)

    def get_history(self, feature_id: str) -> List[HistoryEntry]:
        """Get full history for a feature."""
        return self._entries.get(feature_id, []).copy()

    def get_changes_since(
        self, timestamp: datetime, feature_id: Optional[str] = None
    ) -> List[HistoryEntry]:
        """Get all changes since a timestamp."""
        if feature_id:
            entries = self._entries.get(feature_id, [])
        else:
            entries = []
            for feat_entries in self._entries.values():
                entries.extend(feat_entries)
        
        return [e for e in entries if e.timestamp >= timestamp]

    def get_recent_changes(
        self, hours: int = 24, feature_id: Optional[str] = None
    ) -> List[HistoryEntry]:
        """Get recent changes within a time window."""
        cutoff = datetime.now() - __import__("datetime").timedelta(hours=hours)
        return self.get_changes_since(cutoff, feature_id)

    def get_change_summary(self, feature_id: str) -> Dict[str, Any]:
        """Get summary of changes for a feature."""
        entries = self.get_history(feature_id)
        
        actions = {}
        for entry in entries:
            actions[entry.action] = actions.get(entry.action, 0) + 1
        
        return {
            "feature_id": feature_id,
            "total_changes": len(entries),
            "actions": actions,
            "first_seen": entries[0].timestamp.isoformat() if entries else None,
            "last_changed": entries[-1].timestamp.isoformat() if entries else None,
        }

    def export_log(self, path: Path) -> Path:
        """Export history to JSON file."""
        data = {
            "feature_id": feat_id,
            "changes": [e.to_dict() for e in entries],
        }
        for feat_id, entries in self._entries.items():
            data["features"][feat_id] = {
                "changes": [e.to_dict() for e in entries],
            }
        
        path.write_text(__import__("json").dumps(data, indent=2), encoding="utf-8")
        return path
