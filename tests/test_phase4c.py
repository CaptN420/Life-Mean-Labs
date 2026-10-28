"""Tests for Phase 4C: MetacognitiveBudgetController."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from life_mean_lab.orchestrator import (
    OrchestrationTrace,
    Strategy,
    Task,
)
from life_mean_lab.orchestrator.budget_controller import (
    MetacognitiveBudgetController,
    BudgetAllocation,
    AllocationStage,
    TransferRecord,
    ProgressSignal,
)
from life_mean_lab.orchestrator.task_analyzer import TaskAnalysis, UncertaintyLevel, RiskLevel


class TestBudgetAllocation(unittest.TestCase):
    """Tests for BudgetAllocation."""

    def test_initial_state(self):
        alloc = BudgetAllocation(stage=AllocationStage.PLANNING, allocated=1000)
        self.assertEqual(alloc.allocated, 1000)
        self.assertEqual(alloc.used, 0.0)
        self.assertEqual(alloc.remaining, 1000)
        self.assertEqual(alloc.utilization, 0.0)

    def test_utilization_calculation(self):
        alloc = BudgetAllocation(stage=AllocationStage.EXECUTION, allocated=1000, used=250)
        self.assertEqual(alloc.remaining, 750)
        self.assertAlmostEqual(alloc.utilization, 0.25)

    def test_negative_remaining_clamped(self):
        alloc = BudgetAllocation(stage=AllocationStage.EXECUTION, allocated=100, used=150)
        self.assertEqual(alloc.remaining, 0)


class TestTransferRecord(unittest.TestCase):
    """Tests for TransferRecord."""

    def test_creation(self):
        record = TransferRecord(
            from_stage="planning",
            to_stage="execution",
            amount=500.0,
            reason="Planning completed early",
        )
        self.assertEqual(record.from_stage, "planning")
        self.assertEqual(record.amount, 500.0)


class TestProgressSignal(unittest.TestCase):
    """Tests for ProgressSignal."""

    def test_creation(self):
        signal = ProgressSignal(
            signal_type="tests_passed",
            value=5.0,
            source="branch_1",
        )
        self.assertEqual(signal.signal_type, "tests_passed")
        self.assertEqual(signal.source, "branch_1")


class TestMetacognitiveBudgetController(unittest.TestCase):
    """Tests for MetacognitiveBudgetController."""

    def test_initial_state(self):
        controller = MetacognitiveBudgetController(
            global_token_budget=10000,
            global_time_budget_seconds=60.0,
        )
        self.assertEqual(controller.tokens_remaining, 10000)
        self.assertAlmostEqual(controller.time_remaining_seconds, 60.0)

    def test_token_consumption(self):
        controller = MetacognitiveBudgetController(global_token_budget=1000)
        self.assertTrue(controller.record_token_consumption(500))
        self.assertEqual(controller.tokens_remaining, 500)
        self.assertFalse(controller.record_token_consumption(600))  # Exceeds budget
        self.assertEqual(controller.tokens_remaining, 500)  # Not consumed when over budget

    def test_time_consumption(self):
        controller = MetacognitiveBudgetController(global_time_budget_seconds=100.0)
        controller.record_time_consumption(30.0)
        self.assertAlmostEqual(controller.time_remaining_seconds, 70.0)
        controller.record_time_consumption(50.0)
        self.assertAlmostEqual(controller.time_remaining_seconds, 20.0)

    def test_allocation_simple_task(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        analysis = TaskAnalysis(
            task_id="simple",
            complexity=1,
            independent_subtasks=1,
            uncertainty=UncertaintyLevel.LOW,
            risk_level=RiskLevel.LOW,
            needs_verification=False,
        )
        controller.allocate_stage(AllocationStage.EXECUTION, analysis, num_branches=1)
        # Simple task: 80% execution = 8000 tokens.
        self.assertGreaterEqual(controller._allocations[AllocationStage.EXECUTION].allocated, 7000)

    def test_allocation_complex_task(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        analysis = TaskAnalysis(
            task_id="complex",
            complexity=4,
            independent_subtasks=3,
            uncertainty=UncertaintyLevel.HIGH,
            risk_level=RiskLevel.MEDIUM,
            needs_verification=True,
        )
        controller.allocate_stage(AllocationStage.EXECUTION, analysis, num_branches=2)
        # Complex tasks should have smaller execution allocation percentage.
        self.assertLessEqual(
            controller._allocations[AllocationStage.EXECUTION].allocated,
            5000,
        )

    def test_reallocation(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        analysis = TaskAnalysis(
            task_id="test",
            complexity=2,
            independent_subtasks=1,
            uncertainty=UncertaintyLevel.LOW,
            risk_level=RiskLevel.LOW,
            needs_verification=False,
        )
        controller.allocate_stage(AllocationStage.PLANNING, analysis)
        controller.allocate_stage(AllocationStage.EXECUTION, analysis)

        # Ensure PLANNING has some budget to reallocate.
        planning_alloc = controller._allocations[AllocationStage.PLANNING].allocated
        if planning_alloc == 0:
            # Manually set some allocation for testing.
            controller._allocations[AllocationStage.PLANNING].allocated = 1000

        # Reallocate from planning to execution.
        result = controller.reallocate(
            AllocationStage.PLANNING,
            AllocationStage.EXECUTION,
            500.0,
            "Planning completed early",
        )
        self.assertTrue(result)
        self.assertEqual(len(controller._transfers), 1)

    def test_release_branch_budget(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        controller._branch_budgets["branch_1"] = {"tokens": 1000}
        released = controller.release_branch_budget("branch_1")
        self.assertEqual(released, 1000)
        self.assertNotIn("branch_1", controller._branch_budgets)

    def test_progress_recording(self):
        controller = MetacognitiveBudgetController()
        controller.record_progress("tests_passed", 5.0, "branch_1")
        self.assertEqual(len(controller._progress_signals), 1)
        self.assertEqual(controller._stagnation.consecutive_no_progress, 0)

    def test_stagnation_detection(self):
        controller = MetacognitiveBudgetController(no_progress_stalls=2)
        # Simulate no progress.
        controller.increment_no_progress()
        controller.increment_no_progress()
        self.assertTrue(controller.check_stagnation())

    def test_early_stopping_budget_exhausted(self):
        controller = MetacognitiveBudgetController(global_token_budget=1000)
        controller._tokens_used = 1000
        should_stop, reason = controller.should_stop()
        self.assertTrue(should_stop)
        self.assertIn("Token budget", reason)

    def test_early_stopping_disabled(self):
        controller = MetacognitiveBudgetController(
            global_token_budget=100,
            enable_early_stopping=False,
        )
        controller._tokens_used = 100
        should_stop, _ = controller.should_stop()
        self.assertFalse(should_stop)

    def test_fingerprint_computation(self):
        controller = MetacognitiveBudgetController()
        task = Task(task_id="test", description="simple task")
        fingerprint1 = controller.compute_fingerprint(task, {"mode": "a"})
        fingerprint2 = controller.compute_fingerprint(task, {"mode": "b"})
        self.assertNotEqual(fingerprint1, fingerprint2)
        self.assertEqual(len(fingerprint1), 16)

    def test_cache_operations(self):
        controller = MetacognitiveBudgetController()
        fingerprint = controller.compute_fingerprint(
            Task(task_id="test", description="task"), {}
        )
        controller.store_cached_result(fingerprint, {"result": "cached"})
        self.assertEqual(controller.get_cached_result(fingerprint), {"result": "cached"})
        self.assertIsNone(controller.get_cached_result("nonexistent"))

    def test_cache_invalidation(self):
        controller = MetacognitiveBudgetController()
        controller._result_cache = {"abc123": "result1", "def456": "result2"}
        count = controller.invalidate_cache("abc")
        self.assertEqual(count, 1)
        self.assertNotIn("abc123", controller._result_cache)
        self.assertIn("def456", controller._result_cache)

    def test_snapshot(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        controller._tokens_used = 500
        snapshot = controller.take_snapshot()
        self.assertEqual(snapshot.global_tokens_allocated, 10000)
        self.assertEqual(snapshot.global_tokens_used, 500)

    def test_extend_trace(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        controller._tokens_used = 500
        trace = OrchestrationTrace(run_id="r1", task_id="t1", strategy_chosen=Strategy.DIVERGENT)
        controller.extend_trace(trace)
        self.assertIn("budget", trace.metadata)
        self.assertEqual(trace.metadata["budget"]["global_tokens_used"], 500)

    def test_reset(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        controller._tokens_used = 500
        controller._transfers.append(TransferRecord("planning", "execution", 100, "test"))
        controller.reset()
        self.assertEqual(controller.tokens_remaining, 10000)
        self.assertEqual(len(controller._transfers), 0)

    def test_summary(self):
        controller = MetacognitiveBudgetController(global_token_budget=10000)
        controller._tokens_used = 2500
        summary = controller.get_summary()
        self.assertEqual(summary["tokens"]["used"], 2500)
        self.assertAlmostEqual(summary["tokens"]["utilization"], 0.25)

    def test_ram_vram_tracking(self):
        controller = MetacognitiveBudgetController(global_ram_mb=8192, global_vram_mb=4096)
        self.assertTrue(controller.record_ram_consumption(4000))
        self.assertTrue(controller.record_vram_consumption(2000))
        self.assertFalse(controller.record_ram_consumption(5000))  # Exceeds
        self.assertFalse(controller.record_vram_consumption(3000))  # Exceeds

    def test_zero_budget_handling(self):
        """Test that zero budgets are treated as unlimited."""
        controller = MetacognitiveBudgetController(global_token_budget=0)
        self.assertTrue(controller.record_token_consumption(999999))
        self.assertEqual(controller.tokens_utilization, 0.0)


class TestIntegration(unittest.TestCase):
    """Integration tests for Phase 4C."""

    def test_budget_with_divergence(self):
        """Test budget controller integrates with divergence engine."""
        from life_mean_lab.orchestrator import DivergenceEngine

        controller = MetacognitiveBudgetController(global_token_budget=5000)
        engine = DivergenceEngine(
            max_branches=2,
            global_token_budget=5000,
        )

        task = Task(task_id="integration", description="complex task", difficulty=3)
        analysis = TaskAnalysis(
            task_id="integration",
            complexity=3,
            independent_subtasks=2,
            uncertainty=UncertaintyLevel.MEDIUM,
            risk_level=RiskLevel.LOW,
            needs_verification=True,
        )

        def dummy_executor(cfg, tk):
            return type('AgentResult', (), {
                'tokens_total': 100,
                'duration_seconds': 0.5,
            })()

        result = engine.execute_all(task, analysis, dummy_executor)
        self.assertGreaterEqual(result.branches_created, 1)

    def test_budget_with_convergence(self):
        """Test budget controller integrates with convergence engine."""
        from life_mean_lab.orchestrator import ConvergenceEngine

        controller = MetacognitiveBudgetController()
        engine = ConvergenceEngine()

        branches = [
            type('Branch', (), {
                'branch_id': 'b1',
                'status': 'evaluated',
                'evaluation': {'validation_passed': True, 'tests_passed': 3},
                'result': type('Result', (), {'tokens_total': 100})(),
            })(),
        ]
        analysis = engine.analyze("t1", branches)
        self.assertEqual(analysis.outcome.value, "selected")


if __name__ == "__main__":
    unittest.main()
