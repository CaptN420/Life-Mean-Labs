"""Tests for Phase 4D: Debate System, Strategy Learning, and Real Benchmark."""

import json
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from life_mean_lab.orchestrator import (
    ArgumentLedger,
    DebateEvent,
    DebateEventType,
    DebateExperimentRunner,
    DebateConfig,
    DebateCondition,
    EmergenceMeasures,
    StrategyLearning,
    TaskType,
    RealBenchmarkRunner,
    ExperimentConfig,
    MeasureType,
    MetricProvenance,
)
from life_mean_lab.orchestrator.models import Task, Strategy


class TestArgumentLedger(unittest.TestCase):
    """Tests for ArgumentLedger."""

    def test_record_argument(self):
        ledger = ArgumentLedger("test_debate")
        event = ledger.record(DebateEventType.ARGUMENT, "agent_1", "I agree with the proposition.")
        self.assertEqual(event.event_type, DebateEventType.ARGUMENT)
        self.assertEqual(event.agent_id, "agent_1")
        self.assertEqual(len(ledger.get_events_by_agent("agent_1")), 1)

    def test_record_objection(self):
        ledger = ArgumentLedger("test_debate")
        event = ledger.record(DebateEventType.OBJECTION, "agent_2", "That assumption is flawed.")
        self.assertEqual(event.event_type, DebateEventType.OBJECTION)
        self.assertEqual(len(ledger.get_events_by_type(DebateEventType.OBJECTION)), 1)

    def test_record_concession(self):
        ledger = ArgumentLedger("test_debate")
        event = ledger.record(DebateEventType.CONCESSION, "agent_1", "You make a valid point.")
        self.assertEqual(event.event_type, DebateEventType.CONCESSION)

    def test_position_change_tracking(self):
        ledger = ArgumentLedger("test_debate")
        ledger.record(DebateEventType.POSITION_CHANGE, "agent_1", "I now believe X.")
        changes = ledger.get_position_changes()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["agent_id"], "agent_1")

    def test_open_questions(self):
        ledger = ArgumentLedger("test_debate")
        ledger.record(DebateEventType.OPEN_QUESTION, "agent_2", "What about Y?")
        questions = ledger.get_open_questions()
        self.assertEqual(len(questions), 1)

    def test_summary(self):
        ledger = ArgumentLedger("test_debate")
        ledger.record(DebateEventType.ARGUMENT, "agent_1", "Argument 1")
        ledger.record(DebateEventType.ARGUMENT, "agent_2", "Argument 2")
        ledger.record(DebateEventType.OBJECTION, "agent_1", "Objection")
        summary = ledger.get_summary()
        self.assertEqual(summary["total_events"], 3)
        self.assertEqual(summary["event_type_counts"]["argument"], 2)
        self.assertEqual(summary["event_type_counts"]["objection"], 1)

    def test_export_json(self):
        ledger = ArgumentLedger("test_debate")
        ledger.record(DebateEventType.ARGUMENT, "agent_1", "Test argument")
        path = Path("/tmp/test_ledger.json")
        ledger.export_json(str(path))
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["debate_id"], "test_debate")
        self.assertEqual(len(data["events"]), 1)

    def test_exact_repetition_detection(self):
        ledger = ArgumentLedger("test_debate", detect_repetitions=True)
        ledger.record(DebateEventType.ARGUMENT, "agent_1", "Exact same argument")
        event = ledger.record(DebateEventType.ARGUMENT, "agent_1", "Exact same argument")
        self.assertTrue(event.metadata.get("is_repeated", False))


class TestDebateExperimentRunner(unittest.TestCase):
    """Tests for DebateExperimentRunner."""

    def test_run_with_stub_executor(self):
        runner = DebateExperimentRunner()
        config = DebateConfig(
            question="Is AI conscious?",
            num_agents=2,
            max_rounds=2,
            condition=DebateCondition.INDEPENDENT_AGENTS,
        )
        result = runner.run(config)
        self.assertIsNotNone(result)
        self.assertEqual(result.condition, DebateCondition.INDEPENDENT_AGENTS)
        self.assertGreaterEqual(result.ledger.get_summary()["total_events"], 2)

    def test_run_condition(self):
        runner = DebateExperimentRunner()
        result = runner.run_condition(
            DebateCondition.SHARED_MEMORY,
            "Should we regulate AI?",
            num_agents=3,
            max_rounds=3,
        )
        self.assertEqual(result.condition, DebateCondition.SHARED_MEMORY)

    def test_emergence_measures(self):
        runner = DebateExperimentRunner()
        config = DebateConfig(
            question="Test question",
            num_agents=2,
            max_rounds=2,
        )
        result = runner.run(config)
        measures = result.emergence_measures
        self.assertGreaterEqual(measures.argument_diversity, 0.0)
        self.assertLessEqual(measures.position_stability, 1.0)

    def test_export_results(self):
        runner = DebateExperimentRunner()
        config = DebateConfig(question="Test", num_agents=2, max_rounds=2)
        runner.run(config)
        path = Path("/tmp/test_debate_results.json")
        runner.export_results(str(path))
        self.assertTrue(path.exists())

    def test_real_llm_executor_integration(self):
        """Test with a mock LLM executor."""
        mock_executor = MagicMock(return_value={"response": "Mock response"})
        runner = DebateExperimentRunner(llm_executor=mock_executor)
        config = DebateConfig(
            question="Test",
            num_agents=1,
            max_rounds=1,
        )
        result = runner.run(config)
        self.assertTrue(result.success)


class TestStrategyLearning(unittest.TestCase):
    """Tests for StrategyLearning."""

    def test_record_and_recommend(self):
        learner = StrategyLearning()
        # Record some outcomes.
        for _ in range(10):
            learner.record(
                task_type=TaskType.SIMPLE,
                task_difficulty=1,
                strategy_used="sequential",
                models_used=["model_a"],
                tokens_consumed=100,
                duration_seconds=0.5,
                tests_passed=1,
                tests_total=1,
                success=True,
            )
        # Should have enough samples now.
        rec = learner.recommend(TaskType.SIMPLE, 1)
        self.assertIsNotNone(rec)

    def test_insufficient_samples(self):
        learner = StrategyLearning()
        learner.record(
            task_type=TaskType.COMPLEX,
            task_difficulty=4,
            strategy_used="divergence",
            models_used=["model_b"],
            tokens_consumed=500,
            duration_seconds=2.0,
            tests_passed=0,
            tests_total=1,
            success=False,
        )
        # Should not recommend with only 1 sample.
        rec = learner.recommend(TaskType.COMPLEX, 4)
        self.assertIsNone(rec)

    def test_learning_disabled(self):
        learner = StrategyLearning(enable_learning=False)
        learner.record(
            task_type=TaskType.SIMPLE,
            task_difficulty=1,
            strategy_used="sequential",
            models_used=[],
            tokens_consumed=50,
            duration_seconds=0.1,
            tests_passed=1,
            tests_total=1,
            success=True,
        )
        rec = learner.recommend(TaskType.SIMPLE, 1)
        self.assertIsNone(rec)

    def test_get_statistics(self):
        learner = StrategyLearning()
        learner.record(
            task_type=TaskType.MEDIUM,
            task_difficulty=2,
            strategy_used="multi_role",
            models_used=["model_a"],
            tokens_consumed=200,
            duration_seconds=1.0,
            tests_passed=1,
            tests_total=1,
            success=True,
        )
        stats = learner.get_statistics()
        self.assertEqual(stats["total_records"], 1)
        self.assertIn("multi_role", stats["strategy_stats"])

    def test_export_records(self):
        learner = StrategyLearning()
        learner.record(
            task_type=TaskType.SIMPLE,
            task_difficulty=1,
            strategy_used="direct",
            models_used=[],
            tokens_consumed=50,
            duration_seconds=0.2,
            tests_passed=1,
            tests_total=1,
            success=True,
        )
        path = Path("/tmp/test_strategy_records.json")
        learner.export_records(path)
        self.assertTrue(path.exists())


class TestRealBenchmarkRunner(unittest.TestCase):
    """Tests for RealBenchmarkRunner."""

    def test_run_experiment(self):
        runner = RealBenchmarkRunner()
        tasks = [Task(task_id="test_1", description="Write a function")]
        runner.register_tasks(tasks)

        def mock_executor(task):
            from life_mean_lab.orchestrator.models import AgentResult, ValidationResult
            return (
                AgentResult(
                    run_id="run_1",
                    task_id=task.task_id,
                    strategy=Strategy.SEQUENTIAL,
                    final_output="def foo(): pass",
                    tokens_total=100,
                    validation_result=ValidationResult.PASS,
                ),
                {
                    "tokens_input": 50,
                    "tokens_output": 50,
                    "latency_ms": 1500.0,
                    "measure_type": "estimated",
                    "token_source": "estimated",
                    "tests_passed": 1,
                    "tests_total": 1,
                    "model_used": "test-model",
                },
            )

        metrics = runner.run_condition("A", mock_executor)
        self.assertEqual(metrics.tasks_run, 1)
        self.assertEqual(metrics.tasks_passed, 1)

    def test_export_full_report(self):
        runner = RealBenchmarkRunner()
        tasks = [Task(task_id="test_1", description="Test task")]
        runner.register_tasks(tasks)

        def mock_executor(task):
            from life_mean_lab.orchestrator.models import AgentResult, ValidationResult
            return (
                AgentResult(
                    run_id="run_1",
                    task_id=task.task_id,
                    strategy=Strategy.SEQUENTIAL,
                    final_output="result",
                    tokens_total=100,
                    validation_result=ValidationResult.PASS,
                ),
                {"tokens_input": 50, "tokens_output": 50, "latency_ms": 1000.0, "measure_type": "measured", "tests_passed": 1, "tests_total": 1},
            )

        runner.run_condition("A", mock_executor)
        path = Path("/tmp/test_benchmark_report.json")
        runner.export_full_report(path)
        self.assertTrue(path.exists())

    def test_metric_provenance(self):
        measured = MetricProvenance(100, MeasureType.MEASURED, "engine")
        estimated = MetricProvenance(50, MeasureType.ESTIMATED, "calc")
        unavailable = MetricProvenance(0, MeasureType.UNAVAILABLE)

        self.assertEqual(measured.to_dict()["type"], "measured")
        self.assertEqual(estimated.to_dict()["type"], "estimated")
        self.assertEqual(unavailable.to_dict()["type"], "unavailable")


class TestSmokeTestRealDebate(unittest.TestCase):
    """Optional smoke test for real LLM debate.

    Run with: pytest tests/test_phase4d.py::TestSmokeTestRealDebate -v -s
    Requires a local LLM endpoint configured.
    """

    @unittest.skipIf(
        not __import__("os").environ.get("LIFE_MEAN_TEST_REAL_LLM"),
        "Skip real LLM smoke test (set LIFE_MEAN_TEST_REAL_LLM=1 to enable)",
    )
    def test_real_debate_with_local_model(self):
        """Smoke test: run a real debate with local model."""
        from life_mean_lab.orchestrator import RealLLMExecutor

        # Try to connect to local model.
        executor = RealLLMExecutor(
            base_url="http://localhost:1234/v1",
            api_key="test-key",
            default_model="llama-3.2-1b",
        )

        if not executor.is_available:
            self.skipTest("No local LLM available at configured endpoint")

        # Wrap to match expected signature (model, prompt, system_prompt, max_tokens, temperature).
        def llm_wrapper(model: str, prompt: str, system_prompt: str, max_tokens: int, temperature: float) -> dict:
            return executor._call_llm(prompt, max_tokens, temperature)

        runner = DebateExperimentRunner(llm_executor=llm_wrapper)
        config = DebateConfig(
            question="Is free will compatible with determinism?",
            num_agents=2,
            max_rounds=2,
            condition=DebateCondition.SHARED_MEMORY,
        )
        result = runner.run(config)

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.ledger.get_summary()["total_events"], 2)
        self.assertGreater(result.tokens_total, 0)


if __name__ == "__main__":
    unittest.main()
