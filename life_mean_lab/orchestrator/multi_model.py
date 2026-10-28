"""MultiModelOrchestrator — Mode B: Multi-Model Collaboration.

Multiple local or remote models collaborate on a task, communicating via
structured objects (Task, AgentResult, Branch, OrchestrationTrace) rather
than full conversations.

Design rules:
  - Each model is assigned a role based on its capabilities.
  - Results are structured artefacts with provenance, not raw text dumps.
  - Independent tasks run in parallel within resource constraints.
  - Failed models trigger fallback to Mode A or another available model.
  - Every decision is recorded in OrchestrationTrace.
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import (
    AgentResult,
    AgentType,
    Branch,
    BranchStatus,
    ConvergenceResult,
    OrchestrationTrace,
    Strategy,
    StepResult,
    Task,
    ValidationResult,
)
from .model_registry import ModelHealth, ModelProvider, ModelRegistry, ModelSpec
from .scheduler import ParallelScheduler, TaskDependency, TaskResult
from .multi_role import MultiRoleOrchestrator
from .workspace_manager import WorkspaceManager, BranchInfo, WorkspaceBranchStatus, TestResult

logger = logging.getLogger("Life_mean.Orchestrator.MultiModel")


# ── Collaboration protocol ───────────────────────────────────────────────────


class MessageKind(str, enum.Enum):
    """Type of message exchanged between collaborating agents."""
    PLAN = "plan"
    CODE = "code"
    CRITIQUE = "critique"
    REVIEW = "review"
    JUDGMENT = "judgment"
    ERROR = "error"
    DEPENDENCY_READY = "dependency_ready"


@dataclass
class CollaborationMessage:
    """Structured message between collaborating agents."""
    kind: MessageKind
    sender_model_id: str
    sender_role: str
    content: str
    artefacts: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "sender_model_id": self.sender_model_id,
            "sender_role": self.sender_role,
            "content_len": len(self.content),
            "artefacts": self.artefacts,
            "dependencies": self.dependencies,
            "errors": self.errors,
            "provenance": self.provenance,
        }


# ── Role-to-model mapping ────────────────────────────────────────────────────


_ROLE_MODEL_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "PLANNER": {"min_context": 2048, "prefer_local": True, "tags": ["reasoning"]},
    "DEVELOPER": {"min_context": 4096, "prefer_local": True, "tags": ["coding"]},
    "CRITIC": {"min_context": 2048, "prefer_local": False, "tags": ["analysis"]},
    "REVIEWER": {"min_context": 2048, "prefer_local": True, "tags": ["quality"]},
    "JUDGE": {"min_context": 1024, "prefer_local": False, "tags": ["evaluation"]},
}


# ── MultiModelOrchestrator ───────────────────────────────────────────────────


class MultiModelOrchestrator:
    """Mode B: Multi-Model Collaboration orchestration.

    Assigns different models to different roles, runs independent tasks in
    parallel, and converges results via deterministic evaluation.

    Integrated with WorkspaceManager for isolated code execution.
    """

    # Max retry attempts per role before fallback.
    _MAX_RETRIES_PER_ROLE = 3
    # Backoff multiplier for retries.
    _RETRY_BACKOFF = 1.5

    def __init__(
        self,
        registry: ModelRegistry,
        llm_executor: Callable[[str, str, str, int, float], Dict[str, Any]],
        test_executor: Optional[Callable[[str, str], Dict[str, Any]]] = None,
        global_token_budget: int = 32768,
        max_parallel_tasks: int = 4,
        fallback_to_mode_a: bool = True,
        workspace_manager: Optional[WorkspaceManager] = None,
        max_retries: int = 3,
    ) -> None:
        """
        Args:
            registry: ModelRegistry with available models.
            llm_executor: Callable(model_id, prompt, system_prompt, max_tokens, temperature) -> {response, tokens, duration, error}
            test_executor: Callable(source, tests) -> {passed, output, returncode}
            global_token_budget: Total tokens for the entire run.
            max_parallel_tasks: Max concurrent model calls.
            fallback_to_mode_a: If True, fall back to MultiRoleOrchestrator on failure.
            workspace_manager: Optional WorkspaceManager for isolated execution.
            max_retries: Maximum retry attempts per role before fallback.
        """
        self.registry = registry
        self.llm_executor = llm_executor
        self.test_executor = test_executor or self._default_test_executor
        self.global_token_budget = global_token_budget
        self.max_parallel_tasks = max_parallel_tasks
        self.fallback_to_mode_a = fallback_to_mode_a
        self.workspace_manager = workspace_manager
        self.max_retries = max_retries

        # Scheduler for parallel execution.
        self.scheduler = ParallelScheduler(
            max_concurrency=max_parallel_tasks,
            global_token_budget=global_token_budget,
        )

        # Fallback orchestrator (Mode A).
        self._fallback: Optional[MultiRoleOrchestrator] = None

        # Track per-role retry counts.
        self._retry_counts: Dict[str, int] = {}

    async def run(self, task: Task, run_id: Optional[str] = None) -> tuple[AgentResult, OrchestrationTrace]:
        """Execute multi-model collaboration for a task.

        Returns (result, trace). Falls back to Mode A if no models are available
        or if the collaboration fails.
        """
        run_id = run_id or f"mm_{uuid.uuid4().hex[:8]}"
        trace = OrchestrationTrace(
            run_id=run_id,
            task_id=task.task_id,
            strategy_chosen=Strategy.MULTI_MODEL_COLLABORATION,
            reason="Mode B: multi-model collaboration",
        )
        result = AgentResult(run_id=run_id, task_id=task.task_id, strategy=Strategy.MULTI_MODEL_COLLABORATION)

        # Check model availability.
        available = self.registry.list_available()
        if not available:
            logger.warning("No models available; falling back to Mode A")
            return self._fallback_run(task, run_id, trace)

        # Assign models to roles.
        role_assignments = self._assign_models(task, available, trace)
        if not role_assignments:
            logger.warning("Could not assign models to all roles; falling back to Mode A")
            return self._fallback_run(task, run_id, trace)

        # Build dependency graph for parallel execution.
        deps = self._build_dependencies(role_assignments)
        tasks = []
        for role, mid in role_assignments.items():
            task_id = f"role_{role}_{mid}"
            tasks.append(
                TaskDependency(
                    task_id=task_id,
                    description=f"Execute {role} with model {mid}",
                    depends_on=deps.get(task_id, []),
                    estimated_tokens=self._estimate_tokens(role),
                    estimated_vram_mb=self._estimate_vram(mid),
                    estimated_ram_mb=self._estimate_ram(mid),
                    timeout_seconds=120.0,
                    metadata={"role": role, "model_id": mid},
                )
            )

        # Execute in parallel.
        t_start = time.time()
        exec_results: Dict[str, Any] = {}

        async def _executor(dep: TaskDependency) -> Any:
            role = dep.metadata["role"]
            model_id = dep.metadata["model_id"]
            return await self._execute_role(role, model_id, task, trace)

        raw_results = await self.scheduler.execute(tasks, _executor)

        # Collect results.
        for dep_id, task_result in raw_results.items():
            role = dep_id.split("_")[1]
            if task_result.success:
                exec_results[role] = task_result.output
            else:
                logger.warning("Role '%s' failed: %s", role, task_result.error)
                trace.record_decision("role_failed", {"role": role, "error": task_result.error})

        # Converge results.
        convergence = self._converge(exec_results, available, trace)
        result.final_output = convergence.get("code", "")
        result.tokens_total = int(self.scheduler.global_token_budget - self.scheduler.available_tokens)
        result.duration_seconds = time.time() - t_start
        result.validation_result = ValidationResult.PASS if convergence.get("tests_passed") else ValidationResult.FAIL

        trace.tokens_total = result.tokens_total
        trace.duration_seconds = result.duration_seconds
        trace.branches_created = len(tasks)
        trace.branches_evaluated = len(raw_results)
        trace.branches_selected = 1

        return result, trace

    async def _execute_role(
        self, role: str, model_id: str, task: Task, trace: OrchestrationTrace,
    ) -> Dict[str, Any]:
        """Execute a single role with a specific model, with retry and fallback.

        Implements bounded retry with exponential backoff:
          1. Retry up to max_retries times with increasing delay.
          2. On each failure, attempt reassignment to a compatible model.
          3. If all retries exhausted, fall back to Mode A for this role.
        """
        spec = self.registry.get(model_id)
        if spec is None:
            return {"error": f"Model '{model_id}' not found in registry"}

        system_prompt = self._system_prompt(role, model_id)
        prompt = self._role_prompt(role, task)

        # Create isolated workspace if available.
        branch_info = None
        if self.workspace_manager:
            branch_info = self.workspace_manager.create_workspace(
                f"branch_{role}_{model_id}",
                source_path=None,
                use_git_worktree=False,
            )

        last_error = None
        for attempt in range(self.max_retries):
            t0 = time.time()
            try:
                resp = self.llm_executor(model_id, prompt, system_prompt, spec.max_output_tokens, 0.3)
                duration = time.time() - t0
                tokens = resp.get("tokens", 0)

                # Record metrics.
                if spec:
                    spec.record_success(duration * 1000)

                result = {
                    "response": resp.get("response", ""),
                    "tokens": tokens,
                    "duration": duration,
                    "error": None,
                    "model_id": model_id,
                    "role": role,
                    "attempt": attempt + 1,
                }

                # Run tests in isolated workspace if available.
                if branch_info and self.test_executor:
                    test_result = self.test_executor(result["response"], "")
                    result["test_passed"] = test_result.get("passed", False)
                    if not result["test_passed"]:
                        result["test_output"] = test_result.get("output", "")

                return result

            except Exception as e:
                duration = time.time() - t0
                last_error = str(e)
                if spec:
                    spec.record_failure()

                logger.warning(
                    "Role '%s' with model '%s' failed (attempt %d/%d): %s",
                    role, model_id, attempt + 1, self.max_retries, e,
                )

                # Exponential backoff before retry.
                if attempt < self.max_retries - 1:
                    backoff = self._RETRY_BACKOFF ** attempt
                    time.sleep(min(backoff, 5.0))  # Cap at 5 seconds.

        # All retries exhausted — attempt reassignment or fall back to Mode A.
        logger.error("Role '%s' failed after %d attempts; attempting fallback", role, self.max_retries)
        trace.record_decision("role_failed_after_retries", {
            "role": role,
            "model_id": model_id,
            "error": last_error,
            "attempts": self.max_retries,
        })

        # Cleanup workspace.
        if branch_info and self.workspace_manager:
            self.workspace_manager.discard_branch(branch_info.branch_id)

        # Try reassignment to a compatible model.
        fallback_model = self._find_compatible_model(role, exclude=model_id)
        if fallback_model:
            logger.info("Reassigned role '%s' from '%s' to '%s'", role, model_id, fallback_model)
            trace.record_decision("model_reassigned", {
                "role": role,
                "from": model_id,
                "to": fallback_model,
            })
            # Retry with new model.
            return await self._execute_role(role, fallback_model, task, trace)

        # Final fallback to Mode A for this role.
        if self.fallback_to_mode_a:
            logger.info("Falling back to Mode A for role '%s'", role)
            trace.record_decision("fallback_to_mode_a", {"role": role})
            return await self._fallback_run_role(role, task, trace)

        return {
            "response": "",
            "tokens": 0,
            "duration": 0,
            "error": f"All retries and fallbacks exhausted for role '{role}': {last_error}",
            "model_id": model_id,
            "role": role,
            "attempt": self.max_retries,
        }

    async def _fallback_run_role(
        self, role: str, task: Task, trace: OrchestrationTrace,
    ) -> Dict[str, Any]:
        """Run a single role using Mode A fallback."""
        if self._fallback is None:
            def stub_llm(model_id, prompt, system_prompt, max_tokens, temperature):
                return {"response": f"[fallback] {prompt[:100]}", "tokens": 10, "duration": 0.001, "error": None}
            self._fallback = MultiRoleOrchestrator(llm_executor=stub_llm)

        # Use the fallback orchestrator's internal execution.
        try:
            # Extract the role-specific logic from MultiRoleOrchestrator.
            result = await self._fallback._execute_role(role, task, trace)
            return {
                "response": result.get("response", ""),
                "tokens": result.get("tokens", 0),
                "duration": result.get("duration", 0),
                "error": None,
                "model_id": "mode_a_fallback",
                "role": role,
                "attempt": 1,
            }
        except Exception as e:
            return {
                "response": "",
                "tokens": 0,
                "duration": 0,
                "error": f"Mode A fallback failed: {e}",
                "model_id": "mode_a_fallback",
                "role": role,
                "attempt": 1,
            }

    def _find_compatible_model(self, role: str, exclude: Optional[str] = None) -> Optional[str]:
        """Find a compatible model for a role, excluding a specific model."""
        available = self.registry.list_available()
        reqs = _ROLE_MODEL_REQUIREMENTS.get(role, {})
        min_context = reqs.get("min_context", 2048)

        for spec in available:
            if spec.model_id == exclude:
                continue
            if spec.context_window >= min_context:
                return spec.model_id
        return None

    def _assign_models(
        self, task: Task, available: List[ModelSpec], trace: OrchestrationTrace,
    ) -> Dict[str, str]:
        """Assign models to roles based on capabilities and resources."""
        assignments: Dict[str, str] = {}
        used_models: set = set()

        for role in ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"]:
            reqs = _ROLE_MODEL_REQUIREMENTS.get(role, {})
            min_context = reqs.get("min_context", 2048)
            prefer_local = reqs.get("prefer_local", True)

            # Find best model for this role.
            best_model = None
            for spec in available:
                if spec.model_id in used_models and len(used_models) < len([r for r in ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"] if r in assignments]):
                    # Allow reuse only if we've already assigned some models.
                    pass
                else:
                    if spec.context_window < min_context:
                        continue
                    if best_model is None:
                        best_model = spec
                    elif prefer_local and not best_model.is_local and spec.is_local:
                        best_model = spec
                    elif (not prefer_local and best_model.is_local and not spec.is_local):
                        best_model = spec

            # If no model meets requirements, allow reuse of any available model.
            if best_model is None:
                for spec in available:
                    if spec.context_window >= min_context or len(used_models) == 0:
                        best_model = spec
                        break

            if best_model is None:
                logger.warning("No model available for role '%s'", role)
                trace.record_decision("model_assignment_failed", {"role": role})
                continue

            assignments[role] = best_model.model_id
            # Only add to used_models if not already there (allow reuse).
            if best_model.model_id not in used_models:
                used_models.add(best_model.model_id)
            trace.record_decision("model_assigned", {"role": role, "model": best_model.model_id})

        return assignments

    def _build_dependencies(self, assignments: Dict[str, str]) -> Dict[str, List[str]]:
        """Build dependency graph: PLANNER → DEVELOPER → (CRITIC|REVIEWER) → JUDGE."""
        deps: Dict[str, List[str]] = {}
        roles_order = ["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"]
        for i, role in enumerate(roles_order):
            if role in assignments:
                task_id = f"role_{role}_{assignments[role]}"
                if i > 0 and roles_order[i - 1] in assignments:
                    prev_task_id = f"role_{roles_order[i - 1]}_{assignments[roles_order[i - 1]]}"
                    deps[task_id] = [prev_task_id]
                else:
                    deps[task_id] = []
        return deps

    def _estimate_tokens(self, role: str) -> int:
        """Estimate token budget for a role."""
        estimates = {"PLANNER": 1024, "DEVELOPER": 4096, "CRITIC": 2048, "REVIEWER": 1024, "JUDGE": 1024}
        return estimates.get(role, 1024)

    def _estimate_vram(self, model_id: str) -> int:
        """Estimate VRAM for a model."""
        spec = self.registry.get(model_id)
        if spec and spec.estimated_vram_mb > 0:
            return spec.estimated_vram_mb
        return 0

    def _estimate_ram(self, model_id: str) -> int:
        """Estimate RAM for a model."""
        spec = self.registry.get(model_id)
        if spec and spec.estimated_ram_mb > 0:
            return spec.estimated_ram_mb
        return 0

    def _converge(
        self, exec_results: Dict[str, Any], available: List[ModelSpec], trace: OrchestrationTrace,
    ) -> Dict[str, Any]:
        """Merge results from all roles into a final output."""
        code = exec_results.get("DEVELOPER", {}).get("response", "")
        tests_passed = False

        # Run tests if test executor is available.
        if code and self.test_executor:
            test_resp = self.test_executor(code, "")
            tests_passed = test_resp.get("passed", False)

        trace.record_decision("convergence", {
            "roles_executed": list(exec_results.keys()),
            "tests_passed": tests_passed,
        })

        return {"code": code, "tests_passed": tests_passed}

    def _fallback_run(self, task: Task, run_id: str, trace: OrchestrationTrace) -> tuple[AgentResult, OrchestrationTrace]:
        """Fall back to Mode A (MultiRoleOrchestrator)."""
        if self._fallback is None:
            # Create a fallback orchestrator with a stub LLM.
            def stub_llm(prompt: str, system_prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
                return {"response": f"[fallback] {prompt[:100]}", "tokens": 10, "duration": 0.001, "error": None}
            self._fallback = MultiRoleOrchestrator(llm_executor=stub_llm)
        trace.record_decision("fallback_to_mode_a", {"reason": "no_models_available"})
        return self._fallback.run(task, run_id)

    # ── Prompt builders ────────────────────────────────────────────────────

    @staticmethod
    def _system_prompt(role: str, model_id: str) -> str:
        prompts = {
            "PLANNER": f"Model: {model_id}. You are the PLANNER. Produce a concise build plan.",
            "DEVELOPER": f"Model: {model_id}. You are the DEVELOPER. Emit valid Python source code.",
            "CRITIC": f"Model: {model_id}. You are the CRITIC. Diagnose root cause of failures.",
            "REVIEWER": f"Model: {model_id}. You are the REVIEWER. Assess code quality.",
            "JUDGE": f"Model: {model_id}. You are the JUDGE. Assess semantic quality.",
        }
        return prompts.get(role, f"Model: {model_id}. You are a coding assistant role: {role}.")

    def _role_prompt(self, role: str, task: Task) -> str:
        prompts = {
            "PLANNER": f"Task: {task.description}\nDomain: {task.domain}\nProduce a build plan with files, API contract, and test cases.",
            "DEVELOPER": f"Task: {task.description}\nLanguage: {task.metadata.get('language', 'Python')}\nImplement the solution.",
            "CRITIC": f"Analyze the code for defects. Source and test output will follow.",
            "REVIEWER": f"Review the implementation for quality. Source will follow.",
            "JUDGE": f"Judge the semantic quality of the solution. Source and test results will follow.",
        }
        return prompts.get(role, f"Role: {role}. Task: {task.description}")

    # ── Default test executor ────────────────────────────────────────────────

    @staticmethod
    def _default_test_executor(source: str, tests: str) -> Dict[str, Any]:
        return {"passed": False, "output": "No test executor configured.", "returncode": 1}


# ── Convenience: build from existing CodeLabEngine ───────────────────────────


def build_from_code_lab_engine(engine, registry: Optional[ModelRegistry] = None, **kwargs) -> MultiModelOrchestrator:
    """Wrap an existing CodeLabEngine into a MultiModelOrchestrator."""
    if registry is None:
        registry = ModelRegistry()

    def llm_wrap(model_id: str, prompt: str, system_prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        # Try to delegate to the engine's multi-agent.
        ma = getattr(engine, '_coding_multi_agent', None)
        if ma is not None:
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
        return {"response": f"[stub {model_id}/{kwargs.get('role', 'unknown')}] {prompt[:100]}",
                "tokens": 10, "duration": 0.001, "error": None}

    def test_wrap(source, tests):
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

    return MultiModelOrchestrator(
        registry=registry,
        llm_executor=llm_wrap,
        test_executor=test_wrap,
        **kwargs,
    )
