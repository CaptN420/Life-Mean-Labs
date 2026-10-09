"""Regression: every AGENT_STARTED must have a matching terminal event.

P0/P1 integrity (spec): the timeline must never show an AGENT_STARTED with no
terminal AGENT_RESPONSE / AGENT_FAILED. Previously plan/develop/critique/review/
judge emitted AGENT_STARTED then called agent.turn() with no try/finally, so an
LLM that raised (backend down, network error) left an orphaned STARTED.
"""

import pytest

from code_lab.multiagent import CodingMultiAgent


class _Boom:
    """LLM backend whose chat() raises — simulates a dead backend mid-call."""
    last_model_used = ""
    def get_models(self): return []
    def chat(self, *a, **k):
        raise ConnectionError("backend unreachable")

class _Ok:
    last_model_used = "stub"
    def get_models(self): return []
    def chat(self, messages, **k):
        return "55", "stop"

class _Flaky:
    def __init__(self):
        self.n = 0
        self.last_model_used = "stub"
    def get_models(self): return []
    def chat(self, *a, **k):
        self.n += 1
        if self.n == 1:
            raise RuntimeError("boom")
        return "x", "stop"


def _make(stub):
    events = []
    ma = CodingMultiAgent("", "", llm_client=stub, on_event=events.append,
                          use_router=False, run_id="run_t")
    return ma, events


class TestTerminalEventAlwaysEmitted:
    def test_raised_turn_emits_started_then_failed_not_orphan(self):
        ma, events = _make(_Boom())
        with pytest.raises(ConnectionError):
            ma.plan("build it", "python")
        types = [e["type"] for e in events]
        assert types.index("AGENT_STARTED") < types.index("AGENT_FAILED")
        assert "AGENT_RESPONSE" not in types, "no response may be claimed"
        assert types.count("AGENT_STARTED") == types.count("AGENT_FAILED")

    def test_success_still_emits_started_then_response(self):
        ma, events = _make(_Ok())
        res = ma.plan("build it", "python")
        types = [e["type"] for e in events]
        assert types == ["AGENT_STARTED", "AGENT_RESPONSE"], types
        assert res["ok"] is True

    def test_mixed_success_and_failure_terminals_always_balanced(self):
        ma, events = _make(_Flaky())
        with pytest.raises(RuntimeError):
            ma.develop("plan", "python")
        ma.plan("second", "python")
        starts = sum(1 for e in events if e["type"] == "AGENT_STARTED")
        terminals = sum(1 for e in events
                        if e["type"] in ("AGENT_RESPONSE", "AGENT_FAILED"))
        assert starts == terminals, [(e["type"], e.get("role")) for e in events]
        assert starts == 2

    def test_judge_failure_emits_terminal_failed(self):
        ma, events = _make(_Flaky())
        with pytest.raises(RuntimeError):
            ma.judge("src", "tests", True)
        types = [e["type"] for e in events]
        assert "AGENT_STARTED" in types and "AGENT_FAILED" in types
        assert types.count("AGENT_STARTED") == types.count("AGENT_FAILED")