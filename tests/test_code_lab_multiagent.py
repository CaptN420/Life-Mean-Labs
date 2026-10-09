"""Code Lab — REAL multi-agent integration tests (Phase 15/16/18).

These tests exercise the actual LLM-backed multi-agent path using a fake
LLMClient that behaves like the real one, and an OPTIONAL live integration
test tagged so it only runs when a reachable+authenticated LLM backend exists
(the local LM Studio server requires a valid API token; see resolve_llm_credentials).

Hard rule: we NEVER fake an LLM turn in a way that makes a run look
multi-agent when it isn't. `requires_llm` tests SKIP when `probe_llm` reports
the backend unavailable/invalid-token (rule 15).
"""

from __future__ import annotations

import subprocess

import pytest

from code_lab.config import CodeLabConfig
from code_lab.multiagent import (
    CodingAgent,
    CodingMultiAgent,
    probe_llm,
    resolve_llm_credentials,
)
from code_lab.engine import _extract_python_blocks, build_default_engine


# ── phantom-turn / extraction unit tests (deterministic, no LLM) ─────────
class TestExtraction:
    @pytest.mark.parametrize("text,expected", [
        ("", ""),
        ("  \n  ", ""),
        ("no code here", ""),
        ("```python\nx = 1\n```", "x = 1"),
        ("pre\n```python\ndef f():\n    return 1\n```\npost", "def f():\n    return 1"),
        ("```py\ny=2\n```", "y=2"),
    ])
    def test_extract_python_blocks(self, text, expected):
        assert _extract_python_blocks(text) == expected


class _FakeLLM:
    """Behaves like the real LLMClient but deterministic for unit tests."""
    def __init__(self, script=None):
        # script: list of (text, finish) responses consumed in order
        self.script = script or [("```python\nX=1\n```", "stop")]
        self.i = 0
        self.calls = []

    def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
        self.calls.append({"messages": messages, "model": model})
        text, finish = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return text, finish


class TestCodingAgentUnit:
    def test_empty_response_is_failure(self):
        """Rule 8: empty/whitespace output is FAILURE, never a success."""
        llm = _FakeLLM(script=[("   ", "stop")])
        agent = CodingAgent("DEVELOPER", llm)
        res = agent.turn("task")
        assert res["ok"] is False
        assert res["error"] == "empty_response"
        assert len(agent.history) == 0  # nothing committed

    def test_error_response_is_failure(self):
        llm = _FakeLLM(script=[("[Error responding after 0.1s: boom]", "error")])
        agent = CodingAgent("DEVELOPER", llm)
        res = agent.turn("task")
        assert res["ok"] is False
        assert res["error"] == "llm_error"

    def test_valid_response_committed_to_history(self):
        llm = _FakeLLM(script=[("```python\n\nZ=3\n```", "stop")])
        agent = CodingAgent("DEVELOPER", llm)
        res = agent.turn("task")
        assert res["ok"] is True
        assert len(agent.history) == 1


class TestCodingMultiAgentUnit:
    def test_plan_develop_critique_trace(self):
        script = [
            ("PLAN: create module x\nTESTS: 3 cases", "stop"),
            ("```python\ndef x():\n    return 1\n```", "stop"),
            ("```python\ndef x():\n    return 2\n```", "stop"),
        ]
        ma = CodingMultiAgent("http://fake/v1", "unused", on_event=None,
                              llm_client=_FakeLLM(script=script))
        p = ma.plan("prompt", "Python")
        d = ma.develop(p["response"], "Python")
        c = ma.critique("src", {"output": "E failed"}, "Python")
        assert p["ok"] and d["ok"] and c["ok"]
        assert p["agent"] == "PLANNER"
        assert d["agent"] == "DEVELOPER"
        assert c["agent"] == "CRITIC"
        # responses recorded
        assert "def x" in d["response"]

    def test_role_model_uses_model_config(self):
        class _MC:
            def get_model(self, role):
                return "my-model:" + role
        ma = CodingMultiAgent("http://x/v1", "k", model_config=_MC(),
                              llm_client=_FakeLLM())
        assert ma.role_model("DEVELOPER") == "my-model:developer"

    def test_role_model_no_hardcode_default(self):
        # Rule 13: without config, model is "" (resolved by router/default).
        ma = CodingMultiAgent("http://x/v1", "k", llm_client=_FakeLLM())
        assert ma.role_model("DEVELOPER") == ""


# ── LLM availability probe (honest) ──────────────────────────────────────
class TestProbe:
    def test_probe_returns_dict_never_raises(self):
        # Must not raise even with an unreachable/aug-required backend.
        res = probe_llm("http://localhost:59999/v1", "x")
        assert isinstance(res, dict)
        assert "available" in res

    def test_resolve_credentials_prefers_env_or_config(self):
        base, key = resolve_llm_credentials(base_url="", api_key="")
        # Either env or config fallback -> non-empty base
        assert isinstance(base, str) and base.endswith("/v1") or base.endswith("/")


# ── LIVE integration: only runs if a real, authenticated LLM is reachable ─
_has_llm = probe_llm(*resolve_llm_credentials()).get("available")
# A model the backend actually lists (so the live run does not 400 on an
# unloaded default like a router-picked model nobody configured for coding).
_live_models = probe_llm(*resolve_llm_credentials()).get("models") or []
_live_dev = next((m for m in _live_models
                  if any(s in m for s in ("python", "sft", "instruct", "tech"))),
                 (_live_models[0] if _live_models else None))


@pytest.mark.skipif(not (_has_llm and _live_dev),
                    reason="No reachable+authenticated+model-able LLM backend")
class TestLiveMultiAgentIntegration:
    """Proves REAL LLM agents participate (Phase 15 item #4).

    Runs only when probe_llm() reports an authenticated backend with models.
    This is the test that demonstrates the execution path is truly multi-agent.
    """

    def test_real_llm_multi_agent_run(self, tmp_path):
        cfg = CodeLabConfig(
            prompt="Create a Python function fibonacci(n) with unit tests.",
            multi_agent=True,
            max_iterations=3,
            run_id="live_ma_1",
            role_models={"developer": _live_dev, "planner": _live_dev,
                         "critic": _live_dev, "reviewer": _live_dev,
                         "judge": _live_dev},
        )
        eng = build_default_engine(cfg, base_dir=tmp_path)
        res = eng.run()
        # A REAL multi-agent execution actually happened against the live backend:
        # the mode is multi-agent, the backend was reachable/authenticated, and real
        # PLANNER + DEVELOPER agent turns were recorded. Whether a specific dev LLM
        # produced a *passing* turn depends on model output quality (not on wiring),
        # so this live smoke test asserts participation, not guaranteed success.
        assert res["execution_mode"] == "multi_agent", "not in multi-agent mode"
        assert res["llm_available"] is True
        trace = res.get("agent_trace", [])
        assert any(t.get("agent") == "PLANNER" for t in trace), \
            "no real PLANNER agent turn recorded"
        assert any(t.get("agent") == "DEVELOPER" for t in trace), \
            "no real DEVELOPER agent turn recorded"
        # When the run produced a file, the workspace is the source of truth.
        if res.get("files_created"):
            assert (tmp_path / "live_ma_1" / "workspace").exists()

    def test_real_llm_repair_path_on_failure(self, tmp_path):
        # Force a failing deterministic test against LLM-produced code to
        # exercise the CRITIC repair loop with REAL agent turns.
        cfg = CodeLabConfig(
            prompt="Create a Python function fibonacci(n) with unit tests.",
            multi_agent=True,
            max_iterations=5,
            run_id="live_ma_repair",
            role_models={"developer": _live_dev, "planner": _live_dev,
                         "critic": _live_dev, "reviewer": _live_dev,
                         "judge": _live_dev},
        )
        # Inject a deliberately-broken source so pytest fails first.
        base = tmp_path / "live_ma_repair" / "workspace"
        base.mkdir(parents=True, exist_ok=True)
        (base / "fibonacci.py").write_text("def fibonacci(n):\n    return 'wrong'\n")
        (base / "test_fibonacci.py").write_text(
            "from fibonacci import fibonacci\n"
            "def test_a():\n    assert fibonacci(0) == []\n"
            "def test_b():\n    assert fibonacci(10) == [0,1,1,2,3,5,8,13,21,34]\n"
        )
        eng = build_default_engine(cfg, base_dir=tmp_path)
        # Re-run engine (will re-write files but existing failing file forces
        # at least one FAIL; the critic may repair or honestly report).
        res = eng.run()
        assert res["execution_mode"] == "multi_agent"
