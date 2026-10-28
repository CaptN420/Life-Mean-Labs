"""Tests for Phase 4B: DivergenceEngine and ConvergenceEngine."""

from __future__ import annotations

import unittest
from typing import Any, Dict
from unittest.mock import MagicMock

from life_mean_lab.orchestrator import (
    AgentResult,
    Branch,
    BranchStatus,
    ConvergenceResult,
    OrchestrationTrace,
    Strategy,
    Task,
)
from life_mean_lab.orchestrator.task_analyzer import TaskAnalysis, UncertaintyLevel, RiskLevel
from life_mean_lab.orchestrator.divergence_engine import (
    DivergenceEngine,
    DivergenceStrategy,
    BranchConfig,
    DivergenceResult,
)
from life_mean_lab.orchestrator.convergence_engine import (
    ConvergenceEngine,
    ConvergenceOutcome,
    BranchEvidence,
    EvidenceLevel,
    ConvergenceAnalysis,
)


class TestDivergenceStrategy(unittest.TestCase):
    """Tests for DivergenceStrategy enum."""

    def test_all_strategies_exist(self):
        self.assertEqual(len(DivergenceStrategy), 5)
        self.assertIn(DivergenceStrategy.DIRECT, list(DivergenceStrategy))
        self.assertIn(DivergenceStrategy.DECOMPOSED, list(DivergenceStrategy))


class TestBranchConfig(unittest.TestCase):
    """Tests for BranchConfig dataclass."""

    def test_creation(self):
        config = BranchConfig(
            branch_id="test_branch",
            strategy=DivergenceStrategy.DIRECT,
            token_budget=4096,
            time_budget_seconds=120.0,
        )
        self.assertEqual(config.branch_id, "test_branch")
        self.assertEqual(config.token_budget, 4096)


class TestDivergenceResult(unittest.TestCase):
    """Tests for DivergenceResult."""

    def test_empty_result(self):
        result = DivergenceResult(task_id="t1")
        self.assertEqual(result.branches_created, 0)
        self.assertFalse(result.has_successful_branch)
        self.assertIsNone(result.best_branch)

    def test_has_successful_branch(self):
        result = DivergenceResult(task_id="t1")
        result.branches.append(Branch(
            branch_id="b1", task_id="t1",
            status=BranchStatus.EVALUATED,
            evaluation={"validation_passed": True},
        ))
        self.assertTrue(result.has_successful_branch)

    def test_best_branch_selection(self):
        result = DivergenceResult(task_id="t1")
        result.branches = [
            Branch(
                branch_id="b1", task_id="t1",
                status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": False},
                result=AgentResult(run_id="r", task_id="t1", strategy=Strategy.DIVERGENT,
                                   tokens_total=5000),
            ),
            Branch(
                branch_id="b2", task_id="t1",
                status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": True},
                result=AgentResult(run_id="r", task_id="t1", strategy=Strategy.DIVERGENT,
                                   tokens_total=3000),
            ),
        ]
        best = result.best_branch
        self.assertEqual(best.branch_id, "b2")


class TestDivergenceEngine(unittest.TestCase):
    """Tests for DivergenceEngine."""

    def test_create_branches(self):
        engine = DivergenceEngine(max_branches=3)
        task = Task(task_id="test", description="complex system", difficulty=4)
        analysis = TaskAnalysis(
            task_id="test",
            complexity=4,
            independent_subtasks=3,
            uncertainty=UncertaintyLevel.HIGH,
            risk_level=RiskLevel.HIGH,
            needs_verification=True,
        )
        configs = engine.create_branches(task, analysis)
        self.assertGreaterEqual(len(configs), 2)
        self.assertEqual(configs[0].strategy, DivergenceStrategy.DIRECT)

    def test_execute_branch(self):
        engine = DivergenceEngine()
        task = Task(task_id="test", description="simple task")
        config = BranchConfig(
            branch_id="b1",
            strategy=DivergenceStrategy.DIRECT,
            token_budget=1000,
            time_budget_seconds=60.0,
        )

        def dummy_executor(cfg, tk):
            return AgentResult(
                run_id="r1", task_id=tk.task_id,
                strategy=Strategy.DIVERGENT,
                final_output="result",
                tokens_total=100,
                duration_seconds=0.5,
            )

        branch = engine.execute_branch(config, task, dummy_executor)
        self.assertEqual(branch.status, BranchStatus.EVALUATED)
        self.assertIsNotNone(branch.result)

    def test_execute_all(self):
        engine = DivergenceEngine(max_branches=2)
        task = Task(task_id="test", description="complex uncertain task", difficulty=4)
        analysis = TaskAnalysis(
            task_id="test",
            complexity=4,
            independent_subtasks=3,
            uncertainty=UncertaintyLevel.HIGH,
            risk_level=RiskLevel.MEDIUM,
            needs_verification=True,
        )

        def dummy_executor(cfg, tk):
            return AgentResult(
                run_id="r1", task_id=tk.task_id,
                strategy=Strategy.DIVERGENT,
                final_output=f"result for {cfg.strategy.value}",
                tokens_total=100,
                duration_seconds=0.5,
            )

        result = engine.execute_all(task, analysis, dummy_executor)
        self.assertEqual(result.branches_created, 2)
        self.assertEqual(result.branches_completed, 2)

    def test_cancel(self):
        engine = DivergenceEngine()
        engine.cancel("Test cancellation")
        self.assertTrue(engine._cancelled)

    def test_detect_redundancy(self):
        engine = DivergenceEngine()
        branches = [
            Branch(
                branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                result=AgentResult(run_id="r", task_id="t1", strategy=Strategy.DIVERGENT,
                                   final_output="same output", tokens_total=100),
            ),
            Branch(
                branch_id="b2", task_id="t1", status=BranchStatus.EVALUATED,
                result=AgentResult(run_id="r", task_id="t1", strategy=Strategy.DIVERGENT,
                                   final_output="same output", tokens_total=100),
            ),
        ]
        redundancies = engine.detect_redundancy(branches)
        self.assertIn("b2", redundancies)

    def test_isolated_workspaces(self):
        """Verify branches use isolated workspaces."""
        engine = DivergenceEngine(max_branches=2)
        task = Task(task_id="test", description="task")
        analysis = TaskAnalysis(
            task_id="test", complexity=3, independent_subtasks=2,
            uncertainty=UncertaintyLevel.MEDIUM, risk_level=RiskLevel.LOW,
            needs_verification=False,
        )

        def dummy_executor(cfg, tk):
            return AgentResult(
                run_id="r1", task_id=tk.task_id,
                strategy=Strategy.DIVERGENT,
                final_output="result",
                tokens_total=50,
                duration_seconds=0.1,
            )

        result = engine.execute_all(task, analysis, dummy_executor)
        # Each branch should have its own workspace.
        for branch in result.branches:
            self.assertIn("workspace", branch.context_snapshot)


class TestEvidenceLevel(unittest.TestCase):
    """Tests for EvidenceLevel enum."""

    def test_all_levels_exist(self):
        self.assertEqual(len(EvidenceLevel), 4)
        self.assertIn(EvidenceLevel.STRONG, list(EvidenceLevel))


class TestBranchEvidence(unittest.TestCase):
    """Tests for BranchEvidence."""

    def test_valid_evidence(self):
        evidence = BranchEvidence(
            branch_id="b1",
            evidence_level=EvidenceLevel.STRONG,
            validation_passed=True,
            tests_passed=5,
        )
        self.assertTrue(evidence.is_valid)

    def test_invalid_evidence(self):
        evidence = BranchEvidence(
            branch_id="b1",
            evidence_level=EvidenceLevel.WEAK,
            validation_passed=False,
            regressions_detected=["regression1"],
        )
        self.assertFalse(evidence.is_valid)


class TestConvergenceEngine(unittest.TestCase):
    """Tests for ConvergenceEngine."""

    def test_analyze_no_branches(self):
        engine = ConvergenceEngine()
        analysis = engine.analyze("t1", [])
        self.assertEqual(analysis.outcome, ConvergenceOutcome.FAILED)

    def test_analyze_single_valid_branch(self):
        engine = ConvergenceEngine()
        branches = [
            Branch(
                branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": True, "tests_passed": 3},
            ),
        ]
        analysis = engine.analyze("t1", branches)
        self.assertEqual(analysis.outcome, ConvergenceOutcome.SELECTED)
        self.assertEqual(analysis.selected_branch_id, "b1")

    def test_analyze_multiple_valid_branches(self):
        engine = ConvergenceEngine()
        branches = [
            Branch(
                branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": True, "tests_passed": 2,
                            "code_quality_score": 0.6},
            ),
            Branch(
                branch_id="b2", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": True, "tests_passed": 5,
                            "code_quality_score": 0.9},
            ),
        ]
        analysis = engine.analyze("t1", branches)
        self.assertEqual(analysis.outcome, ConvergenceOutcome.SELECTED)
        # b2 should be selected (more tests, higher quality).
        self.assertEqual(analysis.selected_branch_id, "b2")

    def test_analyze_all_invalid(self):
        engine = ConvergenceEngine()
        branches = [
            Branch(
                branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": False},
            ),
        ]
        analysis = engine.analyze("t1", branches)
        self.assertEqual(analysis.outcome, ConvergenceOutcome.FAILED)

    def test_analyze_with_custom_evaluation(self):
        engine = ConvergenceEngine()

        def custom_eval(branch):
            return BranchEvidence(
                branch_id=branch.branch_id,
                evidence_level=EvidenceLevel.STRONG,
                validation_passed=True,
                tests_passed=10,
            )

        branches = [
            Branch(branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED),
        ]
        analysis = engine.analyze("t1", branches, evaluation_fn=custom_eval)
        self.assertEqual(len(analysis.valid_branches), 1)

    def test_require_approval(self):
        engine = ConvergenceEngine()

        # Single valid branch — no approval needed.
        analysis = ConvergenceAnalysis(task_id="t1", outcome=ConvergenceOutcome.SELECTED)
        self.assertFalse(engine.require_approval(analysis))

        # Multiple valid branches — approval needed.
        analysis.outcome = ConvergenceOutcome.TIE
        self.assertTrue(engine.require_approval(analysis))

    def test_build_convergence_result(self):
        engine = ConvergenceEngine()
        analysis = ConvergenceAnalysis(
            task_id="t1",
            outcome=ConvergenceOutcome.SELECTED,
            selected_branch_id="b1",
        )
        branches = [
            Branch(branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                   evaluation={"validation_passed": True}),
        ]
        trace = OrchestrationTrace(run_id="r1", task_id="t1", strategy_chosen=Strategy.DIVERGENT)
        result = engine.build_convergence_result(analysis, branches, trace)
        self.assertEqual(result.selected_branch_id, "b1")
        self.assertTrue(result.validation_passed)


class TestIntegration(unittest.TestCase):
    """Integration tests for Phase 4B."""

    def test_end_to_end_divergence_convergence(self):
        """Test full divergence → convergence workflow."""
        from life_mean_lab.orchestrator import AdaptiveStrategyController

        controller = AdaptiveStrategyController(enable_divergence=True)
        task = Task(
            task_id="integration",
            description="complex uncertain research",
            difficulty=4,
        )

        # Run divergence and convergence.
        div_result, conv_analysis = controller.run_divergence(task)

        # Verify results.
        self.assertGreaterEqual(div_result.branches_created, 1)
        self.assertIn(conv_analysis.outcome, [
            ConvergenceOutcome.SELECTED,
            ConvergenceOutcome.FAILED,
        ])

    def test_verified_solution_preferred_over_elegant_but_wrong(self):
        """Test that verified solution is preferred over elegant but incorrect."""
        engine = ConvergenceEngine()

        # Branch 1: Elegant but fails tests.
        branches = [
            Branch(
                branch_id="elegant", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={
                    "validation_passed": False,
                    "tests_passed": 0,
                    "tests_failed": 2,
                    "code_quality_score": 0.95,
                },
            ),
            Branch(
                branch_id="simple", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={
                    "validation_passed": True,
                    "tests_passed": 5,
                    "code_quality_score": 0.7,
                },
            ),
        ]
        analysis = engine.analyze("t1", branches)
        # Should prefer the verified solution.
        self.assertEqual(analysis.selected_branch_id, "simple")

    def test_no_automated_merge(self):
        """Verify convergence never triggers automatic merge."""
        engine = ConvergenceEngine()
        branches = [
            Branch(
                branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": True},
            ),
        ]
        analysis = engine.analyze("t1", branches)
        # Convergence only selects, never merges.
        self.assertEqual(analysis.outcome, ConvergenceOutcome.SELECTED)


if __name__ == "__main__":
    unittest.main()
