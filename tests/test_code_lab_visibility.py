"""Code Lab agent-visibility + failure-diagnostics regression tests (GOAL 12).

Each test drives the REAL CodeLabEngine (not a mock of it). For multi-agent
cases the only injected piece is the LLM layer — a deterministic stub ChatLLM
passed via CodeLabEngine injection so no network and no API key is needed.
"Judge" here is the Code Lab SemanticCodeJudge; the absent hermes-debate
JudgeAgent is out of scope.

Terminal semantics asserted (GOAL 4/5):
  - RUN_COMPLETED only on success
  - RUN_FAILED on failure
  - judge status NOT_REACHED (pipeline stopped earlier) vs UNAVAILABLE
    (would have run, no backend) vs PASS/FAIL/ERROR
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_lab.config import CodeLabConfig
from code_lab.engine import CodeLabEngine, build_default_engine


@pytest.fixture(scope="module")
def base_dir(tmp_path_factory) -> Path:
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="lm_codelab_visibility_"))
    return d


# ── deterministic ChatLLM stub (returns scripted responses, no network) ───
class _StubChat:
    def __init__(self, script):
        # script: list of (text, finish)
        self.script = list(script)
        self.i = 0
        self.calls = []

    def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
        self.calls.append(model)
        text, finish = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return text, finish

    def get_models(self):  # -> list[str], not a list wrapper
        return ["stub-model"]


def _make_engine(run_id, script, base_dir, prompt, language="Python"):
    """Build an engine whose LLM layer is a stub; multi_agent forced on."""
    cfg = CodeLabConfig(run_id=run_id, prompt=prompt, language=language,
                        multi_agent=True, max_iterations=3)
    engine = CodeLabEngine(config=cfg, base_dir=base_dir)

    def _faked_availability():
        return {"llm_available": True, "llm_error": None, "llm_models": ["stub-model"]}

    def _faked_multi_agent():
        from code_lab.multiagent import CodingMultiAgent
        return CodingMultiAgent("http://fake/v1", "", llm_client=_StubChat(script),
                                on_event=engine._agent_event, run_id=cfg.run_id)

    engine._check_llm_availability = _faked_availability
    engine._new_coding_multi_agent = _faked_multi_agent
    return engine


P_PLAN = "PLAN: module x\nTESTS: 3 cases\n"
P_OK = "```python\ndef solve(x):\n    return x * 2\n```"
P_SRC = "```python\ndef solve(x):\n    return x * 2\n```"
P_PATCH = "```python\ndef solve(x):\n    return x * 2\n```"


# ── A: Planner succeeds, Developer empty response ─────────────────────────
class TestEmptyDeveloper:
    def test_empty_developer_is_explicit_failure(self, base_dir):
        # script order: PLANNER ok, DEVELOPER empty/whitespace
        script = [(P_PLAN, "stop"), ("   \n  ", "stop")]
        eng = _make_engine("vis_empty", script, base_dir,
                           "Create a function solve(x) with unit tests.")
        res = eng.run()

        assert res["status"] == "failed"
        types = [e["type"] for e in eng.events]

        # GOAL 3: explicit failure event, distinct from a successful response
        assert "AGENT_FAILED" in types
        agent_fail = next(e for e in eng.events if e["type"] == "AGENT_FAILED")
        assert agent_fail["role"] == "DEVELOPER"
        assert agent_fail["error_type"]  # classified (empty_response)

        # GOAL 2: AGENT_STARTED/AGENT_RESPONSE carry structured metadata
        starts = [e for e in eng.events if e["type"] == "AGENT_STARTED"]
        assert any(e.get("role") == "PLANNER" and e.get("stage") for e in starts)
        assert any(e.get("role") == "DEVELOPER" for e in starts)
        resp = [e for e in eng.events if e["type"] == "AGENT_RESPONSE"]
        assert all("role" in e and "duration_ms" in e and "response_length" in e
                   for e in resp)

        # no files / tests reached
        assert not any(e["type"] == "FILE_CREATED" for e in eng.events)
        assert not any(e["type"] == "TEST_STARTED" for e in eng.events)
        assert res["files_created"] == []
        assert res["iterations"] == 0

        # GOAL 5: judge NOT_REACHED (developer failed before judge), not UNAVAILABLE
        assert res["semantic_judge"]["status"] == "NOT_REACHED"
        assert res["semantic_judge"]["reached"] is False

        # GOAL 4: terminal event is RUN_FAILED, not RUN_COMPLETED
        assert not any(e["type"] == "RUN_COMPLETED" for e in eng.events)
        assert any(e["type"] == "RUN_FAILED" for e in eng.events)

    def test_planner_ok_developer_empty_has_structured_response(self, base_dir):
        script = [(P_PLAN, "stop"), ("", "stop")]
        eng = _make_engine("vis_empty2", script, base_dir,
                           "Create a function solve(x) with unit tests.")
        eng.run()
        resps = [e for e in eng.events if e["type"] == "AGENT_RESPONSE"]
        planner = [e for e in resps if e.get("role") == "PLANNER"]
        assert planner and planner[0]["ok"] is True
        assert "response_present" in planner[0]
        # developer failed -> AGENT_FAILED present, developer has no success event
        assert any(e.get("type") == "AGENT_FAILED" and e.get("role") == "DEVELOPER"
                   for e in eng.events)


# ── B: Developer succeeds and creates files ──────────────────────────────
class TestDeveloperCreatesFiles:
    def test_success_emits_file_created_events(self, base_dir):
        script = [(P_PLAN, "stop"), (P_SRC, "stop")]
        eng = _make_engine("vis_files", script, base_dir,
                           "Create a Python function fibonacci(n) with unit tests.")
        res = eng.run()
        created = [e for e in eng.events if e["type"] == "FILE_CREATED"]
        assert len(created) >= 2  # source + test
        # GOAL 8: relative path, operation, stage, agent role — no absolute paths
        for e in created:
            assert e["file"] and not Path(e["file"]).is_absolute()
            assert e["operation"] == "created"
            assert e["agent_role"] == "DEVELOPER"
        assert res["status"] in ("passed", "failed")  # env-dependent pytest result


# ── C: tests fail and Critic repair runs ─────────────────────────────────
class TestRepairIterations:
    def test_repair_iteration_is_visible(self, base_dir):
        # DEVELOPER returns code that fails the generated tests; CRITIC emits
        # a patch; second test run passes.
        script = [
            (P_PLAN, "stop"),
            ("```python\ndef solve(x):\n    return None\n```", "stop"),  # wrong impl
            (P_PATCH, "stop"),  # CRITIC patch (still wrong for fibonacci but is a change)
        ]
        eng = _make_engine("vis_repair", script, base_dir,
                           "Create a Python function fibonacci(n) with unit tests.")
        res = eng.run()
        types = [e["type"] for e in eng.events]
        assert "CRITIQUE_STARTED" in types
        assert "REPAIR_STARTED" in types
        assert any(e["type"] == "FILE_MODIFIED" for e in eng.events)
        # iterations counter corresponds to actual verify/repair iterations
        assert res["iterations"] >= 1
        assert any(e["type"] == "TEST_FAILED" for e in eng.events)


# ── D: tests pass (deterministic authority) ──────────────────────────────
class TestDeterministicPass:
    def test_deterministic_pass_keeps_validation_authority(self, base_dir):
        cfg = CodeLabConfig(run_id="vis_pass", multi_agent=False,
                            prompt="Create a Python function fibonacci(n) with unit tests.")
        eng = build_default_engine(cfg, base_dir=base_dir)
        res = eng.run()
        assert res["status"] == "passed"
        assert res["validation"]["deterministic_validation"] is True
        assert res["deterministic_validation_status"] == "PASS"
        types = [e["type"] for e in eng.events]
        assert "TEST_PASSED" in types and "RUN_COMPLETED" in types
        # good run -> not RUN_FAILED
        assert not any(e["type"] == "RUN_FAILED" for e in eng.events)


# ── E: judge backend UNAVAILABLE after deterministic PASS ────────────────
class TestJudgeUnavailableVsNotReached:
    def test_judge_unavailable_after_det_pass(self, base_dir):
        # deterministic PASS with an LLM that was never reached -> the judge
        # stage is UNAVAILABLE (not NOT_REACHED).
        cfg = CodeLabConfig(run_id="vis_j_unavail", multi_agent=False,
                            prompt="Create a Python function is_prime(n) with unit tests.")
        eng = build_default_engine(cfg, base_dir=base_dir)
        res = eng.run()
        assert res["status"] == "passed"
        assert res["semantic_judge"]["status"] == "UNAVAILABLE"
        assert res["semantic_judge"]["reached"] is True
        assert res["semantic_judge"]["reason"] == "llm_backend_unavailable"

    def test_judge_not_reached_when_developer_failed(self, base_dir):
        script = [(P_PLAN, "stop"), (" ", "stop")]
        eng = _make_engine("vis_j_notreached", script, base_dir,
                           "Create a function solve(x) with unit tests.")
        res = eng.run()
        assert res["status"] == "failed"
        assert res["semantic_judge"]["status"] == "NOT_REACHED"
        assert res["semantic_judge"]["reached"] is False


# ── F: run stopped ───────────────────────────────────────────────────────
class TestStopped:
    def test_stop_requests_explicit_terminal(self, base_dir):
        eng = _make_engine_with_self_requesting_stop(base_dir)
        res = eng.run()
        assert res["status"] == "stopped"
        assert any(e["type"] == "RUN_STOPPED" for e in eng.events)
        assert res["semantic_judge"]["status"] == "NOT_REACHED"


def _make_engine_with_self_requesting_stop(base_dir):
    """A run that requests stop before the first test outcome."""
    cfg = CodeLabConfig(run_id="vis_stop", multi_agent=True, max_iterations=3,
                        prompt="Create a function solve(x) with unit tests.")
    engine = CodeLabEngine(config=cfg, base_dir=base_dir)
    from code_lab.multiagent import CodingMultiAgent
    engine._check_llm_availability = lambda: {
        "llm_available": True, "llm_error": None, "llm_models": ["stub-model"]}
    engine._new_coding_multi_agent = lambda: CodingMultiAgent(
        "http://fake/v1", "", llm_client=_StubChat([(P_PLAN, "stop"), (P_SRC, "stop")]),
        on_event=engine._agent_event, run_id=cfg.run_id)

    # Stop injected: immediately after files are written, set the stop flag so
    # the bounded loop sees it on the first iteration.
    original = engine._write_files
    def _write_and_stop(files):
        original(files)
        engine.stop_requested = True
    engine._write_files = _write_and_stop
    return engine


# ── run_id correlation (GOAL 11) ─────────────────────────────────────────
class TestRunIdCorrelation:
    def test_run_id_correlates_events_result_and_raw(self, base_dir):
        cfg = CodeLabConfig(run_id="vis_corr", multi_agent=False,
                            prompt="Create a Python function fibonacci(n) with unit tests.")
        eng = build_default_engine(cfg, base_dir=base_dir)
        res = eng.run()
        run_id = "vis_corr"
        assert res["run_id"] == run_id
        # every event carries the run_id
        for e in eng.events:
            assert e.get("run_id") == run_id, e
        # RAW snapshot keyed by run_id
        raw_dir = base_dir / run_id / "raw"
        assert (raw_dir / f"run_{run_id}.json").exists()
        snap = json.loads((raw_dir / f"run_{run_id}.json").read_text(encoding="utf-8"))
        assert snap.get("run_id") == run_id
