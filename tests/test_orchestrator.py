"""Tests for the orchestration abstractions layer."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from life_mean_lab.orchestrator import (
    AgentResult,
    AgentType,
    Branch,
    BranchStatus,
    ConvergenceResult,
    OrchestrationTrace,
    Strategy,
    Task,
    ValidationResult,
    CognitiveMemory,
    StrategyRouter,
    BenchmarkRunner,
    ConditionMetrics,
)
from life_mean_lab.orchestrator.memory import MemoryEntry


class TestTask(unittest.TestCase):
    def test_simple_task(self):
        task = Task(task_id="t1", description="write fibonacci")
        self.assertEqual(task.task_id, "t1")
        self.assertFalse(task.is_complex)

    def test_complex_task(self):
        task = Task(task_id="t2", description="build full system",
                    difficulty=4, context_budget_tokens=16384)
        self.assertTrue(task.is_complex)


class TestAgentResult(unittest.TestCase):
    def test_empty_result(self):
        result = AgentResult(run_id="r1", task_id="t1", strategy=Strategy.SINGLE_MODEL_MULTI_ROLE)
        self.assertFalse(result.is_complete)

    def test_successful_result(self):
        result = AgentResult(
            run_id="r1", task_id="t1", strategy=Strategy.SINGLE_MODEL_MULTI_ROLE,
            final_output="def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)",
        )
        self.assertTrue(result.is_complete)

    def test_to_dict(self):
        result = AgentResult(
            run_id="r1", task_id="t1", strategy=Strategy.MULTI_MODEL_COLLABORATION,
            tokens_total=1024, duration_seconds=5.5,
            validation_result=ValidationResult.PASS,
        )
        d = result.to_dict()
        self.assertEqual(d["run_id"], "r1")
        self.assertEqual(d["strategy"], "multi_model_collaboration")
        self.assertEqual(d["validation_result"], "pass")
        self.assertEqual(d["tokens_total"], 1024)


class TestBranch(unittest.TestCase):
    def test_pending_branch(self):
        b = Branch(branch_id="b1", task_id="t1")
        self.assertEqual(b.status, BranchStatus.PENDING)
        self.assertFalse(b.is_evaluated)

    def test_evaluated_branch(self):
        b = Branch(branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                   evaluation={"validation_passed": True})
        self.assertTrue(b.is_evaluated)
        self.assertFalse(b.is_selected)


class TestCognitiveMemory(unittest.TestCase):
    def test_store_and_recall(self):
        mem = CognitiveMemory(project_name="test")
        mem.store("working", "plan", "step1: parse, step2: generate", source_run_id="run1")
        entries = mem.recall("working", "step1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].content, "step1: parse, step2: generate")

    def test_working_memory_expires(self):
        mem = CognitiveMemory(project_name="test")
        # Store with explicit expiry in the past.
        entry = MemoryEntry(key="temp", category="working", content="temporary data",
                            expires_at=time.time() - 1)
        mem._stores["working"].append(entry)
        entries = mem.recall("working")
        self.assertEqual(len(entries), 0)

    def test_clear_working(self):
        mem = CognitiveMemory(project_name="test")
        mem.store("working", "a", "data a")
        mem.store("working", "b", "data b")
        cleared = mem.clear_working()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(mem.recall("working")), 0)

    def test_project_persistent(self):
        mem = CognitiveMemory(project_name="test")
        mem.store_architecture_decision("use SQLite", "fast and embedded")
        entries = mem.recall_all("project")
        self.assertGreaterEqual(len(entries), 1)
        self.assertEqual(entries[0].category, "project")

    def test_episodic_pruning(self):
        mem = CognitiveMemory(project_name="test")
        # Cap at 5 for this test by monkey-patching the instance.
        mem._EPISODIC_MAX = 5  # type: ignore[misc]
        for i in range(10):
            mem.store_episode(f"run_{i}", "passed", strategy_used="mode_a")
        entries = mem.recall_all("episodic")
        self.assertLessEqual(len(entries), 5)

    def test_summary(self):
        mem = CognitiveMemory(project_name="test")
        mem.store("working", "k1", "content")
        mem.store("project", "k2", "content")
        summary = mem.summary()
        self.assertEqual(summary["working"]["count"], 1)
        self.assertEqual(summary["project"]["count"], 1)


class TestStrategyRouter(unittest.TestCase):
    def test_selects_mode_a_for_simple_task(self):
        router = StrategyRouter()
        task = Task(task_id="t1", description="simple task", difficulty=1)
        strategy, reason = router.select_strategy(task)
        self.assertEqual(strategy, Strategy.SINGLE_MODEL_MULTI_ROLE)

    def test_trace_recording(self):
        router = StrategyRouter()
        task = Task(task_id="t1", description="task")
        trace = router.build_trace("run1", task, Strategy.SINGLE_MODEL_MULTI_ROLE, "default")
        self.assertEqual(trace.run_id, "run1")
        self.assertEqual(trace.task_id, "t1")
        self.assertEqual(trace.strategy_chosen, Strategy.SINGLE_MODEL_MULTI_ROLE)

    def test_record_decision(self):
        trace = OrchestrationTrace(run_id="r1", task_id="t1",
                                   strategy_chosen=Strategy.SEQUENTIAL)
        trace.record_decision("route_choice", {"reason": "simple task"})
        self.assertEqual(len(trace.decisions), 1)
        self.assertEqual(trace.decisions[0]["type"], "route_choice")

    def test_select_best_branch(self):
        router = StrategyRouter()
        branches = [
            Branch(branch_id="b1", task_id="t1", status=BranchStatus.EVALUATED,
                   evaluation={"validation_passed": False},
                   result=AgentResult(run_id="r1", task_id="t1", strategy=Strategy.DIVERGENT,
                                      tokens_total=5000)),
            Branch(branch_id="b2", task_id="t1", status=BranchStatus.EVALUATED,
                   evaluation={"validation_passed": True},
                   result=AgentResult(run_id="r1", task_id="t1", strategy=Strategy.DIVERGENT,
                                      tokens_total=3000)),
        ]
        trace = OrchestrationTrace(run_id="r1", task_id="t1",
                                   strategy_chosen=Strategy.DIVERGENT)
        result = router.select_best_branch(branches, trace)
        self.assertEqual(result.selected_branch_id, "b2")
        self.assertTrue(result.validation_passed)

    def test_select_best_branch_no_evaluated(self):
        router = StrategyRouter()
        branches = [
            Branch(branch_id="b1", task_id="t1", status=BranchStatus.PENDING),
        ]
        trace = OrchestrationTrace(run_id="r1", task_id="t1",
                                   strategy_chosen=Strategy.DIVERGENT)
        result = router.select_best_branch(branches, trace)
        self.assertEqual(result.integration_method, "rollback")


class TestBenchmarkRunner(unittest.TestCase):
    def test_run_condition_collects_metrics(self):
        runner = BenchmarkRunner(benchmark_id="test_bench")
        task = Task(task_id="t1", description="simple math", difficulty=1)
        runner.register_tasks([task])

        def fake_executor(task):
            return AgentResult(
                run_id="r1", task_id=task.task_id,
                strategy=Strategy.SINGLE_MODEL_MULTI_ROLE,
                final_output="42", tokens_total=100, duration_seconds=1.0,
                validation_result=ValidationResult.PASS,
            )

        metrics = runner.run_condition("C", fake_executor)
        self.assertEqual(metrics.tasks_run, 1)
        self.assertEqual(metrics.tasks_passed, 1)
        self.assertEqual(metrics.success_rate, 1.0)

    def test_export_json(self):
        runner = BenchmarkRunner(benchmark_id="json_test")
        task = Task(task_id="t1", description="task")
        runner.register_tasks([task])

        def good_executor(task):
            return AgentResult(run_id="r1", task_id=task.task_id,
                               strategy=Strategy.SINGLE_MODEL_MULTI_ROLE,
                               final_output="ok", tokens_total=50,
                               duration_seconds=0.5, validation_result=ValidationResult.PASS)

        def bad_executor(task):
            return AgentResult(run_id="r2", task_id=task.task_id,
                               strategy=Strategy.SINGLE_MODEL_MULTI_ROLE,
                               final_output="", tokens_total=200,
                               duration_seconds=2.0, validation_result=ValidationResult.FAIL)

        runner.run_condition("C", good_executor)
        runner.run_condition("D", bad_executor)
        result = runner.finalize()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            result.export_json(path)
            data = json.loads(path.read_text())
            self.assertEqual(data["benchmark_id"], "json_test")
            self.assertIn("C", data["conditions"])
            self.assertIn("D", data["conditions"])
            self.assertGreaterEqual(len(data["pairwise_comparisons"]), 1)
        finally:
            path.unlink(missing_ok=True)

    def test_export_csv(self):
        runner = BenchmarkRunner(benchmark_id="csv_test")
        task = Task(task_id="t1", description="task")
        runner.register_tasks([task])

        def executor(task):
            return AgentResult(run_id="r1", task_id=task.task_id,
                               strategy=Strategy.SINGLE_MODEL_MULTI_ROLE,
                               final_output="ok", tokens_total=50,
                               duration_seconds=0.5, validation_result=ValidationResult.PASS)

        runner.run_condition("A", executor)
        result = runner.finalize()

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = Path(f.name)
        try:
            result.export_csv(path)
            text = path.read_text()
            self.assertIn("condition_id", text)
            self.assertIn("A", text)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
