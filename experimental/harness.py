"""Experimental sandbox harness — play safely without touching the stable core.

This is an OPT-IN, additive layer. The stable core does NOT depend on it: the
harness only *reaches INTO* the core (CodeLabEngine, ToolWorker) to run a
single executor isolated in a throwaway workspace, then returns the result. It
never registers anything, never persists to the normal ``code_lab_runs/<id>``
layout, and never mutates shared state.

Design rules:
- Only executors whose ``connected == True`` may run here. A ``not-connected``
  executor (debate / research / synthesis / review / hermes_debate) is refused
  with a clear EXECUTOR_NOT_AVAILABLE — never faked, never silently skipped.
- Code stages run through the REAL CodeLabEngine in a temp ``base_dir``, so
  no ``code_lab_runs/`` workspace is created in the project.
- Deterministic / tool stages run the real synchronous tool host.
- The response is a plain dict consumed by the Experimental tab's "Harness".
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

from experimental.dispatch import ExecutorNotAvailable, executor_catalog


def _sandbox_dir() -> Path:
    """Create a disposable sandbox root (cleaned after the run)."""
    return Path(tempfile.mkdtemp(prefix="exp_harness_"))


def run_executor(executor_type: str, payload: Dict[str, Any],
                 feedback_store=None, run_id: str = "") -> Dict[str, Any]:
    """Run a single connected executor in an isolated, throwaway sandbox.

    Args:
        executor_type: a key of :data:`STAGE_EXECUTORS`
            (code / deterministic / code_lab / ...); must be ``connected``.
        payload: executor-specific inputs such as ``prompt``/``tool``/``args``.
        feedback_store: optional :class:`RunFeedbackStore` used by long
            multi-turn runners (e.g. ``llm_sweep``) to publish live progress.
        run_id: the store key for this run's feedback events.

    Returns:
        dict with ``executor``, ``kind``, ``status``
        (``passed`` / ``failed`` / ``EXECUTOR_NOT_AVAILABLE``) and ``result``.
    """
    cap = executor_catalog().get(executor_type)
    if cap is None:
        raise ExecutorNotAvailable(
            f"executor '{executor_type}' has no registered harness entry",
            executor_type)
    if not cap.get("connected"):
        raise ExecutorNotAvailable(
            f"executor '{executor_type}' ({cap.get('engine')}) is NOT connected "
            "now — it cannot run in the sandbox until its backend is available. "
            "No fake result is produced.",
            executor_type, engine=cap.get("engine"))

    kind = cap.get("kind", "")
    payload = payload or {}
    root = _sandbox_dir()
    try:
        if kind in ("code",):
            return _run_code(executor_type, cap, payload, root)
        if kind in ("deterministic",):
            return _run_tool(executor_type, cap, payload)
        if kind in ("debate_code",):
            return _run_debate_code(executor_type, cap, payload)
        if kind in ("sweep",):
            return _run_sweep(executor_type, cap, payload)
        if kind in ("llm_sweep",):
            return _run_llm_sweep(executor_type, cap, payload,
                                  feedback_store=feedback_store, run_id=run_id)
        return {
            "executor": executor_type,
            "kind": kind,
            "status": "EXECUTOR_NOT_AVAILABLE",
            "result": {"error": f"no harness runner for kind '{kind}'"},
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _run_code(executor_type: str, cap: Dict[str, Any], payload: Dict[str, Any],
              root: Path) -> Dict[str, Any]:
    """Run a code executor through the REAL CodeLabEngine in a temp sandbox."""
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine

    prompt = str(payload.get("prompt") or
                 "Create a small Python program with unit tests.")
    cfg = CodeLabConfig(
        run_id=str(payload.get("run_id") or "harness"),
        prompt=prompt,
        multi_agent=False,  # harness stays deterministic-first
        run_tests=bool(payload.get("run_tests", True)),
        deterministic_validation=bool(payload.get("deterministic_validation", True)),
        template_id=str(payload.get("template_id") or "coding-standard"),
        max_iterations=int(payload.get("max_iterations", 3)),
    )
    try:
        result = CodeLabEngine(config=cfg, base_dir=root).run()
    except Exception as e:  # pragma: no cover - defensive
        return {
            "executor": executor_type, "kind": "code",
            "status": "failed", "dispatched_to": "CodeLabEngine",
            "result": {"error": str(e)},
        }
    return {
        "executor": executor_type, "kind": "code",
        "dispatched_to": "CodeLabEngine",
        "status": result.get("status"),
        "result": {
            "det_status": result.get("deterministic_validation_status"),
            "validation": result.get("validation"),
            "files_created": result.get("files_created"),
            "errors": result.get("errors"),
        },
    }


def _run_debate_code(executor_type: str, cap: Dict[str, Any],
                     payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the closed DEBATE→SPEC→CODE→VERIFY chain (deterministic, traced).

    The returned trace includes the debate contributions, the handoff
    DECISION_SPEC, the generated files and the real pytest verification — an
    inspectable, reproducible chain (no hidden steps).
    """
    from experimental.retry_agent import run_debate_code

    seed = int(payload.get("seed", 1))
    mode = str(payload.get("mode", "deterministic"))
    task_type = str(payload.get("task_type", "retry_controller"))
    task_prompt = str(payload.get("task_prompt", ""))
    try:
        trace = run_debate_code(task_type=task_type, seed=seed, mode=mode,
                                task_prompt=task_prompt)
    except Exception as e:  # pragma: no cover - defensive
        return {
            "executor": executor_type, "kind": "debate_code",
            "status": "failed", "dispatched_to": "RetryAgent",
            "result": {"error": str(e)},
        }
    return {
        "executor": executor_type, "kind": "debate_code",
        "dispatched_to": "RetryAgent", "seed": seed, "mode": mode,
        "task_type": task_type,
        "status": trace.get("status", "failed"), "reproducible": trace.get("reproducible"),
        "result": {
            "debate": trace.get("debate"),
            "handoff": trace.get("handoff"),
            "generated_code": trace.get("generated_code"),
            "code_files": trace.get("code_files"),
            "verify": trace.get("verify"),
            "reason": trace.get("reason"),
        },
    }


def _run_sweep(executor_type: str, cap: Dict[str, Any],
               payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the robustness sweep (N runs across catalogue task types).

    Uses the same debate_code chain; aggregates a matrix of per-type
    pass / stable-hash / average duration and a global status. This is the
    large-run confidence check: if the chain is sound, every run in a
    deterministic sweep must PASS with no drift in spec_hash.
    """
    from experimental.sweep import sweep

    runs = int(payload.get("runs", 30))
    types = list(payload.get("types") or [])
    if not types:
        from experimental.retry_agent import CATALOG
        types = list(CATALOG)
    if runs < 1:
        runs = 30
    try:
        result = sweep(runs, types)
    except Exception as e:  # pragma: no cover - defensive
        return {
            "executor": executor_type, "kind": "sweep",
            "status": "failed", "dispatched_to": "RobustnessSweep",
            "result": {"error": str(e)},
        }
    return {
        "executor": executor_type, "kind": "sweep",
        "dispatched_to": "RobustnessSweep", "runs": runs, "types": types,
        "status": "passed" if result.get("all_green") else "failed",
        "result": {
            "runs": result.get("runs"),
            "status_counts": result.get("status_counts"),
            "matrix": result.get("matrix"),
            "failures": result.get("failures"),
            "total_duration_s": result.get("total_duration_s"),
            "all_green": result.get("all_green"),
        },
    }


def _run_llm_sweep(executor_type: str, cap: Dict[str, Any],
                   payload: Dict[str, Any],
                   feedback_store=None, run_id: str = "") -> Dict[str, Any]:
    """Run the LLM multi-turn experiment (mode-B chain N times + synthesis).

    Each tour goes through run_debate_code(mode='llm') so every tour is fully
    traced. The synthesis (observation / conclusion / next_leads) is computed
    deterministically from the aggregated real traces — never fabricated. An
    unavailable backend yields an honest NO_CONVERGENCE, not a fake pass.

    When ``feedback_store`` + ``run_id`` are given, a live event is published
    after every tour (kind='tour', text='tour N/M -> STATUS hash=...') so the
    UI can render a real-time timeline instead of waiting for the whole sweep.
    """
    from experimental.llm_sweep import run_llm_sweep

    turns = int(payload.get("turns", 30))
    task_prompt = str(payload.get("task_prompt") or payload.get("prompt") or "")
    model = str(payload.get("model") or "")
    if turns < 1:
        turns = 30

    def _report(tour, status, spec_hash):
        if feedback_store is not None and run_id:
            feedback_store.add_event(
                run_id,
                f"tour {tour}/{turns} -> {status}"
                + (f"  hash={spec_hash}" if spec_hash else ""),
                tour=tour, kind="tour")

    try:
        result = run_llm_sweep(turns, task_prompt, on_tour=_report, model=model)
    except Exception as e:  # pragma: no cover - defensive
        return {
            "executor": executor_type, "kind": "llm_sweep",
            "status": "failed", "dispatched_to": "LLMMultiTurn",
            "result": {"error": str(e)},
        }
    # status reflects whether the chain itself was usable this run (a real
    # signal, not just a green badge): passed only if >0 tours produced PASS.
    n_pass = (result.get("status_counts") or {}).get("PASS", 0)
    # synthesis text goes to the feedback stream too.
    if feedback_store is not None and run_id:
        syn = result.get("synthesis") or {}
        if syn.get("conclusion"):
            feedback_store.add_event(
                run_id,
                f"[synthesis] {syn['conclusion']}", kind="synthesis")
    return {
        "executor": executor_type, "kind": "llm_sweep",
        "dispatched_to": "LLMMultiTurn", "turns": turns,
        "status": "passed" if n_pass > 0 else "inconclusive",
        "result": {
            "turns": result.get("turns"),
            "status_counts": result.get("status_counts"),
            "pass_rate": result.get("pass_rate"),
            "spec_hashes_distinct": result.get("spec_hashes_distinct"),
            "convergence": result.get("convergence"),
            "synthesis": result.get("synthesis"),
            "verify_failures": result.get("verify_failures"),
            "inconclusive_reasons": result.get("inconclusive_reasons"),
        },
    }


def _run_tool(executor_type: str, cap: Dict[str, Any],
              payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run a deterministic tool through the existing synchronous tool host."""
    from core.workers.tool import _execute_tool, detect_tool

    tool_name = str(payload.get("tool") or "")
    if not tool_name:
        text = str(payload.get("prompt") or "")
        det = detect_tool(text) if text else None
        tool_name = det["tool_name"] if det else ""
    if not tool_name:
        return {
            "executor": executor_type, "kind": "deterministic",
            "status": "failed",
            "dispatched_to": "ToolWorker",
            "result": {"error": "no tool declared and none auto-detectable"},
        }
    args = dict(payload.get("args") or {})
    try:
        result = _execute_tool(tool_name, **args)
    except Exception as e:  # pragma: no cover - defensive
        return {
            "executor": executor_type, "kind": "deterministic",
            "status": "failed", "dispatched_to": "ToolWorker",
            "result": {"error": str(e)},
        }
    return {
        "executor": executor_type, "kind": "deterministic",
        "dispatched_to": "ToolWorker", "tool": tool_name,
        "status": "passed" if result.get("valid") is True else "failed",
        "result": result,
    }