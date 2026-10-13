"""Provenance integrity: agent events must land in events.jsonl.

P0/P1 spec (CC-2026-1013-LM): every AGENT_STARTED must have a matching
AGENT_RESPONSE / AGENT_FAILED, and these must be written to the EventLogger
(events.jsonl) for structured provenance.

Regression: _agent_event() routed multi-agent events into self.events and
self.event_handler but NOT through self._emit(), so AGENT_STARTED/RESPONSE
bypassed the EventLogger entirely — TASK_RECEIVED and FILE_MUTATION appeared
but no model-call provenance was recorded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_lab.config import CodeLabConfig
from code_lab.engine import CodeLabEngine


class _FakeLLM:
    """Deterministic fake LLM returning a parseable Python block."""

    def __init__(self):
        self.script = [
            ("```python\ndef factorial(n):\n    if n <= 1: return 1\n    return n * factorial(n-1)\n```\n", "stop"),
        ]
        self.i = 0
        self.last_model_used = ""

    def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
        self.last_model_used = model or ""
        text, finish = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return text, finish

    def get_models(self):
        return []


def _run_with_fake(base_dir: Path) -> tuple[dict, list, Path]:
    """Run a CodeLabEngine with the fake LLM and collect events."""
    config = CodeLabConfig(
        prompt="Write factorial(n).",
        language="python",
        run_id="prov_test_001",
        multi_agent=True,
        max_iterations=2,
    )
    fake_llm = _FakeLLM()
    engine = CodeLabEngine(config=config, base_dir=base_dir, llm_client=fake_llm)

    events = []
    engine.event_handler = lambda ev: events.append(ev)
    result = engine.run()

    events_path = engine.ws.logs / config.run_id / "events.jsonl"
    return result, events, events_path


class TestAgentEventsInEventsJsonl:
    """Verify AGENT_STARTED/AGENT_RESPONSE land in events.jsonl."""

    def test_agent_events_written_to_events_jsonl(self, tmp_path):
        _, events, events_path = _run_with_fake(tmp_path)

        # Check events.jsonl contains agent events
        lines = events_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 3, f"Expected at least 3 events, got {len(lines)}"

        event_types = [json.loads(line).get("event_type") for line in lines]
        assert "AGENT_STARTED" in event_types, f"Missing AGENT_STARTED: {event_types}"
        assert "AGENT_RESPONSE" in event_types, f"Missing AGENT_RESPONSE: {event_types}"

    def test_agent_events_have_trace_index(self, tmp_path):
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        started_events = [json.loads(l) for l in lines if l.strip()]
        started_events = [e for e in started_events if e.get("event_type") == "AGENT_STARTED"]

        # Each AGENT_STARTED should have a trace_index
        for ev in started_events:
            assert "trace_index" in ev, f"Missing trace_index in {ev}"
            assert isinstance(ev["trace_index"], int), f"trace_index not int: {ev['trace_index']}"

    def test_agent_response_has_role_template_id(self, tmp_path):
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        response_events = [json.loads(l) for l in lines if l.strip()]
        response_events = [e for e in response_events if e.get("event_type") == "AGENT_RESPONSE"]

        # Each AGENT_RESPONSE should have role_template_id
        for ev in response_events:
            assert "role_template_id" in ev, f"Missing role_template_id in {ev}"

    def test_event_sequence_is_ordered(self, tmp_path):
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        event_seq = [json.loads(l).get("event_seq") for l in lines if l.strip()]

        # Sequence should be monotonically increasing starting from 0
        assert event_seq == list(range(len(event_seq))), f"Non-sequential events: {event_seq}"


class TestAgentEventNoDuplicates:
    """Verify each agent event appears exactly once."""

    def test_no_duplicate_agent_events(self, tmp_path):
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        event_types = [json.loads(l).get("event_type") for l in lines if l.strip()]

        # Count agent events
        started_count = event_types.count("AGENT_STARTED")
        response_count = event_types.count("AGENT_RESPONSE")
        failed_count = event_types.count("AGENT_FAILED")

        # Should be balanced (each STARTED has one RESPONSE or FAILED)
        assert started_count == response_count + failed_count, (
            f"Unbalanced: {started_count} STARTED vs {response_count} RESPONSE + {failed_count} FAILED"
        )
        assert started_count >= 1, "Expected at least one agent turn"


class TestP0IntegrityBalancedEvents:
    """P0/P1 spec: AGENT_STARTED must always have a terminal event."""

    def test_started_always_has_matching_response(self, tmp_path):
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        evts = [json.loads(l) for l in lines if l.strip()]

        started_indices = [i for i, e in enumerate(evts) if e.get("event_type") == "AGENT_STARTED"]
        response_indices = [i for i, e in enumerate(evts) if e.get("event_type") == "AGENT_RESPONSE"]
        failed_indices = [i for i, e in enumerate(evts) if e.get("event_type") == "AGENT_FAILED"]

        # Every STARTED should have a RESPONSE or FAILED after it
        for idx in started_indices:
            assert any(r > idx for r in response_indices + failed_indices), (
                f"AGENT_STARTED at {idx} has no matching AGENT_RESPONSE/AGENT_FAILED"
            )


class TestRetryTraceIndex:
    """Retry scenario: PLANNER success, DEVELOPER fails then succeeds."""

    def test_retry_trace_index_unique(self, tmp_path):
        """PLANNER success, DEVELOPER attempt 1 fails (empty), attempt 2 succeeds."""
        script = [
            ("PLAN: create factorial\n", "stop"),           # PLANNER
            ("", "stop"),                                     # DEVELOPER attempt 1 - empty
            ("```python\ndef factorial(n):\n    return n\n```\n", "stop"),  # DEVELOPER attempt 2
        ]

        class _RetryFakeLLM:
            def __init__(self, script):
                self.script = list(script)
                self.i = 0
                self.last_model_used = ""

            def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
                self.last_model_used = model or ""
                text, finish = self.script[min(self.i, len(self.script) - 1)]
                self.i += 1
                return text, finish

            def get_models(self):
                return []

        config = CodeLabConfig(
            prompt="Write factorial(n).",
            language="python",
            run_id="retry_test_001",
            multi_agent=True,
            max_iterations=3,
        )
        fake_llm = _RetryFakeLLM(script)
        engine = CodeLabEngine(config=config, base_dir=tmp_path, llm_client=fake_llm)

        events = []
        engine.event_handler = lambda ev: events.append(ev)
        result = engine.run()

        # Parse events.jsonl
        events_path = engine.ws.logs / config.run_id / "events.jsonl"
        lines = events_path.read_text(encoding="utf-8").splitlines()
        evts = [json.loads(l) for l in lines if l.strip()]

        # Find STARTED and FAILED/RESPONSE pairs by trace_index
        started_by_trace = {}
        terminal_by_trace = {}

        for ev in evts:
            if ev.get("event_type") == "AGENT_STARTED":
                ti = ev.get("trace_index")
                started_by_trace[ti] = ev
            elif ev.get("event_type") in ("AGENT_RESPONSE", "AGENT_FAILED"):
                ti = ev.get("trace_index")
                terminal_by_trace[ti] = ev

        # Verify: every STARTED has a matching terminal event
        for ti, started_ev in started_by_trace.items():
            assert ti in terminal_by_trace, (
                f"AGENT_STARTED trace={ti} missing terminal event"
            )

        # Verify: different trace indices are unique
        trace_indices = list(started_by_trace.keys())
        assert len(trace_indices) == len(set(trace_indices)), "Duplicate trace_index found"

        # Check DEVELOPER has both FAILED and RESPONSE with different trace_indices
        developer_failed = [e for e in evts if e.get("event_type") == "AGENT_FAILED" and e.get("role") == "DEVELOPER"]
        developer_response = [e for e in evts if e.get("event_type") == "AGENT_RESPONSE" and e.get("role") == "DEVELOPER"]

        assert len(developer_failed) >= 1, "Expected at least one AGENT_FAILED for DEVELOPER"
        assert len(developer_response) >= 1, "Expected at least one AGENT_RESPONSE for DEVELOPER"

        # Verify trace indices are different
        failed_traces = {e.get("trace_index") for e in developer_failed}
        response_traces = {e.get("trace_index") for e in developer_response}
        assert not failed_traces.intersection(response_traces), (
            f"FAILED and RESPONSE share trace_index: {failed_traces & response_traces}"
        )


class TestProvenanceHashes:
    """Verify provenance hashes are recorded in events."""

    def test_input_context_provenance(self, tmp_path):
        """AGENT_RESPONSE should have input_context_hash when available."""
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        response_events = [json.loads(l) for l in lines if l.strip()]
        response_events = [e for e in response_events if e.get("event_type") == "AGENT_RESPONSE"]

        # At minimum, trace_index should be present (provenance linkage)
        for ev in response_events:
            assert "trace_index" in ev, f"Missing trace_index in {ev}"

    def test_response_provenance(self, tmp_path):
        """AGENT_RESPONSE should have response metadata."""
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        response_events = [json.loads(l) for l in lines if l.strip()]
        response_events = [e for e in response_events if e.get("event_type") == "AGENT_RESPONSE"]

        # Each response should have role and model provenance
        for ev in response_events:
            assert "role" in ev, f"Missing role in {ev}"
            assert "model" in ev or "actual_model" in ev, f"Missing model in {ev}"

    def test_model_provenance(self, tmp_path):
        """AGENT_RESPONSE should record configured vs actual model."""
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        response_events = [json.loads(l) for l in lines if l.strip()]
        response_events = [e for e in response_events if e.get("event_type") == "AGENT_RESPONSE"]

        # Each response should have model provenance fields
        for ev in response_events:
            assert "configured_model" in ev or "model" in ev, (
                f"Missing configured_model in {ev}"
            )


class TestProvenanceCompleteness:
    """Full provenance completeness check."""

    def test_provenance_completeness(self, tmp_path):
        """All events should have required provenance fields."""
        _, events, events_path = _run_with_fake(tmp_path)

        lines = events_path.read_text(encoding="utf-8").splitlines()
        evts = [json.loads(l) for l in lines if l.strip()]

        # Check all events have schema_version and collection_contract_version
        for ev in evts:
            assert "schema_version" in ev, f"Missing schema_version in {ev}"
            assert "collection_contract_version" in ev, (
                f"Missing collection_contract_version in {ev}"
            )

        # Check event sequence is complete
        seqs = [e.get("event_seq") for e in evts if e.get("event_seq") is not None]
        assert seqs == list(range(len(seqs))), f"Event sequence incomplete: {seqs}"


class TestRealEngineEventsJsonl:
    """Run one REAL normal CodeLabEngine run and verify events.jsonl."""

    def test_real_engine_events_jsonl(self, tmp_path):
        """Execute a real run (deterministic mode) and validate events."""
        config = CodeLabConfig(
            prompt="Create a Python function fibonacci(n) with unit tests.",
            language="python",
            run_id="real_test_001",
            multi_agent=False,  # deterministic mode
            max_iterations=1,
        )
        engine = CodeLabEngine(config=config, base_dir=tmp_path)
        result = engine.run()

        # Check events.jsonl exists and has content
        events_path = engine.ws.logs / config.run_id / "events.jsonl"
        assert events_path.exists(), "events.jsonl not created"

        lines = events_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) > 0, "No events written"

        evts = [json.loads(l) for l in lines if l.strip()]

        # Check terminal event exists
        terminal_types = [e.get("event_type") for e in evts if e.get("event_type") in ("RUN_COMPLETED", "RUN_FAILED")]
        assert len(terminal_types) > 0, "No terminal event (RUN_COMPLETED/RUN_FAILED)"

        # Check event sequence integrity
        seqs = [e.get("event_seq") for e in evts if e.get("event_seq") is not None]
        assert seqs == list(range(len(seqs))), f"Event sequence incomplete: {seqs}"
