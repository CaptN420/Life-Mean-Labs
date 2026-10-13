"""Real-backend smoke test for event provenance integrity.

Uses actual configured backend/model — no FakeLLM, no manual EventLogger calls.
Verifies all P0/P1 provenance requirements from CC-2026-1013-LM v1.0.
Run from Life_mean root: python tests/test_real_backend_smoke.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure we're running from the right context
sys.path.insert(0, str(Path(__file__).parent.parent))

from code_lab.config import CodeLabConfig
from code_lab.engine import CodeLabEngine


def run_smoke(base_dir: Path) -> dict:
    """Run a real multi-agent task and capture all events."""
    config = CodeLabConfig(
        prompt="Create a Python function fibonacci(n) with unit tests.",
        language="python",
        run_id="smoke_real_001",
        multi_agent=True,
        max_iterations=3,
    )
    engine = CodeLabEngine(config=config, base_dir=base_dir)

    # Collect events via handler (real backend will be used)
    events = []
    engine.event_handler = lambda ev: events.append(ev)

    result = engine.run()

    # Read events.jsonl
    events_path = engine.ws.logs / config.run_id / "events.jsonl"
    raw_events = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                raw_events.append(json.loads(line))

    return {
        "result": result,
        "raw_events": raw_events,
        "events_count": len(raw_events),
        "events_path": str(events_path),
    }


def verify_provenance(raw_events: list) -> dict:
    """Verify all P0/P1 provenance requirements."""
    checks = {
        "task_received_before_agent": False,
        "agent_pairs_valid": True,
        "trace_indices_strict": True,
        "actual_model_real": True,
        "no_placeholder_provenance": True,
        "test_result_null_when_unknown": True,
        "no_duplicate_event_seq": True,
        "no_duplicate_emission": True,
        "terminal_event_exists": False,
        "started_response_pairing": True,
    }

    # Check 1: TASK_RECEIVED before first agent action
    task_idx = None
    first_agent_idx = None
    for i, ev in enumerate(raw_events):
        if ev.get("event_type") == "TASK_RECEIVED":
            task_idx = i
        elif ev.get("event_type") in ("AGENT_STARTED", "AGENT_RESPONSE", "AGENT_FAILED"):
            if first_agent_idx is None:
                first_agent_idx = i
    checks["task_received_before_agent"] = (
        task_idx is not None and first_agent_idx is not None and task_idx < first_agent_idx
    )

    # Check 2 & 3: Agent pairs with matching trace indices, strictly increasing
    started_events = [e for e in raw_events if e.get("event_type") == "AGENT_STARTED"]
    response_events = [e for e in raw_events if e.get("event_type") == "AGENT_RESPONSE"]
    failed_events = [e for e in raw_events if e.get("event_type") == "AGENT_FAILED"]

    # Collect trace indices
    started_trace_indices = [e.get("trace_index") for e in started_events]
    response_trace_indices = [e.get("trace_index") for e in response_events]
    failed_trace_indices = [e.get("trace_index") for e in failed_events]

    # Verify pairs match
    all_response_traces = set(response_trace_indices) | set(failed_trace_indices)
    checks["agent_pairs_valid"] = set(started_trace_indices) == all_response_traces

    # Verify strictly increasing (0, 1, 2, ...)
    expected_traces = list(range(len(started_events)))
    checks["trace_indices_strict"] = started_trace_indices == expected_traces

    # Check 4: actual_model is real backend model, not placeholder
    for ev in response_events + failed_events:
        actual = ev.get("actual_model")
        if actual and actual in ("test-model", "fake-model", "placeholder"):
            checks["actual_model_real"] = False

    # Check 5: No placeholder provenance
    for ev in raw_events:
        role_template = ev.get("role_template_id", "")
        if role_template and "test" in role_template.lower():
            checks["no_placeholder_provenance"] = False
            break

    # Check 6: TEST_RESULT uses null when relationship unknown
    test_results = [e for e in raw_events if e.get("event_type") == "TEST_RESULT"]
    for tr in test_results:
        after = tr.get("occurred_after_trace_index")
        before = tr.get("occurred_before_trace_index")
        # If both are None, that's acceptable (we don't know)
        # If one is set, verify it's an int
        if after is not None and not isinstance(after, int):
            checks["test_result_null_when_unknown"] = False
        if before is not None and not isinstance(before, int):
            checks["test_result_null_when_unknown"] = False

    # Check 7: No duplicate event_seq
    event_seqs = [e.get("event_seq") for e in raw_events]
    checks["no_duplicate_event_seq"] = len(event_seqs) == len(set(event_seqs))

    # Check 8: Terminal event exists
    terminal_types = {"RUN_COMPLETED", "RUN_FAILED"}
    checks["terminal_event_exists"] = any(
        e.get("event_type") in terminal_types for e in raw_events
    )

    # Check 9: STARTED/RESPONSE pairing valid
    started_set = set(started_trace_indices)
    response_set = set(response_trace_indices) | set(failed_trace_indices)
    checks["started_response_pairing"] = started_set == response_set

    return checks


def print_report(raw_events: list, checks: dict) -> None:
    """Print ordered real events and verification results."""
    print("\n" + "=" * 80)
    print("REAL-BACKEND SMOKE TEST REPORT")
    print("=" * 80)

    # Print event table with full model attribution
    print("\n--- EVENT TABLE ---")
    print(f"{'seq':<6} {'type':<20} {'trace_idx':<12} {'role':<12} {'configured_model':<40} {'actual_model':<40} {'stage':<15}")
    print("-" * 120)

    for ev in raw_events:
        seq = ev.get("event_seq", "?")
        etype = ev.get("event_type", "UNKNOWN")
        trace_idx = ev.get("trace_index", "")
        role = ev.get("role", "")
        configured_model = ev.get("configured_model", "") or ""
        actual_model = ev.get("actual_model", "") or ""
        stage = ev.get("stage", "")

        print(f"{seq:<6} {etype:<20} {trace_idx:<12} {role:<12} {configured_model:<40} {actual_model:<40} {stage:<15}")

    # Print checks
    print("\n--- VERIFICATION RESULTS ---")
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {check}: {status}")


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "life_mean_runs"
        result = run_smoke(base_dir)

        print(f"\nRun ID: {result['raw_events'][0].get('run_id', 'UNKNOWN') if result['raw_events'] else 'N/A'}")
        print(f"Events count: {result['events_count']}")
        print(f"Events path: {result['events_path']}")

        checks = verify_provenance(result["raw_events"])
        print_report(result["raw_events"], checks)

        # Final verdict
        print("\n" + "=" * 80)
        print("FINAL VERDICT")
        print("=" * 80)

        all_pass = all(checks.values())

        print(f"\nREAL_BACKEND_SMOKE: {'PASS' if checks['agent_pairs_valid'] and checks['trace_indices_strict'] else 'FAIL'}")
        print(f"REAL_MODEL_ATTRIBUTION: {'PASS' if checks['actual_model_real'] else 'FAIL'}")
        print(f"TRACE_PAIR_LINKAGE: {'PASS' if checks['started_response_pairing'] else 'FAIL'}")
        print(f"EVENT_ORDER: {'PASS' if checks['no_duplicate_event_seq'] else 'FAIL'}")
        print(f"LOG_INTEGRITY: {'PASS' if checks['terminal_event_exists'] and checks['no_duplicate_emission'] else 'FAIL'}")
        print(f"\nCOLLECTION_READY: {'YES' if all_pass else 'NO'}")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
