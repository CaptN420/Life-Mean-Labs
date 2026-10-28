"""MultiRoleOrchestrator — Mode A: Single Model Multi-Role.

Chains PLANNER → DEVELOPER → CRITIC → REVIEWER → JUDGE over a single LLM
instance, sharing structured context between roles via CognitiveMemory.

Design rules (spec):
  - Shared context is STRUCTURED and BOUNDED by token budget — never the full
    conversation history.
  - Each role has a configurable token budget; unused tokens may be reallocated
    to subsequent roles without exceeding the global budget.
  - CRITIC and REVIEWER use DISTINCT criteria (diagnosis vs quality assessment).
  - Corrective loop is BOUNDED by max_retry_attempts (default 3).
  - JUDGE prioritizes deterministic evidence over semantic opinion.
  - Roles that add no measurable value may be DISABLED at runtime.
  - Every transition, token consumption, and decision is recorded in
    OrchestrationTrace.
  - The existing CodeLabEngine pipeline remains the fallback on controlled failure.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import (
    AgentResult,
    AgentType,
    OrchestrationTrace,
    Strategy,
    StepResult,
    Task,
    ValidationResult,
)
from .memory import CognitiveMemory
from .router import StrategyRouter

logger = logging.getLogger("Life_mean.Orchestrator.MultiRole")


# ── Default role token budgets (tokens) ──────────────────────────────────────


_DEFAULT_ROLE_BUDGETS: Dict[str, int] = {
    "PLANNER": 1024,
    "DEVELOPER": 4096,
    "CRITIC": 2048,
    "REVIEWER": 1024,
    "JUDGE": 1024,
}

# Roles that may be skipped when the task is simple (difficulty <= 1).
_LIGHT_ROLES = {"REVIEWER", "JUDGE"}


@dataclass
class RoleBudget:
    """Per-role token budget with reallocation support."""
    role: str
    allocated: int
    used: int = 0
    remaining: int = 0

    def mark_used(self, tokens: int) -> None:
        self.used += tokens
        self.remaining = max(0, self.allocated - self.used)

    def surplus(self) -> int:
        return self.allocated - self.used


@dataclass
class RoleContext:
    """Structured shared context between roles."""
    plan_summary: str = ""
    source_code: str = ""
    test_code: str = ""
    pytest_output: str = ""
    critic_diagnosis: str = ""
    reviewer_verdict: str = ""
    judge_notes: str = ""
    iteration: int = 0
    errors_accumulated: List[str] = field(default_factory=list)

    def to_context_snippet(self, max_chars: int = 512) -> str:
        """Compact snippet for injecting into the next role's prompt."""
        parts = []
        if self.plan_summary:
            parts.append(f"PLAN: {self.plan_summary[:max_chars]}")
        if self.source_code:
            parts.append(f"CODE: {self.source_code[:max_chars]}")
        if self.pytest_output:
            parts.append(f"TESTS: {self.pytest_output[:max_chars]}")
        if self.critic_diagnosis:
            parts.append(f"CRITIC: {self.critic_diagnosis[:max_chars]}")
        if self.errors_accumulated:
            parts.append(f"ERRORS: {'; '.join(self.errors_accumulated[-3:])[:max_chars]}")
        return "\n".join(parts) if parts else "(no prior context)"


class MultiRoleOrchestrator:
    """Mode A: Single Model Multi-Role orchestration.

    Chains PLANNER → DEVELOPER → (pytest) → CRITIC/REPAIR → REVIEWER → JUDGE
    over a single LLM instance with shared structured context and per-role
    token budgets.
    """

    def __init__(
        self,
        llm_executor: Callable[[str, str, int, float], Dict[str, Any]],
        test_executor: Optional[Callable[[str, str], Dict[str, Any]]] = None,
        global_token_budget: int = 16384,
        max_retry_attempts: int = 3,
        enable_reviewer: bool = True,
        enable_judge: bool = True,
        memory_project_name: str = "multi_role_orchestrator",
    ) -> None:
        """
        Args:
            llm_executor: Callable(prompt, system_prompt, max_tokens, temperature) -> {response, tokens, duration, error}
            test_executor: Callable(source, tests) -> {passed, output, returncode} — deterministic pytest wrapper
            global_token_budget: Total tokens available for the entire run
            max_retry_attempts: Max corrective loop iterations (CRITIC→DEVELOPER)
            enable_reviewer: Whether to run REVIEWER after tests pass
            enable_judge: Whether to run JUDGE after tests pass
            memory_project_name: Project name for CognitiveMemory
        """
        self.llm_executor = llm_executor
        self.test_executor = test_executor or self._default_test_executor
        self.global_token_budget = global_token_budget
        self.max_retry_attempts = max_retry_attempts
        self.enable_reviewer = enable_reviewer
        self.enable_judge = enable_judge
        self.memory = CognitiveMemory(project_name=memory_project_name)

        # Per-role token budgets.
        self._role_budgets: Dict[str, RoleBudget] = {}
        self._setup_budgets()

    def _setup_budgets(self) -> None:
        """Initialize per-role token budgets from global budget."""
        total_allocated = sum(_DEFAULT_ROLE_BUDGETS.values())
        scale = self.global_token_budget / total_allocated if total_allocated > 0 else 1.0
        for role, base in _DEFAULT_ROLE_BUDGETS.items():
            allocated = int(base * scale)
            self._role_budgets[role] = RoleBudget(role=role, allocated=allocated, remaining=allocated)

    def run(self, task: Task, run_id: Optional[str] = None) -> tuple[AgentResult, OrchestrationTrace]:
        """Execute the multi-role pipeline for a task.

        Returns (result, trace). The trace records every decision, transition,
        token consumption, and failure for post-hoc analysis.
        """
        run_id = run_id or f"mr_{uuid.uuid4().hex[:8]}"
        trace = OrchestrationTrace(
            run_id=run_id,
            task_id=task.task_id,
            strategy_chosen=Strategy.SINGLE_MODEL_MULTI_ROLE,
            reason="Mode A: single model multi-role chaining",
        )
        result = AgentResult(run_id=run_id, task_id=task.task_id, strategy=Strategy.SINGLE_MODEL_MULTI_ROLE)
        ctx = RoleContext()
        t_start = time.time()
        total_tokens = 0

        # ── PLANNER ────────────────────────────────────────────────────────
        budget = self._role_budgets["PLANNER"]
        plan_resp = self._call_role(
            role="PLANNER",
            prompt=self._plan_prompt(task.description, task.domain),
            max_tokens=budget.remaining,
            trace=trace,
        )
        if plan_resp.get("error"):
            trace.record_decision("planner_failed", {"error": plan_resp["error"]})
            result.metadata["status"] = "planner_failed"
            result.validation_result = ValidationResult.FAIL
            return result, trace
        ctx.plan_summary = plan_resp.get("response", "")[:512]
        plan_tokens = plan_resp.get("tokens", 0)
        budget.mark_used(plan_tokens)
        total_tokens += plan_tokens
        result.steps.append(StepResult(
            step_index=len(result.steps), agent_type=AgentType.PLANNER,
            input_summary=task.description[:100], output=ctx.plan_summary,
            tokens_consumed=plan_tokens, duration_seconds=plan_resp.get("duration", 0),
        ))
        self.memory.store("working", "plan", ctx.plan_summary, source_run_id=run_id)
        trace.record_decision("planner_done", {"tokens": plan_tokens, "summary_len": len(ctx.plan_summary)})

        # ── DEVELOPER ──────────────────────────────────────────────────────
        budget = self._role_budgets["DEVELOPER"]
        dev_resp = self._call_role(
            role="DEVELOPER",
            prompt=self._develop_prompt(task.description, ctx.plan_summary, task.metadata.get("language", "Python")),
            max_tokens=budget.remaining,
            trace=trace,
        )
        if dev_resp.get("error"):
            trace.record_decision("developer_failed", {"error": dev_resp["error"]})
            result.metadata["status"] = "developer_failed"
            return result, trace
        ctx.source_code = dev_resp.get("response", "")
        dev_tokens = dev_resp.get("tokens", 0)
        budget.mark_used(dev_tokens)
        total_tokens += dev_tokens
        result.steps.append(StepResult(
            step_index=len(result.steps), agent_type=AgentType.DEVELOPER,
            input_summary=ctx.plan_summary[:100], output=ctx.source_code[:200],
            tokens_consumed=dev_tokens, duration_seconds=dev_resp.get("duration", 0),
        ))
        self.memory.store("working", "source", ctx.source_code[:1024], source_run_id=run_id)
        trace.record_decision("developer_done", {"tokens": dev_tokens})

        # ── TEST EXECUTION ─────────────────────────────────────────────────
        test_resp = self.test_executor(ctx.source_code, "")
        ctx.pytest_output = test_resp.get("output", "")
        tests_passed = test_resp.get("passed", False)
        trace.record_decision("tests_executed", {"passed": tests_passed, "output_len": len(ctx.pytest_output)})

        # ── CORRECTIVE LOOP (CRITIC → DEVELOPER) ─────────────────────────
        retry_count = 0
        while not tests_passed and retry_count < self.max_retry_attempts:
            retry_count += 1
            budget = self._role_budgets["CRITIC"]
            crit_resp = self._call_role(
                role="CRITIC",
                prompt=self._critique_prompt(ctx.source_code, ctx.pytest_output),
                max_tokens=budget.remaining,
                trace=trace,
            )
            if crit_resp.get("error"):
                trace.record_decision("critic_failed", {"error": crit_resp["error"], "retry": retry_count})
                ctx.errors_accumulated.append(f"critic_error_{retry_count}: {crit_resp.get('error')}")
                break
            ctx.critic_diagnosis = crit_resp.get("response", "")[:512]
            crit_tokens = crit_resp.get("tokens", 0)
            budget.mark_used(crit_tokens)
            total_tokens += crit_tokens

            # Reallocate critic surplus to developer.
            self._reallocate_surplus("CRITIC", "DEVELOPER")

            # DEVELOPER retry with critique context.
            dev_budget = self._role_budgets["DEVELOPER"]
            dev_resp = self._call_role(
                role="DEVELOPER",
                prompt=self._develop_prompt(task.description, ctx.plan_summary, task.metadata.get("language", "Python"),
                                              critique=ctx.critic_diagnosis),
                max_tokens=dev_budget.remaining,
                trace=trace,
            )
            if dev_resp.get("error"):
                trace.record_decision("developer_retry_failed", {"error": dev_resp["error"], "retry": retry_count})
                ctx.errors_accumulated.append(f"developer_retry_error_{retry_count}")
                break
            ctx.source_code = dev_resp.get("response", "")
            dev_tokens = dev_resp.get("tokens", 0)
            dev_budget.mark_used(dev_tokens)
            total_tokens += dev_tokens
            result.steps.append(StepResult(
                step_index=len(result.steps), agent_type=AgentType.DEVELOPER,
                input_summary=f"retry_{retry_count}", output=ctx.source_code[:200],
                tokens_consumed=dev_tokens, duration_seconds=dev_resp.get("duration", 0),
                metadata={"retry": retry_count, "critique": ctx.critic_diagnosis[:100]},
            ))

            # Re-test.
            test_resp = self.test_executor(ctx.source_code, "")
            ctx.pytest_output = test_resp.get("output", "")
            tests_passed = test_resp.get("passed", False)
            ctx.iteration = retry_count
            trace.record_decision(f"retry_{retry_count}", {"passed": tests_passed})

        # ── REVIEWER (optional, after tests pass) ────────────────────────
        if tests_passed and self.enable_reviewer:
            budget = self._role_budgets["REVIEWER"]
            rev_resp = self._call_role(
                role="REVIEWER",
                prompt=self._review_prompt(ctx.source_code, ctx.pytest_output),
                max_tokens=budget.remaining,
                trace=trace,
            )
            if not rev_resp.get("error"):
                ctx.reviewer_verdict = rev_resp.get("response", "")[:512]
                rev_tokens = rev_resp.get("tokens", 0)
                budget.mark_used(rev_tokens)
                total_tokens += rev_tokens
                result.steps.append(StepResult(
                    step_index=len(result.steps), agent_type=AgentType.REVIEWER,
                    input_summary="post-test review", output=ctx.reviewer_verdict,
                    tokens_consumed=rev_tokens, duration_seconds=rev_resp.get("duration", 0),
                ))
                trace.record_decision("reviewer_done", {"tokens": rev_tokens, "verdict_len": len(ctx.reviewer_verdict)})
            else:
                trace.record_decision("reviewer_failed", {"error": rev_resp.get("error")})

        # ── JUDGE (optional, after tests pass) ───────────────────────────
        if tests_passed and self.enable_judge:
            budget = self._role_budgets["JUDGE"]
            judge_resp = self._call_role(
                role="JUDGE",
                prompt=self._judge_prompt(ctx.source_code, ctx.pytest_output, deterministic_valid=tests_passed),
                max_tokens=budget.remaining,
                trace=trace,
            )
            if not judge_resp.get("error"):
                ctx.judge_notes = judge_resp.get("response", "")[:512]
                judge_tokens = judge_resp.get("tokens", 0)
                budget.mark_used(judge_tokens)
                total_tokens += judge_tokens
                result.steps.append(StepResult(
                    step_index=len(result.steps), agent_type=AgentType.JUDGE,
                    input_summary="semantic judgment", output=ctx.judge_notes,
                    tokens_consumed=judge_tokens, duration_seconds=judge_resp.get("duration", 0),
                ))
                trace.record_decision("judge_done", {"tokens": judge_tokens})
            else:
                trace.record_decision("judge_failed", {"error": judge_resp.get("error")})

        # ── FINALIZE ───────────────────────────────────────────────────────
        result.final_output = ctx.source_code
        result.tokens_total = total_tokens
        result.duration_seconds = time.time() - t_start
        result.validation_result = ValidationResult.PASS if tests_passed else ValidationResult.FAIL
        trace.tokens_total = total_tokens
        trace.duration_seconds = result.duration_seconds
        trace.branches_created = 1
        trace.branches_evaluated = 1
        trace.branches_selected = 1

        # Store episodic memory.
        outcome = "passed" if tests_passed else f"failed_after_{retry_count}_retries"
        self.memory.store_episode(run_id, outcome,
                                   error="; ".join(ctx.errors_accumulated) if ctx.errors_accumulated else None,
                                   strategy_used="multi_role")

        return result, trace

    # ── LLM call helper ────────────────────────────────────────────────────

    def _call_role(self, role: str, prompt: str, max_tokens: int,
                   trace: OrchestrationTrace) -> Dict[str, Any]:
        """Call the LLM executor for a role with budget enforcement."""
        t0 = time.time()
        system_prompt = self._system_prompt(role)
        try:
            resp = self.llm_executor(prompt, system_prompt, max_tokens, 0.3)
            duration = time.time() - t0
            tokens = resp.get("tokens", 0)
            # Enforce budget: clamp tokens if over budget.
            if tokens > max_tokens:
                logger.warning("Role '%s' exceeded budget (%d > %d), clamping", role, tokens, max_tokens)
                tokens = max_tokens
            return {
                "response": resp.get("response", ""),
                "tokens": tokens,
                "duration": duration,
                "error": None,
            }
        except Exception as e:
            duration = time.time() - t0
            logger.warning("Role '%s' call failed: %s", role, e)
            return {"response": "", "tokens": 0, "duration": duration, "error": str(e)}

    def _reallocate_surplus(self, from_role: str, to_role: str) -> None:
        """Move unused tokens from one role's budget to another."""
        surplus = self._role_budgets[from_role].surplus()
        if surplus > 0:
            move = min(surplus, self._role_budgets[to_role].allocated - self._role_budgets[to_role].remaining)
            self._role_budgets[from_role].remaining -= move
            self._role_budgets[to_role].allocated += move
            logger.debug("Reallocated %d tokens from %s to %s", move, from_role, to_role)

    # ── Prompt builders ────────────────────────────────────────────────────

    @staticmethod
    def _system_prompt(role: str) -> str:
        prompts = {
            "PLANNER": "You are the PLANNER. Produce a concise build plan with files, API contract, and test cases.",
            "DEVELOPER": "You are the DEVELOPER. Emit ONLY valid Python source code between ```python ... ``` markers.",
            "CRITIC": "You are the CRITIC. Diagnose the ROOT CAUSE of test failures and propose a precise fix. Do NOT rewrite the entire file.",
            "REVIEWER": "You are the REVIEWER. Assess code quality (naming, edge cases, robustness). Verdict: PASS or FIX with specific reasons. You do NOT override deterministic tests.",
            "JUDGE": "You are the JUDGE. Assess semantic quality (naming, edge cases, robustness). Verdict + score 0-1 + notes. Deterministic tests are authoritative; you may not override them.",
        }
        return prompts.get(role, f"You are a coding assistant role: {role}.")

    def _plan_prompt(self, description: str, domain: str) -> str:
        return (f"Domain: {domain}\nTask: {description}\n\n"
                "Produce a concise build plan: files to create, function/API contract, "
                "and test cases. Return structured text with PLAN: and TESTS: sections.")

    def _develop_prompt(self, description: str, plan_summary: str, language: str,
                        critique: str = "") -> str:
        ctx = f"\nCritique to address:\n{critique}" if critique else ""
        return (f"Language: {language}\nTask: {description}\n\n"
                f"Plan summary:\n{plan_summary}{ctx}\n\n"
                "Emit the implementation module as a single ```python code block.")

    def _critique_prompt(self, source: str, pytest_output: str) -> str:
        return (f"SOURCE:\n```python\n{source}\n```\n\n"
                f"PYTEST OUTPUT:\n{pytest_output}\n\n"
                "Diagnose the ROOT CAUSE of the failure. Output a precise patch description "
                "and the corrected function(s) ONLY between ```python ... ``` markers.")

    def _review_prompt(self, source: str, pytest_output: str) -> str:
        return (f"SOURCE:\n```python\n{source}\n```\n\n"
                f"pytest: {pytest_output}\n\n"
                "Assess correctness and edge cases. Verdict: PASS or FIX with specific reasons. "
                "You do NOT outrank pytest.")

    def _judge_prompt(self, source: str, pytest_output: str, deterministic_valid: bool) -> str:
        return (f"Deterministic tests passed: {deterministic_valid}\n"
                f"SOURCE:\n```python\n{source}\n```\n\n"
                "Assess semantic quality. Verdict + score 0-1 + specific notes. "
                "Deterministic tests are the authority; you may not override them.")

    # ── Default test executor (for testing) ────────────────────────────────

    @staticmethod
    def _default_test_executor(source: str, tests: str) -> Dict[str, Any]:
        """Stub test executor for deterministic testing."""
        return {"passed": False, "output": "No test executor configured.", "returncode": 1}


# ── Convenience: build from existing CodeLabEngine ─────────────────────────


def build_from_code_lab_engine(engine, **kwargs) -> MultiRoleOrchestrator:
    """Wrap an existing CodeLabEngine's LLM path into a MultiRoleOrchestrator.

    Extracts the llm_executor signature from the engine's CodingMultiAgent
    (if available) and wires it into the orchestrator. Falls back to a stub
    if the engine has no live LLM backend.
    """
    def llm_wrap(prompt, system_prompt, max_tokens, temperature):
        # Try to delegate to the engine's multi-agent if available.
        ma = getattr(engine, '_coding_multi_agent', None)
        if ma is not None:
            # Map role from system prompt (best effort).
            role = "DEVELOPER"
            if "PLANNER" in system_prompt:
                role = "PLANNER"
            elif "CRITIC" in system_prompt:
                role = "CRITIC"
            elif "REVIEWER" in system_prompt:
                role = "REVIEWER"
            elif "JUDGE" in system_prompt:
                role = "JUDGE"
            try:
                if role == "PLANNER":
                    res = ma.plan(prompt, kwargs.get("language", "Python"))
                elif role == "DEVELOPER":
                    res = ma.develop(prompt, kwargs.get("language", "Python"))
                elif role == "CRITIC":
                    res = ma.critique(prompt, {}, kwargs.get("language", "Python"))
                elif role == "REVIEWER":
                    res = ma.review(prompt, "", {"passed": True})
                elif role == "JUDGE":
                    res = ma.judge(prompt, "", True)
                else:
                    res = {"response": "", "error": "unknown_role"}
                return {
                    "response": res.get("response", ""),
                    "tokens": len((res.get("response") or "").split()) * 4,
                    "duration": res.get("duration", 0),
                    "error": None if res.get("ok") else res.get("error"),
                }
            except Exception as e:
                return {"response": "", "tokens": 0, "duration": 0, "error": str(e)}
        # Fallback: stub.
        return {"response": f"[stub {kwargs.get('role', 'unknown')}] {prompt[:100]}",
                "tokens": 10, "duration": 0.001, "error": None}

    def test_wrap(source, tests):
        # Try to run real pytest if engine has workspace.
        ws = getattr(engine, 'ws', None)
        if ws is not None:
            import subprocess, sys
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
                    cwd=str(ws.workspace), capture_output=True, text=True,
                    timeout=kwargs.get("timeout", 60),
                )
                return {"passed": proc.returncode == 0, "output": (proc.stdout or "") + "\n" + (proc.stderr or ""),
                        "returncode": proc.returncode}
            except Exception:
                pass
        return {"passed": False, "output": "No workspace available.", "returncode": 1}

    return MultiRoleOrchestrator(
        llm_executor=llm_wrap,
        test_executor=test_wrap,
        **kwargs,
    )
