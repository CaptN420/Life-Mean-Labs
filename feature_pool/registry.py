"""FeaturePool registry — central storage and query interface."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from .schemas import Feature, FeatureCategory, FeatureStatus, IntegrationStatus


class FeatureRegistry:
    """Central registry - single source of truth for all features."""

    def __init__(self, storage_path: Optional[Path] = None):
        self._features: Dict[str, Feature] = {}
        self._storage_path = storage_path

    @property
    def count(self) -> int:
        """Total number of registered features."""
        return len(self._features)

    @property
    def all_features(self) -> List[Feature]:
        """Return all features."""
        return list(self._features.values())

    def add(self, feature: Feature) -> None:
        """Add or update a feature in the registry."""
        self._features[feature.id] = feature

    def get(self, feature_id: str) -> Optional[Feature]:
        """Get a feature by ID."""
        return self._features.get(feature_id)

    def remove(self, feature_id: str) -> bool:
        """Remove a feature by ID. Returns True if removed."""
        if feature_id in self._features:
            del self._features[feature_id]
            return True
        return False

    # --- Search ---

    def search(self, query: str) -> List[Feature]:
        """Search features by name, category, or metadata."""
        query_lower = query.lower()
        results = []
        for feature in self._features.values():
            if (query_lower in feature.name.lower() or
                query_lower in feature.category.value or
                any(query_lower in v.lower() for v in feature.metadata.values())):
                results.append(feature)
        return results

    def filter_by_status(self, status: FeatureStatus) -> List[Feature]:
        """Filter features by technical status."""
        return [f for f in self._features.values() if f.status == status]

    def filter_by_integration_status(self, status: IntegrationStatus) -> List[Feature]:
        """Filter features by integration status."""
        return [f for f in self._features.values() if f.integration_status == status]

    def filter_by_category(self, category: FeatureCategory) -> List[Feature]:
        """Filter features by category."""
        return [f for f in self._features.values() if f.category == category]

    def filter_by_source(self, is_legacy: bool) -> List[Feature]:
        """Filter features by source (legacy vs modern)."""
        return [f for f in self._features.values() if f.is_legacy == is_legacy]

    def filter_ready_for_integration(self) -> List[Feature]:
        """Get features that are validated and ready for integration."""
        return [
            f for f in self._features.values()
            if f.status == FeatureStatus.VALIDATED and
               f.integration_status == IntegrationStatus.NOT_STARTED
        ]

    # --- Dependencies ---

    def get_dependencies(self, feature_id: str) -> Set[str]:
        """Get dependencies of a feature."""
        feature = self._features.get(feature_id)
        if feature:
            return feature.dependencies.copy()
        return set()

    def get_dependents(self, feature_id: str) -> Set[str]:
        """Get features that depend on this feature."""
        dependents = set()
        for fid, feat in self._features.items():
            if feature_id in feat.dependencies:
                dependents.add(fid)
        return dependents

    def get_orphans(self) -> List[str]:
        """Find features with no dependencies and no dependents."""
        orphans = []
        for fid, feat in self._features.items():
            if not feat.dependencies and not self.get_dependents(fid):
                orphans.append(fid)
        return orphans

    # --- Persistence ---

    def save(self, path: Optional[Path] = None) -> Path:
        """Save registry to JSON file."""
        storage_path = path or self._storage_path
        if not storage_path:
            storage_path = Path(__file__).parent / "feature_pool.db.json"
        
        data = {
            "features": [f.to_dict() for f in self._features.values()],
            "saved_at": str(Path(storage_path).stat().st_mtime if storage_path.exists() else 0),
        }
        
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return storage_path

    def load(self, path: Optional[Path] = None) -> Path:
        """Load registry from JSON file."""
        storage_path = path or self._storage_path
        if not storage_path or not storage_path.exists():
            return storage_path
        
        data = json.loads(storage_path.read_text(encoding="utf-8"))
        self._features = {
            f["id"]: Feature.from_dict(f)
            for f in data.get("features", [])
        }
        return storage_path

    # --- Statistics ---

    def get_statistics(self) -> Dict[str, Any]:
        """Get summary statistics."""
        stats = {
            "total": self.count,
            "by_status": {},
            "by_category": {},
            "by_source": {"legacy": 0, "modern": 0},
            "with_tests": 0,
            "ready_for_integration": 0,
        }
        
        for feature in self._features.values():
            # Status counts
            stats["by_status"][feature.status.value] = \
                stats["by_status"].get(feature.status.value, 0) + 1
            
            # Category counts
            stats["by_category"][feature.category.value] = \
                stats["by_category"].get(feature.category.value, 0) + 1
            
            # Source counts
            if feature.is_legacy:
                stats["by_source"]["legacy"] += 1
            else:
                stats["by_source"]["modern"] += 1
            
            # Test coverage
            if feature.has_tests:
                stats["with_tests"] += 1
            
            # Integration readiness
            if (feature.status == FeatureStatus.VALIDATED and
                feature.integration_status == IntegrationStatus.NOT_STARTED):
                stats["ready_for_integration"] += 1
        
        return stats

    def export_csv(self, path: Path) -> Path:
        """Export features to CSV format."""
        lines = ["ID", "Nom", "Source", "Catégorie", "Capacité", "Statut", 
                 "Intégration", "Dépendances", "Tests", "Action recommandée"]
        
        for feature in sorted(self._features.values(), key=lambda f: f.name):
            deps = "; ".join(sorted(feature.dependencies)) if feature.dependencies else ""
            tests = "; ".join(feature.test_paths) if feature.test_paths else ""
            
            lines.append(
                f"{feature.id}|{feature.name}|{feature.source}|{feature.category.value}|"
                f"{feature.status.value}|{feature.integration_status.value}|{deps}|{tests}|{feature.recommended_action}"
            )
        
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
