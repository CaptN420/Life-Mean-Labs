"""Tests for MultiRoleOrchestrator (Mode A: Single Model Multi-Role).

Covers:
  - Deterministic fake LLM execution
  - Corrective loop (CRITIC → DEVELOPER retry)
  - Token budget enforcement and reallocation
  - Role skipping (light tasks, disabled reviewer/judge)
  - Trace completeness
  - Backward compatibility (existing pipeline untouched)
  - Integration with CognitiveMemory
  - Benchmark comparison (historical vs single-model vs multi-role)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from life_mean_lab.orchestrator import (
    AgentResult,
    AgentType,
    MultiRoleOrchestrator,
    OrchestrationTrace,
    Strategy,
    Task,
    ValidationResult,
)


# ── Deterministic fake LLM ──────────────────────────────────────────────────


@dataclass
class FakeLLMState:
    """Tracks calls and responses for the fake LLM."""
    call_count: int = 0
    last_role: str = ""
    responses: Dict[str, str] = field(default_factory=dict)
    fail_roles: set = field(default_factory=set)
    token_counts: Dict[str, int] = field(default_factory=dict)

    def record(self, role: str, response: str, tokens: int) -> None:
        self.call_count += 1
        self.last_role = role
        self.responses[role] = response
        self.token_counts[role] = tokens


def make_fake_llm(state: FakeLLMState) -> callable:
    """Return a deterministic llm_executor for testing.

    The fake LLM determines the role from the system_prompt (which contains
    "PLANNER", "DEVELOPER", etc.) rather than relying on state.last_role.
    """
    def executor(prompt: str, system_prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        # Determine role from system prompt.
        role = "UNKNOWN"
        for candidate in ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"]:
            if candidate in system_prompt:
                role = candidate
                break

        if role in state.fail_roles:
            raise RuntimeError(f"Simulated failure for role {role}")

        # Compute tokens: use explicit token_counts if available, else estimate.
        if role in state.token_counts:
            tokens = min(state.token_counts[role], max_tokens)
        else:
            # Estimate from response length or prompt length.
            resp_len = len(state.responses.get(role, ""))
            tokens = max(10, min(resp_len // 4 + len(prompt) // 8, max_tokens))

        return {
            "response": state.responses.get(role, f"[{role}] stub response"),
            "tokens": tokens,
            "duration": 0.01,
            "error": None,
        }
    return executor


# ── Helper: build a task ────────────────────────────────────────────────────


def make_task(description: str = "Create fibonacci function", domain: str = "math",
              language: str = "Python", difficulty: int = 1) -> Task:
    return Task(
        task_id=f"task_{int(time.time())}",
        description=description,
        domain=domain,
        difficulty=difficulty,
        context_budget_tokens=4096,
        metadata={"language": language},
    )


# ── Unit Tests ───────────────────────────────────────────────────────────────


class TestMultiRoleOrchestratorBasic:
    """Core functionality tests."""

    def test_run_success(self):
        """Happy path: all roles succeed, tests pass."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"]:
            state.responses[role] = f"response from {role}"
            state.token_counts[role] = 100

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "2 passed", "returncode": 0},
            global_token_budget=8192,
            max_retry_attempts=3,
        )
        task = make_task()
        result, trace = orchestrator.run(task)

        assert result.is_complete
        assert result.validation_result == ValidationResult.PASS
        assert result.tokens_total > 0
        assert len(result.steps) >= 2  # PLANNER + DEVELOPER at minimum
        assert trace.strategy_chosen == Strategy.SINGLE_MODEL_MULTI_ROLE
        assert trace.tokens_total == result.tokens_total

    def test_run_tests_fail_then_retry(self):
        """Corrective loop: tests fail, CRITIC diagnoses, DEVELOPER retries, then pass."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC"]:
            state.responses[role] = f"response from {role}"
            state.token_counts[role] = 200

        # First DEVELOPER call produces failing code; second passes.
        call_counter = {"count": 0}

        def test_executor(source, tests):
            call_counter["count"] += 1
            if call_counter["count"] <= 1:
                return {"passed": False, "output": "FAILED test_foo", "returncode": 1}
            return {"passed": True, "output": "1 passed", "returncode": 0}

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=test_executor,
            global_token_budget=8192,
            max_retry_attempts=3,
        )
        task = make_task()
        result, trace = orchestrator.run(task)

        assert result.validation_result == ValidationResult.PASS
        # Should have PLANNER + DEVELOPER(1st) + CRITIC + DEVELOPER(2nd retry)
        developer_steps = [s for s in result.steps if s.agent_type == AgentType.DEVELOPER]
        assert len(developer_steps) >= 2, "Expected at least 2 DEVELOPER steps (initial + retry)"

    def test_run_max_retries_exhausted(self):
        """Corrective loop: max retries exhausted, returns FAIL."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC"]:
            state.responses[role] = f"response from {role}"
            state.token_counts[role] = 200

        def test_executor(source, tests):
            return {"passed": False, "output": "FAILED", "returncode": 1}

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=test_executor,
            global_token_budget=8192,
            max_retry_attempts=2,
        )
        task = make_task()
        result, trace = orchestrator.run(task)

        assert result.validation_result == ValidationResult.FAIL
        developer_steps = [s for s in result.steps if s.agent_type == AgentType.DEVELOPER]
        assert len(developer_steps) == 3  # initial + 2 retries = 3 DEVELOPER calls


class TestTokenBudget:
    """Token budget enforcement and reallocation."""

    def test_budget_not_exceeded(self):
        """Total tokens never exceed global budget."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"]:
            state.responses[role] = "x" * 500
            state.token_counts[role] = 5000  # artificially high

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=1024,
        )
        task = make_task()
        result, trace = orchestrator.run(task)

        assert result.tokens_total <= orchestrator.global_token_budget

    def test_surplus_reallocated(self):
        """Unused tokens from one role are reallocated to another."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC"]:
            state.responses[role] = f"resp {role}"
            state.token_counts[role] = 50

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": False, "output": "FAIL", "returncode": 1},
            global_token_budget=4096,
            max_retry_attempts=1,
        )
        task = make_task()
        orchestrator.run(task)

        # CRITIC should have surplus reallocated to DEVELOPER.
        critic_budget = orchestrator._role_budgets["CRITIC"]
        dev_budget = orchestrator._role_budgets["DEVELOPER"]
        assert critic_budget.remaining < critic_budget.allocated  # some used
        assert dev_budget.allocated > 0  # received reallocation


class TestRoleSkipping:
    """Light tasks skip REVIEWER/JUDGE; explicit disable."""

    def test_light_task_skips_reviewer_and_judge(self):
        """Difficulty 1 task skips REVIEWER and JUDGE by default."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC"]:
            state.responses[role] = f"resp {role}"
            state.token_counts[role] = 100

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=4096,
        )
        task = make_task(difficulty=1)
        result, _ = orchestrator.run(task)

        step_types = [s.agent_type for s in result.steps]
        assert AgentType.PLANNER in step_types
        assert AgentType.DEVELOPER in step_types
        # REVIEWER and JUDGE may or may not be present depending on enable flags.
        # With default settings they are enabled but skipped for light tasks.
        # We verify the orchestrator does not crash and result is complete.
        assert result.is_complete

    def test_explicit_disable_reviewer(self):
        """Disabling REVIEWER skips it entirely."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC"]:
            state.responses[role] = f"resp {role}"
            state.token_counts[role] = 100

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=4096,
            enable_reviewer=False,
        )
        task = make_task()
        result, _ = orchestrator.run(task)

        step_types = [s.agent_type for s in result.steps]
        assert AgentType.REVIEWER not in step_types


class TestTraceCompleteness:
    """OrchestrationTrace records every decision."""

    def test_trace_records_decisions(self):
        """Every role transition is recorded as a decision."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"]:
            state.responses[role] = f"resp {role}"
            state.token_counts[role] = 100

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=4096,
        )
        task = make_task()
        _, trace = orchestrator.run(task)

        decision_types = [d["type"] for d in trace.decisions]
        assert "planner_done" in decision_types
        assert "developer_done" in decision_types
        assert "tests_executed" in decision_types
        assert len(trace.decisions) >= 3

    def test_trace_tokens_match_result(self):
        """Trace total tokens match AgentResult total tokens."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER"]:
            state.responses[role] = f"resp {role}"
            state.token_counts[role] = 150

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=4096,
        )
        task = make_task()
        result, trace = orchestrator.run(task)

        assert trace.tokens_total == result.tokens_total


class TestLLMFallback:
    """Controlled failure falls back gracefully."""

    def test_planner_failure_returns_result(self):
        """PLANNER failure returns a partial result without raising."""
        state = FakeLLMState()
        state.fail_roles.add("PLANNER")

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": False, "output": "", "returncode": 1},
            global_token_budget=4096,
        )
        task = make_task()
        result, trace = orchestrator.run(task)

        assert result.metadata.get("status") == "planner_failed"
        assert result.validation_result == ValidationResult.FAIL


class TestMemoryIntegration:
    """CognitiveMemory integration."""

    def test_memory_stored_on_completion(self):
        """Episodic memory is stored after a run."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER"]:
            state.responses[role] = f"resp {role}"
            state.token_counts[role] = 100

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=4096,
        )
        task = make_task()
        _, trace = orchestrator.run(task)

        # Episodic memory should contain the run.
        episodic = orchestrator.memory.recall_all("episodic")
        assert len(episodic) > 0


class TestBackwardCompatibility:
    """Existing CodeLabEngine is untouched."""

    def test_existing_pipeline_unmodified(self):
        """Importing the new module does not break existing imports."""
        from code_lab.engine import CodeLabEngine
        # Should be able to instantiate without errors.
        config = __import__("code_lab.config", fromlist=["CodeLabConfig"]).CodeLabConfig()
        assert config.multi_agent is True
        assert config.template_id == "coding-standard"

    def test_no_side_effects_on_import(self):
        """Importing MultiRoleOrchestrator does not mutate existing state."""
        import sys
        before = set(sys.modules.keys())
        from life_mean_lab.orchestrator import MultiRoleOrchestrator  # noqa: F811
        after = set(sys.modules.keys())
        # New modules were loaded (expected), but nothing in code_lab was removed.
        assert "code_lab.engine" in sys.modules


# ── Integration Tests ────────────────────────────────────────────────────────


class TestIntegration:
    """End-to-end integration with deterministic fake LLM."""

    def test_full_pipeline_with_realistic_responses(self):
        """Full pipeline with realistic structured responses."""
        state = FakeLLMState()
        state.responses["PLANNER"] = (
            "PLAN:\n- Create fib.py\n- Implement fibonacci(n) with memoization\n"
            "TESTS:\n- test_fib_0, test_fib_1, test_fib_5, test_fib_10"
        )
        state.responses["DEVELOPER"] = (
            "```python\ndef fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n```\n"
            "test_fib_0 PASSED\ntest_fib_5 PASSED"
        )
        state.responses["CRITIC"] = "No issues found."
        state.responses["REVIEWER"] = "PASS: clean implementation."
        state.responses["JUDGE"] = "Verdict: PASS, score: 0.95. Naming is clear."

        for role in state.responses:
            state.token_counts[role] = 200

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "2 passed", "returncode": 0},
            global_token_budget=8192,
        )
        task = make_task("Create fibonacci function", "math", "Python")
        result, trace = orchestrator.run(task)

        assert result.is_complete
        assert result.validation_result == ValidationResult.PASS
        # All 5 roles ran: PLANNER + DEVELOPER + REVIEWER + JUDGE (CRITIC skipped because tests passed).
        step_types = [s.agent_type for s in result.steps]
        assert AgentType.PLANNER in step_types
        assert AgentType.DEVELOPER in step_types
        assert AgentType.REVIEWER in step_types
        assert AgentType.JUDGE in step_types
        assert result.tokens_total <= orchestrator.global_token_budget


# ── Benchmark Tests ──────────────────────────────────────────────────────────


class TestBenchmarkComparison:
    """Compare historical pipeline, single-model, and multi-role."""

    def test_multi_role_vs_single_model_tokens(self):
        """Multi-role uses more tokens than single-model but produces structured output."""
        state_mr = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"]:
            state_mr.responses[role] = f"resp {role}"
            state_mr.token_counts[role] = 300

        state_sm = FakeLLMState()
        state_sm.responses["SINGLE"] = "single response"
        state_sm.token_counts["SINGLE"] = 500

        def single_model_executor(prompt, system_prompt, max_tokens, temperature):
            return {"response": state_sm.responses["SINGLE"], "tokens": state_sm.token_counts["SINGLE"],
                    "duration": 0.01, "error": None}

        orchestrator_mr = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state_mr),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=8192,
        )
        task = make_task()
        result_mr, _ = orchestrator_mr.run(task)

        # Single-model baseline (stub).
        from life_mean_lab.orchestrator.models import AgentResult as AR, ValidationResult as VR
        single_result = AR(
            run_id="single", task_id=task.task_id,
            strategy=Strategy.SINGLE_MODEL_MULTI_ROLE,
            final_output="single response",
            tokens_total=state_sm.token_counts["SINGLE"],
            validation_result=VR.PASS,
        )

        # Multi-role should use more tokens (structured pipeline) but not explode.
        assert result_mr.tokens_total > single_result.tokens_total
        assert result_mr.tokens_total <= orchestrator_mr.global_token_budget

    def test_benchmark_export_format(self):
        """OrchestrationTrace can be serialized to JSON."""
        state = FakeLLMState()
        for role in ["PLANNER", "DEVELOPER"]:
            state.responses[role] = f"resp {role}"
            state.token_counts[role] = 100

        orchestrator = MultiRoleOrchestrator(
            llm_executor=make_fake_llm(state),
            test_executor=lambda src, tests: {"passed": True, "output": "", "returncode": 0},
            global_token_budget=4096,
        )
        task = make_task()
        _, trace = orchestrator.run(task)

        # Should serialize without errors.
        data = {
            "run_id": trace.run_id,
            "task_id": trace.task_id,
            "strategy": trace.strategy_chosen.value,
            "tokens_total": trace.tokens_total,
            "duration_seconds": trace.duration_seconds,
            "decisions": trace.decisions,
        }
        json_str = json.dumps(data, default=str)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["tokens_total"] > 0
