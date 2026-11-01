"""FeaturePool compatibility — conflict detection and integration readiness."""

from __future__ import annotations

from typing import Dict, List, Optional

from .schemas import Feature, Conflict, FeatureStatus


class CompatibilityChecker:
    """Checks integration compatibility between features."""

    def __init__(self, registry):
        self.registry = registry

    def check_compatibility(
        self, feature_a_id: str, feature_b_id: str
    ) -> Optional[Conflict]:
        """Check if two features can coexist.
        
        Returns a Conflict if incompatible, None if compatible.
        """
        feat_a = self.registry.get(feature_a_id)
        feat_b = self.registry.get(feature_b_id)
        
        if not feat_a or not feat_b:
            return None
        
        # Check for naming conflicts
        if feat_a.name.lower() == feat_b.name.lower():
            return Conflict(
                feature_a=feature_a_id,
                feature_b=feature_b_id,
                conflict_type="name_collision",
                severity="high",
                description=f"Features '{feat_a.name}' and '{feat_b.name}' have the same name",
            )
        
        # Check for shared dependencies with conflicts
        shared_deps = feat_a.dependencies & feat_b.dependencies
        if shared_deps:
            return Conflict(
                feature_a=feature_a_id,
                feature_b=feature_b_id,
                conflict_type="shared_dependency",
                severity="medium",
                description=f"Both features depend on: {', '.join(shared_deps)}",
            )
        
        # Check for category conflicts (legacy vs modern)
        if feat_a.is_legacy != feat_b.is_legacy:
            return Conflict(
                feature_a=feature_a_id,
                feature_b=feature_b_id,
                conflict_type="legacy_modern_mismatch",
                severity="low",
                description="One feature is legacy, the other is modern",
            )
        
        return None

    def detect_conflicts(self) -> List[Conflict]:
        """Detect all conflicts between features."""
        conflicts = []
        feature_ids = [f.id for f in self.registry.all_features]
        
        for i, id_a in enumerate(feature_ids):
            for id_b in feature_ids[i + 1:]:
                conflict = self.check_compatibility(id_a, id_b)
                if conflict:
                    conflicts.append(conflict)
        
        return conflicts

    def assess_integration_readiness(self, feature_id: str) -> bool:
        """Assess if a feature is ready for integration."""
        feature = self.registry.get(feature_id)
        if not feature:
            return False
        
        # Must be validated
        if feature.status != FeatureStatus.VALIDATED:
            return False
        
        # Check for conflicts
        conflicts = self._get_feature_conflicts(feature_id)
        if conflicts:
            high_severity = [c for c in conflicts if c.severity == "high"]
            if high_severity:
                return False
        
        # Check dependencies are resolved
        for dep_id in feature.dependencies:
            dep_feature = self.registry.get(dep_id)
            if not dep_feature or dep_feature.status != FeatureStatus.INTEGRATED:
                return False
        
        return True

    def _get_feature_conflicts(self, feature_id: str) -> List[Conflict]:
        """Get all conflicts involving a feature."""
        conflicts = []
        for other_id in self.registry.all_features:
            if other_id != feature_id:
                conflict = self.check_compatibility(feature_id, other_id)
                if conflict:
                    conflicts.append(conflict)
        return conflicts

    def get_conflict_summary(self) -> Dict[str, Any]:
        """Get summary of all conflicts."""
        conflicts = self.detect_conflicts()
        
        by_severity = {"high": [], "medium": [], "low": []}
        for conflict in conflicts:
            by_severity[conflict.severity].append(conflict.to_dict())
        
        return {
            "total_conflicts": len(conflicts),
            "by_severity": by_severity,
            "features_with_conflicts": list(set(
                c.feature_a for c in conflicts
            ) | set(c.feature_b for c in conflicts)),
        }
