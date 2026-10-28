"""Tests for Phase 4C.5: RealLLMExecutor."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from life_mean_lab.orchestrator import (
    AgentResult,
    Strategy,
    Task,
)
from life_mean_lab.orchestrator.real_llm_executor import (
    RealLLMExecutor,
    ExecutionStatus,
    LLMCallMetrics,
    ExecutionMetrics,
)
from life_mean_lab.orchestrator.task_analyzer import TaskAnalysis, UncertaintyLevel, RiskLevel


class TestLLMCallMetrics(unittest.TestCase):
    """Tests for LLMCallMetrics."""

    def test_creation(self):
        metrics = LLMCallMetrics(
            tokens_input=100,
            tokens_output=50,
            latency_ms=200.0,
            success=True,
            model_used="llama-3.2-1b",
        )
        self.assertEqual(metrics.tokens_input, 100)
        self.assertTrue(metrics.success)

    def test_error_state(self):
        metrics = LLMCallMetrics(error="timeout")
        self.assertFalse(metrics.success)
        self.assertEqual(metrics.error, "timeout")


class TestExecutionMetrics(unittest.TestCase):
    """Tests for ExecutionMetrics."""

    def test_success_status(self):
        metrics = ExecutionMetrics(branch_id="b1", task_id="t1")
        self.assertTrue(metrics.is_success)

    def test_failure_status(self):
        metrics = ExecutionMetrics(branch_id="b1", task_id="t1")
        metrics.status = ExecutionStatus.FAILED
        self.assertFalse(metrics.is_success)

    def test_avg_latency(self):
        metrics = ExecutionMetrics()
        metrics.call_count = 3
        metrics.total_latency_ms = 600.0
        self.assertAlmostEqual(metrics.avg_latency_ms, 200.0)

    def test_empty_avg_latency(self):
        metrics = ExecutionMetrics()
        self.assertEqual(metrics.avg_latency_ms, 0.0)


class TestRealLLMExecutor(unittest.TestCase):
    """Tests for RealLLMExecutor."""

    def test_initial_state(self):
        executor = RealLLMExecutor()
        self.assertFalse(executor.is_available)
        self.assertIsNone(executor._llm_client)

    def test_unavailable_without_credentials(self):
        executor = RealLLMExecutor(base_url="", api_key="")
        self.assertFalse(executor.is_available)

    def test_execute_with_custom_executor(self):
        executor = RealLLMExecutor()
        task = Task(task_id="test", description="simple task")

        def mock_executor(task, analysis, strategy, branch_id, budget_controller):
            return AgentResult(
                run_id="r1", task_id=task.task_id,
                strategy=strategy, final_output="mock result",
                tokens_total=100, duration_seconds=0.5,
            ), ExecutionMetrics()

        result, metrics = executor.execute(
            task, executor_fn=mock_executor
        )
        self.assertEqual(result.final_output, "mock result")
        self.assertEqual(metrics.branch_id, "")

    def test_execute_with_budget_check(self):
        executor = RealLLMExecutor()
        task = Task(task_id="test", description="task")

        # Create a budget controller that reports exhausted.
        budget_controller = MagicMock()
        budget_controller.should_stop.return_value = (True, "Token budget exhausted")

        result, metrics = executor.execute(
            task, budget_controller=budget_controller
        )
        self.assertEqual(metrics.status, ExecutionStatus.TIMEOUT)
        self.assertIn("Budget exhausted", metrics.errors[0])

    def test_execute_direct(self):
        executor = RealLLMExecutor()
        task = Task(task_id="test", description="write a function")

        # Mock _call_llm directly.
        with patch.object(executor, '_call_llm') as mock_call:
            mock_call.return_value = {"response": "def foo(): pass", "error": None}
            result, metrics = executor.execute(
                task, strategy=Strategy.SEQUENTIAL
            )
            self.assertIsNotNone(result)
            # _call_llm was called once.
            mock_call.assert_called_once()

    def test_execute_multi_role(self):
        executor = RealLLMExecutor()
        task = Task(task_id="test", description="implement sorting")

        # Mock _call_llm to return different responses for planner and developer.
        with patch.object(executor, '_call_llm') as mock_call:
            mock_call.side_effect = [
                {"response": "Plan: sort by quicksort", "error": None},  # planner
                {"response": "def sort(arr): return sorted(arr)", "error": None},  # developer
                {"response": "PASS", "error": None},  # critic (optional)
            ]
            analysis = TaskAnalysis(
                task_id="test", complexity=2, independent_subtasks=1,
                uncertainty=UncertaintyLevel.LOW, risk_level=RiskLevel.LOW,
                needs_verification=True,
            )
            result, metrics = executor.execute(
                task, analysis=analysis, strategy=Strategy.SINGLE_MODEL_MULTI_ROLE
            )
            self.assertIsNotNone(result)
            # Should have made 3 calls (planner + developer + critic).
            self.assertEqual(mock_call.call_count, 3)

    def test_execute_with_error(self):
        executor = RealLLMExecutor()
        task = Task(task_id="test", description="task")

        # Mock _call_llm to raise an error.
        with patch.object(executor, '_call_llm') as mock_call:
            mock_call.side_effect = Exception("Connection refused")
            result, metrics = executor.execute(
                task, strategy=Strategy.SEQUENTIAL
            )
            self.assertEqual(metrics.status, ExecutionStatus.FAILED)
            self.assertGreater(len(metrics.errors), 0)

    def test_reset_metrics(self):
        executor = RealLLMExecutor()
        executor._call_metrics.append(LLMCallMetrics(tokens_output=100))
        self.assertEqual(len(executor._call_metrics), 1)
        executor.reset_metrics()
        self.assertEqual(len(executor._call_metrics), 0)

    def test_get_metrics_summary(self):
        executor = RealLLMExecutor()
        executor._call_metrics = [
            LLMCallMetrics(tokens_input=100, tokens_output=50, latency_ms=200.0, success=True),
            LLMCallMetrics(tokens_input=80, tokens_output=40, latency_ms=150.0, success=True),
        ]
        summary = executor.get_metrics_summary()
        self.assertEqual(summary["total_calls"], 2)
        self.assertEqual(summary["total_tokens_output"], 90)
        self.assertAlmostEqual(summary["avg_latency_ms"], 175.0)

    def test_cancel(self):
        executor = RealLLMExecutor()
        executor.cancel()  # Should not raise

    def test_build_prompt(self):
        executor = RealLLMExecutor()
        task = Task(task_id="test", description="write a function")
        prompt = executor._build_prompt(task, "planner")
        self.assertIn("PLANNER", prompt)
        self.assertIn("write a function", prompt)

    def test_build_prompt_with_context(self):
        executor = RealLLMExecutor()
        task = Task(task_id="test", description="implement")
        prompt = executor._build_prompt(task, "developer", context="Plan: use quicksort")
        self.assertIn("Context:", prompt)
        self.assertIn("use quicksort", prompt)


class TestIntegration(unittest.TestCase):
    """Integration tests for RealLLMExecutor."""

    def test_executor_with_divergence_engine(self):
        """Test executor integrates with divergence engine."""
        from life_mean_lab.orchestrator import DivergenceEngine

        executor = RealLLMExecutor()
        engine = DivergenceEngine(max_branches=2)

        task = Task(task_id="integration", description="complex task", difficulty=3)
        analysis = TaskAnalysis(
            task_id="integration",
            complexity=3,
            independent_subtasks=2,
            uncertainty=UncertaintyLevel.MEDIUM,
            risk_level=RiskLevel.LOW,
            needs_verification=True,
        )

        def mock_executor(cfg, tk):
            return AgentResult(
                run_id="r1", task_id=tk.task_id,
                strategy=Strategy.DIVERGENT,
                final_output="result",
                tokens_total=100,
                duration_seconds=0.5,
            )

        result = engine.execute_all(task, analysis, mock_executor)
        self.assertGreaterEqual(result.branches_created, 1)


if __name__ == "__main__":
    unittest.main()
