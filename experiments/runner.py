"""Experiment runner for synthetic data generation.

Integrates generated tasks with existing SmartRouter and ToolWorker
to execute tasks through the multi-agent pipeline.
"""

from __future__ import annotations

import threading

import logging
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.events.event_bus import EventBus
from core.events.message import Message
from core.runtime.worker import Worker
from experiments.context import ExperimentContext, ProvenanceChain
from experiments.generation.schemas import GeneratedTask

logger = logging.getLogger("ExperimentRunner")


# CANONICAL ValidationResult lives in `experiments.validation.schemas`
# (validation owns the concept). runner reuses it — one implementation.
from experiments.validation.schemas import ValidationResult  # noqa: F401


class UnsupportedTaskError(RuntimeError):
    """Raised when no deterministic tool can serve a task.

    Carries a machine-readable ``code`` prefix (``UNSUPPORTED_TASK`` /
    ``NO_ANSWER``) so a caller can tell "we have no tool for this" from "the tool
    ran and the answer was wrong".
    """


@dataclass
class ExperimentResult:
    """Result of executing a generated task through the pipeline."""

    run_id: str
    task_id: str
    experiment_id: str
    generation_id: str
    config: Dict[str, Any]
    routing_decision: Dict[str, Any]
    workers_used: List[str]
    tools_used: List[str]
    answer: Optional[Any] = None
    ground_truth: Optional[Any] = None
    validation_result: Optional[ValidationResult] = None
    provenance: Optional[ProvenanceChain] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Why the task could not be answered, when it could not. Silent None answers
    # made a missing tool look like a wrong answer; this keeps the reason.
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if the result is valid."""
        return self.validation_result is not None and self.validation_result.valid

    @property
    def is_successful(self) -> bool:
        """Check if the task completed successfully."""
        return self.answer is not None and self.is_valid

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "experiment_id": self.experiment_id,
            "generation_id": self.generation_id,
            "config": self.config,
            "routing_decision": self.routing_decision,
            "workers_used": self.workers_used,
            "tools_used": self.tools_used,
            "answer": self.answer,
            "ground_truth": self.ground_truth,
            "validation_result": self.validation_result.to_dict() if self.validation_result else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "error": self.error,
        }


class ExperimentRunner:
    """Runs generated tasks through the existing multi-agent pipeline.

    Integrates with:
    - SmartRouter (core/assignment/router.py)
    - ToolWorker (core/workers/tool.py)
    - EventBus (core/events/event_bus.py)

    Reuses existing components without modification.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the experiment runner.

        Args:
            config: Experiment configuration dictionary
        """
        self.config = config or {}
        self.event_bus = EventBus()
        self._results: List[ExperimentResult] = []
        self._run_counter = 0
        # Optional observer for the deterministic decisions (routing, validation).
        # The observability tracker used to expose record_transition() and
        # record_rule_application() with NO caller anywhere, so every manifest
        # advertised an empty "traces" section. The sink is optional so the
        # runner stays usable standalone.
        self.trace_sink: Optional[Callable[[Dict[str, Any]], None]] = None
        # Optional runtime usage recorder: proves WHAT executed, instead of
        # inferring it later from ingested logs.
        self.usage_sink: Optional[Callable[[Dict[str, Any]], None]] = None

    def _emit_usage(self, kind: str, name: str, ok: Optional[bool] = None,
                    extra: Optional[Dict[str, Any]] = None) -> None:
        """Publish one executed component. Never breaks the run."""
        sink = self.usage_sink
        if sink is None or not name:
            return
        try:
            sink({"kind": kind, "name": name, "ok": ok, "extra": extra or {}})
        except Exception as exc:  # noqa: BLE001 - telemetry must not fail a task
            logger.warning("usage sink failed for %s:%s: %s", kind, name, exc)

    def _emit_trace(self, rule: str, before: Dict[str, Any], after: Dict[str, Any],
                    agent_id: str = "") -> None:
        """Publish one deterministic decision. Never breaks the run."""
        sink = self.trace_sink
        if sink is None:
            return
        try:
            sink({"rule": rule, "before": before, "after": after, "agent_id": agent_id})
        except Exception as exc:  # noqa: BLE001 - tracing must not fail a task
            logger.warning("trace sink failed for rule %s: %s", rule, exc)

    def run_task(
        self,
        task: GeneratedTask,
        context: Optional[ExperimentContext] = None,
    ) -> ExperimentResult:
        """Execute a single task, bounded by ``task_timeout_seconds``.

        A stalled tool or provider used to hang the whole experiment forever
        (nothing in core/runtime, core/workers or here had a timeout). The task
        now runs in a worker thread with a deadline: on expiry the result is an
        explicit ``TASK_TIMEOUT`` failure, never a silent success.

        Python cannot kill a thread, so an expired worker is abandoned (daemon)
        and its eventual result is discarded — it is NOT appended to the
        statistics, because the task did not finish within its budget.
        """
        timeout = float(self.config.get("task_timeout_seconds", 120) or 0)
        if timeout <= 0:
            result = self._run_task_impl(task, context)
            self._results.append(result)
            return result

        box: Dict[str, Any] = {}

        def _target() -> None:
            try:
                box["result"] = self._run_task_impl(task, context)
            except BaseException as exc:  # noqa: BLE001 - forwarded to the caller
                box["error"] = exc

        worker = threading.Thread(
            target=_target, daemon=True, name=f"task-{task.task_id}",
        )
        worker.start()
        worker.join(timeout)

        if worker.is_alive():
            logger.error(
                "TASK_TIMEOUT: task %s exceeded %.1fs; abandoned "
                "(it may still be running and its result will be ignored)",
                task.task_id, timeout,
            )
            result = self._timeout_result(task, context, timeout)
            self._results.append(result)
            return result

        if "error" in box:
            raise box["error"]

        result = box["result"]
        self._results.append(result)
        return result

    def _timeout_result(
        self,
        task: GeneratedTask,
        context: Optional[ExperimentContext],
        timeout: float,
    ) -> ExperimentResult:
        """Explicit failure record for a task that exceeded its deadline."""
        exp_id = context.experiment_id if context else ""
        gen_id = context.generation_id if context else ""
        return ExperimentResult(
            run_id=f"run_{uuid.uuid4().hex[:8]}",
            task_id=task.task_id,
            experiment_id=exp_id,
            generation_id=gen_id,
            config=self.config,
            routing_decision={},
            workers_used=[],
            tools_used=[],
            answer=None,
            ground_truth=task.ground_truth,
            validation_result=None,
            provenance=None,
            error=(
                f"TASK_TIMEOUT: task exceeded {timeout:.0f}s "
                f"(task_timeout_seconds). No answer was produced."
            ),
            metadata={"timeout_seconds": timeout, "timed_out": True},
        )

    def _run_task_impl(
        self,
        task: GeneratedTask,
        context: Optional[ExperimentContext] = None,
    ) -> ExperimentResult:
        """Execute a single task through the pipeline.

        Args:
            task: Task to execute
            context: Experiment context for provenance tracking

        Returns:
            ExperimentResult with full execution trace
        """
        self._run_counter += 1
        run_id = f"run_{uuid.uuid4().hex[:8]}"

        # Create or use provided context
        if context is None:
            context = ExperimentContext(
                task_id=task.task_id,
                run_id=run_id,
                domain=task.domain,
                difficulty=task.difficulty,
            )

        # Route task to appropriate workers
        routing_decision = self._route_task(task)

        # Execute through workers. A task no tool can serve fails EXPLICITLY:
        # an unanswered task must not look like a merely wrong answer.
        error: Optional[str] = None
        try:
            answer = self._execute_task(task, routing_decision)
        except UnsupportedTaskError as exc:
            answer = None
            error = str(exc)

        # The routing decision is deterministic (SmartRouter), so it is traced
        # with its inputs and outputs: this is what makes a wrong answer
        # explainable after the fact.
        self._emit_trace(
            "RoutingRule",
            {"task_id": task.task_id, "domain": task.domain, "difficulty": task.difficulty},
            {
                "selected": list(routing_decision.get("selected", []) or []),
                "tools": self._extract_tools_used(routing_decision),
            },
        )

        # Validate result
        validation_result = self._validate_task(task, answer)

        self._emit_trace(
            "ValidationRule",
            {"task_id": task.task_id, "answer": answer, "ground_truth": task.ground_truth},
            {
                "valid": bool(validation_result.valid),
                "method": getattr(validation_result, "method", ""),
                "error": error,
            },
        )

        # Create provenance chain
        provenance = ProvenanceChain(
            experiment_id=context.experiment_id,
            generation_id=context.generation_id,
            task_id=task.task_id,
            run_id=run_id,
            generator_version=task.generator_version,
            generator_strategy=task.generation_strategy,
            seed=task.seed,
            routing_decision=routing_decision,
            workers_used=routing_decision.get("selected", []),
            tools_used=self._extract_tools_used(routing_decision),
            validation_result=validation_result.to_dict() if validation_result else None,
        )

        # Create result
        result = ExperimentResult(
            run_id=run_id,
            task_id=task.task_id,
            experiment_id=context.experiment_id,
            generation_id=context.generation_id,
            config=self.config,
            routing_decision=routing_decision,
            workers_used=routing_decision.get("selected", []),
            tools_used=self._extract_tools_used(routing_decision),
            answer=answer,
            ground_truth=task.ground_truth,
            validation_result=validation_result,
            provenance=provenance,
            error=error,
        )

        return result

    def run_task_with_llm_verifier(
        self,
        task: GeneratedTask,
        context: Optional[ExperimentContext] = None,
        llm_verifier: Any = None,
    ) -> ExperimentResult:
        """Run a task through the existing pipeline, plus an OPTIONAL LLM verifier.

        This is an ADAPTER (no new orchestrator): the task still executes via the
        existing SmartRouter + ToolWorker + deterministic validation path. The
        LLM verifier, when provided and available, adds a SEPARATE judge opinion
        recorded in provenance.metadata — it can NEVER override the deterministic
        `validation_result` (rule 6). If the verifier is absent or fails, the
        deterministic path result is returned unchanged.
        """
        result = self.run_task(task, context)
        judge_opinion = None
        if llm_verifier is not None:
            try:
                judge_opinion = llm_verifier.judge(
                    source=str(task.description),
                    tests="",
                    deterministic_valid=result.is_valid,
                )
                result.metadata["judge_opinion"] = judge_opinion
                result.metadata["judge_overrides_deterministic"] = False  # never
                if result.provenance is not None:
                    result.provenance.routing_decision["judge_opinion"] = {
                        "ok": judge_opinion.get("ok"),
                        "verdict_peek": (judge_opinion.get("response") or "")[:120],
                    }
            except Exception as e:  # pragma: no cover
                result.metadata["judge_opinion"] = {"ok": False, "error": str(e)}
                result.metadata["judge_overrides_deterministic"] = False
        return result

    def run_batch(
        self,
        tasks: List[GeneratedTask],
        context: Optional[ExperimentContext] = None,
    ) -> List[ExperimentResult]:
        """Execute a batch of tasks through the pipeline.

        Args:
            tasks: List of tasks to execute
            context: Experiment context for provenance tracking

        Returns:
            List of ExperimentResults
        """
        results = []
        for task in tasks:
            result = self.run_task(task, context)
            results.append(result)
        return results

    def get_results(self) -> List[ExperimentResult]:
        """Get all experiment results."""
        return list(self._results)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about executed tasks."""
        if not self._results:
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "validation_pass_rate": 0.0,
                "avg_score": 0.0,
            }

        successful = sum(1 for r in self._results if r.is_successful)
        scores = [r.validation_result.score for r in self._results if r.validation_result]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        return {
            "total_runs": len(self._results),
            "successful_runs": successful,
            "validation_pass_rate": successful / len(self._results),
            "avg_score": avg_score,
        }

    def _route_task(self, task: GeneratedTask) -> Dict[str, Any]:
        """Route task to appropriate workers using SmartRouter.

        Args:
            task: Task to route

        Returns:
            Routing decision dictionary
        """
        from core.assignment.router import SmartRouter

        router = SmartRouter()
        description = task.description

        # Add domain-specific routing hints
        if task.domain == "math":
            description += f" This is a math problem requiring calculation."
        elif task.domain == "physics":
            description += f" This is a physics problem requiring force/motion analysis."
        elif task.domain == "chemistry":
            description += f" This is a chemistry problem requiring molar mass calculation."

        routing_decision = router.route(
            description=description,
            top_k=2,
            opposition_mode=self.config.get("opposition_mode", False),
        )

        logger.info(f"[ExperimentRunner] Routed task {task.task_id} to {routing_decision['selected']}")
        return routing_decision

    def _execute_task(
        self,
        task: GeneratedTask,
        routing_decision: Dict[str, Any],
    ) -> Optional[Any]:
        """Execute task through selected workers.

        Args:
            task: Task to execute
            routing_decision: Routing decision from SmartRouter

        Returns:
            Answer or None if execution failed
        """
        selected_workers = routing_decision.get("selected", [])

        # For now, use ToolWorker for deterministic execution
        from core.workers.tool import ToolWorker
        from library.tools.detection import detect_tool

        worker = ToolWorker(self.event_bus)
        worker.initialize()

        # Auto-detect tool and extract parameters from task description
        detection = detect_tool(task.description)
        if detection:
            # Enregistré ici, pas après coup : c'est le SEUL outil réellement
            # sélectionné (les listes de famille du routeur en annoncent cinq).
            self._emit_usage("worker", "ToolWorker", extra={"task_id": task.task_id})
            self._emit_usage("tool", str(detection.get("tool_name") or ""),
                             extra={"task_id": task.task_id, "domain": task.domain})
        if not detection:
            raise UnsupportedTaskError(
                f"UNSUPPORTED_TASK: no deterministic tool matches "
                f"domain={task.domain!r} description={task.description[:120]!r}"
            )
        tool_kwargs = {}
        if detection:
            param_key = detection.get("param_key", "")
            tool_name = detection.get("tool_name", "")
            import re

            # ── Coding: pass description directly to coding_generator ────────
            if "coding_generator" in tool_name or "coding" in task.domain.lower():
                # Extract difficulty from description if present
                diff_match = re.search(r'difficulty\s+(\d)', task.description)
                difficulty = int(diff_match.group(1)) if diff_match else 2
                tool_kwargs["description"] = task.description
                tool_kwargs["difficulty"] = difficulty

            # ── Physics: F = ma ──
            elif "physics_force" in tool_name or "force" in task.description.lower():
                nums = [float(x) for x in re.findall(r'\d+\.?\d*', task.description)]
                if len(nums) >= 2:
                    tool_kwargs["mass"] = nums[0]
                    tool_kwargs["acceleration"] = nums[1]

            # ── Chemistry: molar mass ──
            elif "chemistry_molar_mass" in tool_name or "molar mass" in task.description.lower():
                m = re.search(r"of\s+([A-Z][a-z]?[A-Z]?[a-z]?)", task.description)
                if m:
                    tool_kwargs["formula"] = m.group(1)

            # ── Math: two-number / single-number tools ──
            else:
                numbers = [int(x) for x in re.findall(r'\d+', task.description)]
                # For GCD/LCM we need both numbers, for others we need just one
                if param_key == "a" and len(numbers) >= 2:
                    # Two-number operations (gcd, lcm)
                    tool_kwargs["a"] = numbers[0]
                    tool_kwargs["b"] = numbers[1]
                elif param_key in ("a", "n") and len(numbers) >= 1:
                    # Single-number operations (factorial, is_prime, fibonacci)
                    tool_kwargs[param_key] = numbers[0]
                elif param_key in ("angle_deg", "value", "x") and len(numbers) >= 1:
                    # trig (angle in degrees), log/sqrt (single value)
                    tool_kwargs[param_key] = numbers[0]
                    if param_key == "value":
                        # The generator's ground truth uses the natural log, so
                        # say it explicitly instead of relying on a tool default.
                        base_match = re.search(r"base\s+(\d+)", task.description.lower())
                        tool_kwargs["base"] = (
                            float(base_match.group(1)) if base_match else math.e
                        )
                elif len(numbers) >= 2:
                    tool_kwargs["a"] = numbers[0]
                    tool_kwargs["b"] = numbers[1]

        # Create message for task execution
        message = Message(
            sender="experiment_runner",
            destination="tool_worker",
            type="task",
            payload={
                "task_id": task.task_id,
                "description": task.description,
                "domain": task.domain,
                "reasoning_type": task.reasoning_type,
                "ground_truth": task.ground_truth,
                "kwargs": tool_kwargs,  # ToolWorker expects kwargs in this key
            },
        )

        # Execute (synchronous for now)
        try:
            worker.execute(message)
            # Get result from event bus history
            history = self.event_bus.get_history()
            if history:
                last_msg = history[-1]
                if last_msg.type == "tool_response":
                    tool_result = last_msg.payload.get("tool_result", {})
                    raw_answer = tool_result.get("result")

                    # Extract the actual answer from tool result dict
                    # Tool results are dicts like {'valid': True, 'a': 13, 'b': 45, 'gcd': 1, 'lcm': 585}
                    if isinstance(raw_answer, dict):
                        # Try to find the primary answer key based on task type
                        desc = task.description.lower()

                        # ── Coding: return source code ──────────────────────────
                        if "coding" in task.domain.lower() or "code" in desc:
                            return raw_answer.get("source", "")

                        if "gcd" in desc:
                            answer = raw_answer.get("gcd")
                        elif "lcm" in desc:
                            answer = raw_answer.get("lcm")
                        elif "factorial" in desc or "n!" in desc:
                            answer = raw_answer.get("factorial")
                        elif "prime" in desc:
                            answer = raw_answer.get("is_prime")
                        elif "fibonacci" in desc:
                            answer = raw_answer.get("fibonacci")
                        elif "force" in desc:
                            answer = raw_answer.get("force")
                        elif "molar mass" in desc:
                            answer = raw_answer.get("molar_mass")
                        elif "sin" in desc:
                            answer = raw_answer.get("sin")
                        elif "cos" in desc:
                            answer = raw_answer.get("cos")
                        elif "tan" in desc:
                            answer = raw_answer.get("tan")
                        elif "trig" in desc:
                            answer = raw_answer.get("result")
                        elif "log" in desc:
                            answer = raw_answer.get("log")
                        elif "sqrt" in desc or "square root" in desc:
                            answer = raw_answer.get("sqrt")
                        elif re.search(r'\bexp\b', desc) or "exponential" in desc:
                            answer = raw_answer.get("exp")
                        else:
                            # Try to find a numeric answer
                            keys = ["gcd", "lcm", "factorial", "fibonacci",
                                    "is_prime", "force", "molar_mass", "result",
                                    "sin", "cos", "tan", "log", "sqrt", "exp"]
                            for key in keys:
                                if key in raw_answer and isinstance(raw_answer[key], (int, float, bool)):
                                    answer = raw_answer[key]
                                    break
                            else:
                                answer = raw_answer  # Return the whole dict if no match

                        if answer is None:
                            raise UnsupportedTaskError(
                                f"NO_ANSWER: tool '{detection.get('tool_name')}' returned "
                                f"no usable value (keys={sorted(raw_answer)})"
                            )
                        return answer
                    return raw_answer
        except UnsupportedTaskError:
            raise
        except Exception as e:
            logger.error(f"[ExperimentRunner] Execution failed: {e}")
            raise UnsupportedTaskError(f"NO_ANSWER: tool execution failed: {e}") from e

        raise UnsupportedTaskError(
            f"NO_ANSWER: tool worker produced no tool_response for "
            f"description={task.description[:120]!r}"
        )

    def _validate_task(
        self,
        task: GeneratedTask,
        answer: Optional[Any],
    ) -> ValidationResult:
        """Validate task answer against ground truth.

        Args:
            task: Original task
            answer: Computed answer

        Returns:
            ValidationResult
        """
        if answer is None:
            return ValidationResult(
                valid=False,
                score=0.0,
                method="no_answer",
                error="No answer computed",
            )

        # Compare with ground truth
        ground_truth = task.ground_truth
        if ground_truth is None:
            return ValidationResult(
                valid=False,
                score=0.0,
                method="no_ground_truth",
                error="No ground truth available",
            )

        # Determine validity
        valid = self._compare_answers(answer, ground_truth)
        score = 1.0 if valid else 0.0

        return ValidationResult(
            valid=valid,
            score=score,
            method="deterministic",
            evidence={
                "answer": answer,
                "ground_truth": ground_truth,
                "comparison": f"{answer} == {ground_truth}",
            },
        )

    def _compare_answers(self, answer: Any, ground_truth: Any) -> bool:
        """Compare answer with ground truth.

        Args:
            answer: Computed answer
            ground_truth: Expected answer

        Returns:
            True if answers match
        """
        try:
            # Handle numeric comparison with tolerance
            if isinstance(answer, (int, float)) and isinstance(ground_truth, (int, float)):
                return abs(answer - ground_truth) < 1e-6

            # Handle string comparison
            if isinstance(answer, str) and isinstance(ground_truth, str):
                return answer.lower().strip() == ground_truth.lower().strip()

            # Handle exact equality
            return answer == ground_truth
        except (TypeError, ValueError):
            return False

    def _extract_tools_used(self, routing_decision: Dict[str, Any]) -> List[str]:
        """Extract tools used from routing decision.

        Args:
            routing_decision: Routing decision dictionary

        Returns:
            List of tool names used
        """
        # Extract from selected workers
        selected = routing_decision.get("selected", [])

        # Map workers to tools (simplified)
        worker_to_tools = {
            "tool_worker": ["math_calculation", "physics_force", "chemistry_molar"],
            "math_validation_worker": ["math_gcd", "math_lcm"],
            "physics_validation_worker": ["physics_kinematics"],
            "chemistry_validation_worker": ["chemistry_stoichiometry"],
        }

        tools = []
        for worker in selected:
            if worker in worker_to_tools:
                tools.extend(worker_to_tools[worker])

        return list(set(tools))  # Deduplicate
