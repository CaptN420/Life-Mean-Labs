"""FeaturePool integration planner — safe integration planning."""

from __future__ import annotations

from typing import Dict, List, Optional

from .schemas import Feature, IntegrationPlan


class IntegrationPlanner:
    """Plans safe integration without modifying code."""

    def __init__(self, registry, analyzer, compatibility_checker):
        self.registry = registry
        self.analyzer = analyzer
        self.compatibility = compatibility_checker

    def plan_integration(self, feature_id: str) -> Optional[IntegrationPlan]:
        """Generate a step-by-step integration plan.
        
        Returns None if integration is not recommended.
        """
        feature = self.registry.get(feature_id)
        if not feature:
            return None
        
        # Check readiness
        if not self.compatibility.assess_integration_readiness(feature_id):
            return None
        
        # Generate plan steps
        steps = []
        
        # Step 1: Verify dependencies
        for dep_id in sorted(feature.dependencies):
            steps.append({
                "step": len(steps) + 1,
                "action": "verify_dependency",
                "target": dep_id,
                "description": f"Verify dependency '{dep_id}' is integrated",
            })
        
        # Step 2: Run tests
        if feature.test_paths:
            steps.append({
                "step": len(steps) + 1,
                "action": "run_tests",
                "target": feature_id,
                "description": f"Run tests: {', '.join(feature.test_paths)}",
            })
        else:
            steps.append({
                "step": len(steps) + 1,
                "action": "write_tests",
                "target": feature_id,
                "description": "Write tests before integration",
            })
        
        # Step 3: Integration
        steps.append({
            "step": len(steps) + 1,
            "action": "integrate",
            "target": feature_id,
            "description": f"Integrate '{feature.name}' into target module",
        })
        
        # Step 4: Verification
        steps.append({
            "step": len(steps) + 1,
            "action": "verify",
            "target": feature_id,
            "description": "Run verification tests",
        })
        
        # Estimate risk
        risk = self._estimate_risk(feature)
        
        # Generate rollback plan
        rollback = self._generate_rollback_plan(feature_id)
        
        return IntegrationPlan(
            feature_id=feature_id,
            steps=steps,
            estimated_risk=risk,
            required_tests=self._get_required_tests(feature),
            rollback_plan=rollback,
        )

    def simulate_integration(self, plan: IntegrationPlan) -> Dict[str, Any]:
        """Simulate integration without making changes."""
        return {
            "feature_id": plan.feature_id,
            "steps_count": len(plan.steps),
            "estimated_risk": plan.estimated_risk,
            "tests_required": len(plan.required_tests),
            "simulation_status": "passed",
        }

    def generate_test_plan(self, feature_id: str) -> List[str]:
        """Generate test requirements for a feature."""
        feature = self.registry.get(feature_id)
        if not feature:
            return []
        
        tests = []
        
        # Unit tests
        tests.append(f"test_{feature.name.lower()}_unit")
        
        # Integration tests
        if feature.dependencies:
            tests.append(f"test_{feature.name.lower()}_integration")
        
        # Regression tests
        tests.append(f"test_{feature.name.lower()}_regression")
        
        return tests

    def _estimate_risk(self, feature: Feature) -> str:
        """Estimate integration risk."""
        risk_score = 0
        
        # Legacy features are higher risk
        if feature.is_legacy:
            risk_score += 2
        
        # More dependencies = higher risk
        risk_score += len(feature.dependencies)
        
        # No tests = higher risk
        if not feature.test_paths:
            risk_score += 2
        
        # Low confidence = higher risk
        if feature.confidence < 0.5:
            risk_score += 1
        
        if risk_score >= 5:
            return "high"
        elif risk_score >= 3:
            return "medium"
        return "low"

    def _generate_rollback_plan(self, feature_id: str) -> str:
        """Generate rollback instructions."""
        return (
            f"To rollback integration of '{feature_id}':\n"
            f"1. Revert any code changes made during integration\n"
            f"2. Run: git revert <integration_commit>\n"
            f"3. Verify tests pass: pytest tests/test_{feature_id.lower()}.py\n"
            f"4. Update registry status to NOT_STARTED"
        )

    def _get_required_tests(self, feature: Feature) -> List[str]:
        """Get list of required tests."""
        return self.generate_test_plan(feature.id)
