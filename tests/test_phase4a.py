"""Tests for Phase 4A: TaskAnalyzer and AdaptiveStrategyController."""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from life_mean_lab.orchestrator import (
    AgentResult,
    Branch,
    BranchStatus,
    ConvergenceResult,
    OrchestrationTrace,
    Strategy,
    Task,
)
from life_mean_lab.orchestrator.task_analyzer import (
    TaskAnalyzer,
    TaskAnalysis,
    UncertaintyLevel,
    RiskLevel,
    CorrectionRecord,
)
from life_mean_lab.orchestrator.adaptive_controller import (
    AdaptiveStrategyController,
    StrategyDecision,
    ControllerDecision,
)


class TestTaskAnalyzer(unittest.TestCase):
    """Tests for TaskAnalyzer."""

    def test_simple_task_analysis(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="simple", description="print hello world")
        analysis = analyzer.analyze(task)
        self.assertEqual(analysis.task_id, "simple")
        self.assertTrue(analysis.is_simple)
        self.assertEqual(analysis.uncertainty, UncertaintyLevel.LOW)
        self.assertEqual(analysis.risk_level, RiskLevel.LOW)

    def test_complex_task_analysis(self):
        analyzer = TaskAnalyzer()
        task = Task(
            task_id="complex",
            description="build a distributed scalable system",
            difficulty=4,
        )
        analysis = analyzer.analyze(task)
        self.assertTrue(analysis.is_complex)
        self.assertGreaterEqual(analysis.complexity, 4)

    def test_uncertain_task(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="uncertain", description="explore unknown novel approach")
        analysis = analyzer.analyze(task)
        self.assertTrue(analysis.is_uncertain)
        self.assertEqual(analysis.uncertainty, UncertaintyLevel.HIGH)

    def test_needs_verification(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="verify", description="implement and verify the algorithm")
        analysis = analyzer.analyze(task)
        self.assertTrue(analysis.needs_verification)

    def test_risk_assessment(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="risky", description="refactor core critical system")
        analysis = analyzer.analyze(task)
        self.assertEqual(analysis.risk_level, RiskLevel.HIGH)

    def test_subtask_estimation(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="multi", description="step 1: parse, step 2: generate, step 3: validate")
        analysis = analyzer.analyze(task)
        self.assertGreaterEqual(analysis.independent_subtasks, 3)

    def test_token_budget_estimation(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="budget", description="complex task", difficulty=4)
        analysis = analyzer.analyze(task)
        self.assertGreaterEqual(analysis.token_budget_estimate, 4096)

    def test_time_budget_estimation(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="time", description="task", difficulty=3)
        analysis = analyzer.analyze(task)
        self.assertGreaterEqual(analysis.time_budget_estimate_seconds, 90.0)


class TestCorrectionRecord(unittest.TestCase):
    """Tests for correction records."""

    def test_correction_record_creation(self):
        record = CorrectionRecord(
            task_id="t1",
            estimated_complexity=3,
            actual_complexity=4,
            estimated_subtasks=2,
            actual_subtasks=3,
            correction_factor=1.33,
        )
        self.assertEqual(record.task_id, "t1")
        self.assertEqual(record.correction_factor, 1.33)

    def test_correction_record_defaults(self):
        record = CorrectionRecord(
            task_id="t2",
            estimated_complexity=2,
            actual_complexity=2,
            estimated_subtasks=1,
            actual_subtasks=1,
        )
        self.assertEqual(record.correction_factor, 1.0)


class TestTaskAnalyzerLearning(unittest.TestCase):
    """Tests for learning from observations."""

    def test_record_observation(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="learn", description="complex system", difficulty=3)
        analysis = analyzer.analyze(task)

        # Record that actual was harder than estimated.
        analyzer.record_observation(
            task_id="learn",
            estimated=analysis,
            actual_passed=False,
            actual_steps=6,
        )

        summary = analyzer.get_learning_summary()
        self.assertEqual(summary["corrections_count"], 1)
        self.assertGreaterEqual(summary["average_correction_factor"], 1.0)

    def test_correction_refines_estimates(self):
        analyzer = TaskAnalyzer()
        task = Task(task_id="refine", description="complex refactoring", difficulty=3)

        # First analysis.
        analysis1 = analyzer.analyze(task)
        self.assertEqual(analysis1.complexity, 3)

        # Record observation showing actual was harder.
        analyzer.record_observation(
            task_id="refine",
            estimated=analysis1,
            actual_passed=False,
            actual_steps=8,
        )

        # Second analysis should be refined.
        analysis2 = analyzer.analyze(task)
        self.assertGreaterEqual(analysis2.complexity, analysis1.complexity)


class TestAdaptiveStrategyController(unittest.TestCase):
    """Tests for AdaptiveStrategyController."""

    def test_simple_task_direct_execution(self):
        controller = AdaptiveStrategyController()
        task = Task(task_id="simple", description="print hello")
        decision = controller.select_strategy(task)
        self.assertEqual(decision.decision_type, ControllerDecision.DIRECT_EXECUTION)
        self.assertEqual(decision.strategy, Strategy.SEQUENTIAL)

    def test_complex_task_mode_a(self):
        controller = AdaptiveStrategyController()
        task = Task(task_id="complex", description="build system", difficulty=3)
        decision = controller.select_strategy(task)
        # Should be Mode A for complex but not uncertain.
        self.assertIn(
            decision.decision_type,
            [ControllerDecision.MODE_A_MULTI_ROLE, ControllerDecision.MODE_B_COLLABORATION],
        )

    def test_uncertain_task_divergence(self):
        controller = AdaptiveStrategyController(enable_divergence=True)
        task = Task(task_id="uncertain", description="explore unknown novel research approach", difficulty=4)
        decision = controller.select_strategy(task)
        self.assertEqual(decision.decision_type, ControllerDecision.DIVERGENCE)
        self.assertEqual(decision.strategy, Strategy.DIVERGENT)

    def test_decision_explainability(self):
        controller = AdaptiveStrategyController()
        task = Task(task_id="explain", description="simple task")
        decision = controller.select_strategy(task)
        self.assertIsInstance(decision.reason, str)
        self.assertGreater(len(decision.reason), 0)

    def test_decision_to_dict(self):
        controller = AdaptiveStrategyController()
        task = Task(task_id="dict", description="test")
        decision = controller.select_strategy(task)
        d = decision.to_dict()
        self.assertIn("decision_type", d)
        self.assertIn("strategy", d)
        self.assertIn("reason", d)

    def test_budget_check(self):
        controller = AdaptiveStrategyController(
            token_budget=1000,
            time_budget_seconds=60.0,
        )
        # Normal usage.
        result = controller.check_budget(tokens_used=500, time_elapsed=30.0)
        self.assertEqual(result, ControllerDecision.DIRECT_EXECUTION)

        # Budget exhausted.
        result = controller.check_budget(tokens_used=950, time_elapsed=55.0)
        self.assertEqual(result, ControllerDecision.EARLY_STOP)

    def test_decision_history(self):
        controller = AdaptiveStrategyController()
        task1 = Task(task_id="h1", description="simple")
        task2 = Task(task_id="h2", description="complex system", difficulty=4)

        controller.select_strategy(task1)
        controller.select_strategy(task2)

        history = controller.get_decision_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["decision_type"], "direct_execution")

    def test_build_trace(self):
        controller = AdaptiveStrategyController()
        task = Task(task_id="trace", description="test")
        decision = controller.select_strategy(task)
        trace = controller.build_trace("run1", task, decision)

        self.assertEqual(trace.run_id, "run1")
        self.assertEqual(trace.task_id, "trace")
        self.assertEqual(trace.strategy_chosen, decision.strategy)
        self.assertGreaterEqual(len(trace.decisions), 1)

    def test_converge_no_evaluated(self):
        controller = AdaptiveStrategyController()
        branches = [
            Branch(branch_id="b1", task_id="t1", status=BranchStatus.PENDING),
        ]
        trace = OrchestrationTrace(run_id="r1", task_id="t1", strategy_chosen=Strategy.DIVERGENT)
        result = controller.converge(branches, trace)
        self.assertEqual(result.integration_method, "rollback")

    def test_converge_selects_best(self):
        controller = AdaptiveStrategyController()
        branches = [
            Branch(
                branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": False},
                result=AgentResult(run_id="r1", task_id="t1", strategy=Strategy.DIVERGENT,
                                   tokens_total=5000),
            ),
            Branch(
                branch_id="b2", task_id="t1", status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": True},
                result=AgentResult(run_id="r1", task_id="t1", strategy=Strategy.DIVERGENT,
                                   tokens_total=3000),
            ),
        ]
        trace = OrchestrationTrace(run_id="r1", task_id="t1", strategy_chosen=Strategy.DIVERGENT)
        result = controller.converge(branches, trace)
        self.assertEqual(result.selected_branch_id, "b2")
        self.assertTrue(result.validation_passed)

    def test_suggest_branches(self):
        controller = AdaptiveStrategyController()
        task = Task(task_id="div", description="explore unknown novel research")
        analysis = controller.analyze(task)
        branches = controller.suggest_branches(task, analysis)
        self.assertGreaterEqual(len(branches), 2)

    def test_record_observation_via_controller(self):
        controller = AdaptiveStrategyController()
        task = Task(task_id="ctrl", description="complex task", difficulty=3)
        analysis = controller.analyze(task)

        controller.record_observation(
            task_id="ctrl",
            analysis=analysis,
            passed=False,
            steps_taken=6,
        )

        summary = controller.get_learning_summary()
        self.assertEqual(summary["corrections_count"], 1)


class TestIntegration(unittest.TestCase):
    """Integration tests for Phase 4A."""

    def test_end_to_end_workflow(self):
        """Test full workflow: analyze → select → trace → converge."""
        controller = AdaptiveStrategyController()

        # Task definition.
        task = Task(
            task_id="integration_test",
            description="build a scalable distributed system with verification",
            difficulty=4,
            context_budget_tokens=8192,
        )

        # Analyze.
        analysis = controller.analyze(task)
        self.assertTrue(analysis.is_complex)
        self.assertTrue(analysis.needs_verification)

        # Select strategy.
        decision = controller.select_strategy(task)
        self.assertIsNotNone(decision.reason)

        # Build trace.
        trace = controller.build_trace("run_integration", task, decision)
        self.assertEqual(trace.task_id, "integration_test")

        # Simulate branch execution and convergence.
        branches = [
            Branch(
                branch_id="branch_a", task_id="integration_test",
                status=BranchStatus.EVALUATED,
                evaluation={"validation_passed": True},
                result=AgentResult(
                    run_id="run_integration", task_id="integration_test",
                    strategy=Strategy.DIVERGENT, tokens_total=2000,
                ),
            ),
        ]
        result = controller.converge(branches, trace)
        self.assertEqual(result.selected_branch_id, "branch_a")

    def test_learning_over_time(self):
        """Test that the controller learns from past observations."""
        controller = AdaptiveStrategyController()

        # Simulate multiple tasks with varying outcomes.
        for i in range(5):
            task = Task(task_id=f"learn_{i}", description="complex refactoring", difficulty=3)
            analysis = controller.analyze(task)
            controller.record_observation(
                task_id=f"learn_{i}",
                analysis=analysis,
                passed=i > 2,  # Some pass, some fail.
                steps_taken=i * 2,
            )

        summary = controller.get_learning_summary()
        self.assertEqual(summary["corrections_count"], 5)


if __name__ == "__main__":
    unittest.main()
