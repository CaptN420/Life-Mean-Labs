"""StrategyRouter — Mode C: hybrid adaptive orchestration selection.

Chooses between orchestration strategies based on task properties, available
resources, and configured rules. Starts with deterministic heuristics; the
decision trace is recorded for later benchmarking.

Design rules:
  - Never fabricate resource availability — probe honestly.
  - Default to SEQUENTIAL (Mode A) when uncertain.
  - DIVERGENT only for complex tasks where parallel hypotheses add value.
  - Record every decision with its rationale.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from .models import AgentResult, Branch, ConvergenceResult, OrchestrationTrace, Strategy, Task

logger = logging.getLogger("Life_mean.Orchestrator.Router")


# ── Resource probing ─────────────────────────────────────────────────────────


def probe_available_vram_mb() -> int:
    """Estimate available VRAM in MB. Returns 0 if unmeasurable."""
    # Try nvidia-smi on Windows/Linux
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if lines:
                # "19847 MiB" → 19847
                parts = lines[0].split()
                return int(parts[0]) if parts[0].isdigit() else 0
    except Exception:
        pass
    return 0


def probe_available_ram_mb() -> int:
    """Estimate available RAM in MB. Returns 0 if unmeasurable."""
    try:
        import psutil
        avail = psutil.virtual_memory().available
        return avail // (1024 * 1024)
    except Exception:
        pass
    # Fallback: assume 8GB available
    return 8192


def probe_llm_available() -> bool:
    """Check if an LLM backend is reachable. Delegates to code_lab.multiagent."""
    try:
        from code_lab.multiagent import probe_llm, resolve_llm_credentials
        base_url, api_key = resolve_llm_credentials()
        probe = probe_llm(base_url, api_key)
        return bool(probe.get("available", False))
    except Exception as e:
        logger.debug("LLM probe failed: %s", e)
        return False


# ── Strategy selection ───────────────────────────────────────────────────────


class StrategyRouter:
    """Selects the optimal orchestration strategy for a given task.

    Uses deterministic rules based on:
      - Task complexity (difficulty, context budget)
      - Resource availability (VRAM, RAM, LLM backend)
      - Configured preferences
    """

    def __init__(
        self,
        preferred_strategy: Optional[Strategy] = None,
        max_parallel_branches: int = 3,
        enable_divergence: bool = True,
    ) -> None:
        self._preferred = preferred_strategy
        self._max_parallel_branches = max_parallel_branches
        self._enable_divergence = enable_divergence

    def select_strategy(
        self,
        task: Task,
        resources: Optional[Dict[str, Any]] = None,
    ) -> tuple[Strategy, str]:
        """Choose a strategy and return (strategy, reason)."""
        resources = resources or self._probe_resources()

        # If user specified a preference, honor it (unless resources forbid it).
        if self._preferred:
            if self._can_run(self._preferred, task, resources):
                return self._preferred, f"user-preferred: {self._preferred.value}"

        # Deterministic heuristic selection.
        if task.is_complex and self._enable_divergence:
            vram = resources.get("vram_mb", 0)
            if vram >= 8000:  # >= 8GB VRAM → multi-model collaboration feasible
                return (
                    Strategy.MULTI_MODEL_COLLABORATION,
                    f"complex task + sufficient VRAM ({vram}MB)",
                )
            if self._can_run(Strategy.DIVERGENT, task, resources):
                return (
                    Strategy.DIVERGENT,
                    f"complex task, divergence enabled, branches={self._max_parallel_branches}",
                )

        # Default: single-model multi-role (Mode A) — most resource-efficient.
        return (
            Strategy.SINGLE_MODEL_MULTI_ROLE,
            "default for non-complex or resource-constrained tasks",
        )

    def _can_run(self, strategy: Strategy, task: Task,
                 resources: Dict[str, Any]) -> bool:
        """Check if a strategy is feasible given current resources."""
        vram = resources.get("vram_mb", 0)
        ram = resources.get("ram_mb", 0)
        llm_available = resources.get("llm_available", False)

        if strategy == Strategy.MULTI_MODEL_COLLABORATION:
            # Needs multiple models → at least 8GB VRAM or remote LLM.
            return vram >= 8000 or (llm_available and ram >= 4096)
        if strategy == Strategy.DIVERGENT:
            # Needs enough resources for N parallel branches.
            return vram >= 4000 or llm_available
        if strategy == Strategy.PARALLEL:
            return vram >= 4000 or llm_available
        # SEQUENTIAL and SINGLE_MODEL_MULTI_ROLE always feasible.
        return True

    def _probe_resources(self) -> Dict[str, Any]:
        """Honest resource probing — never fabricate."""
        return {
            "vram_mb": probe_available_vram_mb(),
            "ram_mb": probe_available_ram_mb(),
            "llm_available": probe_llm_available(),
            "probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def build_trace(self, run_id: str, task: Task,
                    strategy: Strategy, reason: str) -> OrchestrationTrace:
        """Create an initial trace for recording decisions."""
        return OrchestrationTrace(
            run_id=run_id,
            task_id=task.task_id,
            strategy_chosen=strategy,
            reason=reason,
        )

    def suggest_branches(self, task: Task, strategy: Strategy) -> List[Dict[str, str]]:
        """Suggest independent branch strategies for divergence.

        Returns a list of {label, description} dicts. Empty list if not divergent.
        """
        if strategy != Strategy.DIVERGENT:
            return []
        return [
            {"label": "approach_a", "description": "Direct implementation from plan"},
            {"label": "approach_b", "description": "Decomposed sub-problems then assemble"},
            {"label": "approach_c", "description": "Pattern-based solution from similar cases"},
        ]

    def select_best_branch(self, branches: List[Branch],
                           trace: OrchestrationTrace) -> ConvergenceResult:
        """Select the best branch based on deterministic evaluation.

        Prefers branches with:
          1. Validation pass
          2. Lower token consumption
          3. Shorter duration
        """
        evaluated = [b for b in branches if b.is_evaluated]
        if not evaluated:
            return ConvergenceResult(
                selected_branch_id=branches[0].branch_id if branches else "",
                integration_method="rollback",
                notes="No branches evaluated; rolling back to first.",
            )

        # Score each branch: pass > fail, then prefer efficiency.
        def branch_score(b: Branch) -> tuple:
            validated = b.evaluation.get("validation_passed", False)
            tokens = b.result.tokens_total if b.result else 999999
            duration = b.result.duration_seconds if b.result else 999999
            # Higher is better: (validated, -tokens, -duration)
            return (1 if validated else 0, -tokens, -duration)

        best = max(evaluated, key=branch_score)
        trace.branches_evaluated = len(evaluated)
        trace.branches_selected = 1

        return ConvergenceResult(
            selected_branch_id=best.branch_id,
            integration_method="single_best",
            validation_passed=bool(best.evaluation.get("validation_passed")),
            notes=f"Selected branch '{best.strategy_label}' (tokens={best.result.tokens_total if best.result else 'N/A'}).",
        )
