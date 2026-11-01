"""FeaturePool — Centralized Feature Registry for Life_mean.

Transforms the feature inventory into a living, persistent,
queryable, and extensible registry.

Usage:
    from feature_pool import FeaturePool
    
    pool = FeaturePool(project_root="/path/to/project")
    pool.discover()
    
    # Query features
    features = pool.registry.search("agent")
    ready = pool.registry.filter_ready_for_integration()
    
    # Get analysis
    plan = pool.planner.plan_integration(feature_id)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .analyzer import FeatureAnalyzer
from .compatibility import CompatibilityChecker
from .dependencies import DependencyGraph
from .history import HistoryTracker
from .integration_planner import IntegrationPlanner
from .registry import FeatureRegistry
from .scanner import FeatureScanner
from .schemas import Feature, FeatureCategory, FeatureStatus


class FeaturePool:
    """Main entry point for FeaturePool functionality."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.registry = FeatureRegistry()
        self.scanner = FeatureScanner(str(self.project_root))
        self.analyzer = FeatureAnalyzer(self.registry)
        self.dependencies = DependencyGraph(self.registry)
        self.compatibility = CompatibilityChecker(self.registry)
        self.history = HistoryTracker(self.registry)
        self.planner = IntegrationPlanner(
            self.registry, self.analyzer, self.compatibility
        )

    def discover(self) -> int:
        """Discover all features in the project.
        
        Returns:
            Number of features discovered.
        """
        discoveries = self.scanner.discover()
        
        for feature in discoveries.values():
            self.registry.add(feature)
            self.history.record(
                feature.id,
                "DISCOVERED",
                actor="scanner",
                details={"source": feature.source},
            )
        
        return len(discoveries)

    def analyze_all(self) -> int:
        """Analyze all discovered features.
        
        Returns:
            Number of features analyzed.
        """
        count = 0
        for feature in self.registry.all_features:
            if feature.status == FeatureStatus.DISCOVERED:
                self.analyzer.analyze(feature)
                self.history.record(
                    feature.id,
                    "ANALYZED",
                    actor="analyzer",
                )
                count += 1
        
        # Build dependency graph
        self.dependencies.build()
        
        return count

    def validate_all(self) -> int:
        """Validate all analyzed features.
        
        Returns:
            Number of features validated.
        """
        count = 0
        for feature in list(self.registry.all_features):
            if feature.status == FeatureStatus.ANALYZED:
                readiness = self.analyzer.assess_readiness(feature)
                if readiness == "READY":
                    # « READY » = le code parse et ses dépendances existent.
                    # Cela ne prouve pas qu'il FONCTIONNE : sans test associé,
                    # la feature reste READY et n'est PAS promue VALIDATED.
                    # (Message d'origine : une feature ne doit jamais devenir
                    # VALIDATED parce qu'elle a simplement été découverte.)
                    if feature.test_paths:
                        feature.status = FeatureStatus.VALIDATED
                        count += 1
                        self.history.record(
                            feature.id,
                            "VALIDATED",
                            actor="validator",
                            details={"evidence": "tests", "test_paths": feature.test_paths[:5]},
                        )
                    else:
                        feature.status = FeatureStatus.READY
                        self.history.record(
                            feature.id,
                            "READY",
                            actor="validator",
                            details={"evidence": "parses+resolved_deps", "missing": "no_tests"},
                        )
                elif readiness == "BROKEN":
                    feature.status = FeatureStatus.BROKEN
                elif readiness == "BLOCKED":
                    feature.status = FeatureStatus.BLOCKED
        
        return count

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        stats = self.registry.get_statistics()
        stats["conflicts"] = self.compatibility.get_conflict_summary()
        stats["orphans"] = self.dependencies.detect_orphans()
        return stats

    def export_report(self, path: Optional[Path] = None) -> Path:
        """Export full report to CSV and JSON."""
        if path is None:
            path = self.project_root / "feature_pool_report.csv"
        
        # Export CSV
        csv_path = self.registry.export_csv(path)
        
        # Export JSON with full details
        json_path = path.with_suffix(".json")
        payload = __import__("json").dumps({
            "features": [f.to_dict() for f in self.registry.all_features],
            "statistics": self.get_statistics(),
            "exported_at": __import__("datetime").datetime.now().isoformat(),
        }, indent=2)
        json_path.write_text(payload, encoding="utf-8")

        # Miroir historique : certains consommateurs (pont Pipeline Inspector,
        # anciens scripts d'audit) lisent encore le nom préfixé par un point.
        # On écrit la MÊME version fraîche aux deux emplacements : aucun
        # fichier n'est supprimé et aucun rapport périmé ne peut masquer le
        # nouveau.
        legacy_path = self.project_root / ".feature_pool_report.json"
        if legacy_path.resolve() != json_path.resolve():
            legacy_path.write_text(payload, encoding="utf-8")

        return csv_path

    def get_feature_list(self) -> List[Dict[str, str]]:
        """Get feature list for display."""
        features = sorted(
            self.registry.all_features,
            key=lambda f: (f.category.value, f.name),
        )
        
        result = []
        for f in features:
            result.append({
                "id": f.id,
                "name": f.name,
                "source": f.source,
                "category": f.category.value,
                "status": f.status.value,
                "integration_status": f.integration_status.value,
                "dependencies": "; ".join(sorted(f.dependencies)) if f.dependencies else "",
                "tests": "; ".join(f.test_paths) if f.test_paths else "",
                "action": f.recommended_action,
            })
        
        return result
