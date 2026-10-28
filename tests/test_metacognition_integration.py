"""Quick integration test for metacognitive memory in engine."""

from pathlib import Path
import tempfile

from code_lab.config import CodeLabConfig
from code_lab.engine import CodeLabEngine


def test_engine_saves_metacognitive_memory() -> None:
    """Verify the engine saves run memory to the metacognitive store."""
    import os
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            os.chdir(tmpdir)

            config = CodeLabConfig(
                prompt="Create a function fibonacci(n) with unit tests.",
                project_name="test_project",
                run_id="integration_test_run",
            )

            engine = CodeLabEngine(config=config)
            engine.router = None  # No router for this test

            # Simulate a completed run result
            result = {
                "run_id": "integration_test_run",
                "project": "test_project",
                "status": "passed",
                "plan": {"plan_id": "fibonacci", "params": {"source_target": "main"}},
                "agent_trace": [{"agent": "PLANNER", "ok": True}],
                "semantic_judge": {
                    "status": "UNAVAILABLE",
                    "reason": "llm_backend_unavailable",
                },
                "iterations": [
                    {"iteration": 1, "pytest": {"passed_count": 5, "total": 5}}
                ],
                "errors": [],
                "duration": 1.5,
            }

            # Call the method directly
            engine._save_metacognitive_memory(result)

            # Verify memory was saved to default path
            from experiments.metacognition import MetacognitiveMemory

            storage_path = Path("data") / "metacognition" / "memory.json"
            mem_store = MetacognitiveMemory(storage_path=storage_path)
            memory = mem_store.get_run_memory("integration_test_run")

            assert memory is not None
            assert memory.run_id == "integration_test_run"
            assert memory.status == "passed"
            assert memory.domain == "coding"
            assert memory.classification == "fibonacci"
            assert len(memory.agent_traces) == 1
            assert memory.duration_seconds == 1.5
        finally:
            os.chdir(original_cwd)


def test_engine_handles_missing_memory_module() -> None:
    """Verify graceful degradation if metacognitive module is unavailable."""
    config = CodeLabConfig(
        prompt="Test prompt",
        project_name="test_project",
        run_id="graceful_test_run",
    )

    engine = CodeLabEngine(config=config)

    # Simulate a result - should not raise
    result = {
        "run_id": "graceful_test_run",
        "project": "test_project",
        "status": "failed",
        "plan": None,
        "agent_trace": [],
        "semantic_judge": {},
        "iterations": [],
        "errors": [{"type": "test_error", "description": "Test failed"}],
        "duration": 0.5,
    }

    # This should not raise even if module import fails
    engine._save_metacognitive_memory(result)
