"""Analysis utilities for metacognitive insights.

Provides functions to extract, transform, and analyze run data
for pattern detection and strategy comparison.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def extract_run_metadata(run_path: Path) -> Optional[Dict[str, Any]]:
    """Extract metadata from a code_lab run snapshot."""
    if not run_path.exists():
        return None

    try:
        with open(run_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            "run_id": data.get("run_id", run_path.parent.parent.name),
            "project": data.get("project", ""),
            "status": data.get("status", "unknown"),
            "iterations": data.get("iterations", 0),
            "duration": data.get("duration", 0.0),
            "errors": data.get("errors", []),
            "agent_trace": data.get("agent_trace", []),
            "judge_validation": data.get("judge_validation", ""),
            "llm_available": data.get("llm_available", False),
        }
    except (json.JSONDecodeError, OSError) as e:
        print(f"Failed to extract metadata from {run_path}: {e}")
        return None


def compute_run_hash(run_data: Dict[str, Any]) -> str:
    """Compute a deterministic hash for a run's conditions."""
    keys = sorted(run_data.keys())
    serialized = json.dumps(
        {k: run_data[k] for k in keys}, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()[:16]


def find_similar_runs(
    target_run: Dict[str, Any],
    all_runs: List[Dict[str, Any]],
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """Find runs with similar conditions to the target run."""
    similarities = []

    for run in all_runs:
        if run.get("run_id") == target_run.get("run_id"):
            continue

        score = _compute_similarity(target_run, run)
        similarities.append((score, run))

    similarities.sort(key=lambda x: -x[0])
    return [run for _, run in similarities[:max_results]]


def _compute_similarity(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> float:
    """Compute similarity between two runs."""
    score = 0.0

    # Domain match
    if run_a.get("project") == run_b.get("project"):
        score += 3.0

    # Status match
    if run_a.get("status") == run_b.get("status"):
        score += 1.0

    # Error type overlap
    errors_a = set(e.get("type", "") for e in run_a.get("errors", []))
    errors_b = set(e.get("type", "") for e in run_b.get("errors", []))
    if errors_a and errors_b:
        overlap = len(errors_a & errors_b)
        score += overlap * 2.0

    # Agent trace similarity
    trace_a = [t.get("agent") for t in run_a.get("agent_trace", [])]
    trace_b = [t.get("agent") for t in run_b.get("agent_trace", [])]
    if trace_a and trace_b:
        common_agents = len(set(trace_a) & set(trace_b))
        score += common_agents * 0.5

    return score


def analyze_failure_root_causes(
    failed_runs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze root causes of failures."""
    error_counts: Dict[str, int] = {}
    error_runs: Dict[str, List[str]] = {}

    for run in failed_runs:
        for error in run.get("errors", []):
            error_type = error.get("type", "unknown")
            if error_type not in error_counts:
                error_counts[error_type] = 0
                error_runs[error_type] = []

            error_counts[error_type] += 1
            error_runs[error_type].append(run.get("run_id", ""))

    root_causes = []
    for error_type, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        root_causes.append({
            "error_type": error_type,
            "occurrence_count": count,
            "affected_runs": error_runs[error_type],
            "likelihood": count / len(failed_runs) if failed_runs else 0.0,
        })

    return {
        "total_failed_runs": len(failed_runs),
        "root_causes": root_causes,
        "most_common_error": root_causes[0]["error_type"] if root_causes else None,
    }


def extract_strategy_comparison_data(
    runs: List[Dict[str, Any]],
    strategy_field: str = "execution_mode",
) -> Dict[str, List[Dict[str, Any]]]:
    """Group runs by strategy for comparison."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for run in runs:
        strategy = run.get(strategy_field, "unknown")
        if strategy not in grouped:
            grouped[strategy] = []
        grouped[strategy].append(run)

    return grouped


def generate_experiment_report(
    runs: List[Dict[str, Any]],
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generate a comprehensive experiment report."""
    passed = [r for r in runs if r.get("status") == "passed"]
    failed = [r for r in runs if r.get("status") == "failed"]

    # Analyze failures
    failure_analysis = analyze_failure_root_causes(failed)

    # Group by strategy
    strategies = extract_strategy_comparison_data(runs)

    # Compute metrics per strategy
    strategy_metrics = {}
    for strategy, strategy_runs in strategies.items():
        s_passed = [r for r in strategy_runs if r.get("status") == "passed"]
        strategy_metrics[strategy] = {
            "total": len(strategy_runs),
            "passed": len(s_passed),
            "failed": len(strategy_runs) - len(s_passed),
            "success_rate": len(s_passed) / len(strategy_runs) if strategy_runs else 0.0,
            "avg_duration": (
                sum(r.get("duration", 0.0) for r in strategy_runs) / len(strategy_runs)
                if strategy_runs else 0.0
            ),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_runs": len(runs),
        "overall_success_rate": len(passed) / len(runs) if runs else 0.0,
        "failure_analysis": failure_analysis,
        "strategy_metrics": strategy_metrics,
        "runs": runs,
    }

    if output_path:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Failed to write report: {e}")

    return report
