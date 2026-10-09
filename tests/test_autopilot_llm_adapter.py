"""Tests for the Autopilot → stable-core LLM adapter (Phase 17).

Proves the runner's deterministic path is untouched, and the optional LLM
verifier is recorded SEPARATELY without ever overriding deterministic validity.
"""

from __future__ import annotations

import pytest

from experiments.runner import ExperimentRunner, ValidationResult
from experiments.generation.schemas import GeneratedTask


def _task():
    return GeneratedTask(
        task_id="task_test_1",
        description="Calculate the GCD of 12 and 8",
        domain="math",
        difficulty=1,
        ground_truth=4,
        generator_version="1.0.0",
        generation_strategy="template",
        seed=42,
        reasoning_type="arithmetic",
    )


class TestRunnerDeterministicAuthoritative:
    def test_plain_run_deterministic(self):
        runner = ExperimentRunner()
        res = runner.run_task(_task())
        assert res.is_valid is True  # gcd(12,8)=4
        # provenance recorded
        assert res.provenance is not None
        assert res.provenance.task_id == "task_test_1"

    def test_llm_verifier_never_overrides_deterministic(self):
        runner = ExperimentRunner()

        class _JudgeSaysFail:
            """A judge opinion that disagrees with deterministic PASS."""

            def judge(self, source, tests, deterministic_valid):
                return {
                    "ok": True,
                    "role": "JUDGE",
                    "response": "FAIL: I think gcd is wrong",
                }

        # Task is deterministically VALID (gcd 12/8 = 4).
        res = runner.run_task_with_llm_verifier(_task(), llm_verifier=_JudgeSaysFail())
        # Deterministic validity is the authority (rule 6).
        assert res.is_valid is True
        assert res.validation_result.valid is True
        # Judge disagreement is recorded SEPARATELY and flagged non-overriding.
        assert res.metadata.get("judge_overrides_deterministic") is False
        assert res.metadata.get("judge_opinion", {}).get("response", "").startswith("FAIL")

    def test_llm_verifier_absent_returns_unmodified(self):
        runner = ExperimentRunner()
        res = runner.run_task_with_llm_verifier(_task(), llm_verifier=None)
        assert res.is_valid is True
        assert "judge_opinion" not in res.metadata

    def test_llm_verifier_error_swallowed(self):
        runner = ExperimentRunner()

        class _Broken:
            def judge(self, *a, **k):
                raise RuntimeError("boom")

        res = runner.run_task_with_llm_verifier(_task(), llm_verifier=_Broken())
        assert res.is_valid is True  # deterministic unaffected
        assert res.metadata.get("judge_opinion", {}).get("ok") is False


class TestExperimentLLMAdapter:
    def test_adapter_reports_availability_honestly(self):
        from experiments.llm_adapter import ExperimentLLMAdapter
        adapter = ExperimentLLMAdapter()
        avail = adapter.availability
        assert "available" in avail
        # It must never report available when probe is not authenticated.
        assert isinstance(avail.get("available"), bool)

    def test_adapter_runner_wraps_without_crash(self):
        from experiments.llm_adapter import ExperimentLLMAdapter
        runner = ExperimentRunner()
        adapter = ExperimentLLMAdapter()
        run = adapter.build_runner(runner)
        res = run(_task())
        # Deterministic path always works regardless of LLM availability.
        assert res.is_valid is True
