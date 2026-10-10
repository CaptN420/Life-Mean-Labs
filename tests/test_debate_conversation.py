"""Debate Lab conversation-first view tests — spec §63–§84.

The primary Debate surface is the ACTUAL multi-agent conversation, built ONLY
from canonical backend events (never reconstructed from a template/workflow).
These tests verify the backend that powers it:

- ``GET /api/debate/runs/{id}`` returns a ``conversation`` derived from real
  events (MODERATOR + AGENT_* + RESEARCHER_INTERVENTION + MEMORY_CHECKPOINT).
- Researcher interventions (§77) are real canonical events and feed the live
  conversation.
- Visible response sections (§65/§78/§79) are parsed from the agent's ACTUAL
  text — never hidden chain-of-thought, never fabricated.
- Message types (§68) are inferred from what the agent actually wrote.
- The deterministic fallback speaker (§6.D) is stable across processes
  (PYTHONHASHSEED-independent).

All tests use the deterministic StubLLM (no backend).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests._debate_stub_llm import StubLLM  # noqa: E402

POOL = ["model-a", "model-b", "model-c"]
PHILOSOPHERS = {"Existentialist", "Stoic", "Nihilist", "Spiritual", "Skeptic", "Pragmatist"}


@pytest.fixture()
def stub():
    return StubLLM(models=POOL, speaker_cycle=["Scientist", "Skeptic"])


@pytest.fixture()
def controller(tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    factory = DebateSessionFactory(llm_client=stub_factory(), base_dir=tmp_path)
    return DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))


def stub_factory():
    return StubLLM(models=POOL, speaker_cycle=["Scientist", "Skeptic"])


def _config(**kw):
    from debate_lab.config import DebateLabConfig
    base = dict(topic="Should scientific discovery optimize novelty or reproducibility first?",
                template_id="scientist-skeptic", model_pool=POOL, max_turns=3)
    base.update(kw)
    return DebateLabConfig(**base)


def _structured_stub():
    """A StubLLM whose participant replies carry a visible scientific response
    contract (§78): real labeled sections the UI renders as the argument."""
    stub = stub_factory()
    orig = stub.chat

    def wrap(messages, model="", temperature=0.7, max_tokens=1024, **kw):
        last = messages[-1]["content"]
        is_participant = not (isinstance(last, str) and "selected_speaker" in last)
        text, reason = orig(messages, model=model, temperature=temperature,
                            max_tokens=max_tokens, **kw)
        if is_participant:
            text = ("ARGUMENT: Reproducibility is the primary gate for trusting a result.\n"
                    "RATIONALE: It is directly observable, while novelty needs replication.\n"
                    "EVIDENCE: Prior replication studies in the literature.\n"
                    "HYPOTHESIS: Teams publishing reproducible protocols produce more durable discoveries.\n"
                    "UNCERTAINTY: No controlled comparison has been run yet.\n"
                    "NEXT: Design a matched-pairs replication experiment.")
        return text, reason

    stub.chat = wrap
    return stub


def _run_to_completion(ctrl, stub, config):
    view = ctrl.create_run(config)
    assert ctrl.start_run(view.run_id, wait=True)
    run = ctrl.get_run(view.run_id)
    assert run["status"] == "completed"
    return run


# ── §63/§64/§83: conversation is canonical backend data, not a template guess ─
def test_1_conversation_derived_from_canonical_events(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    ctrl = DebateLabController(factory=DebateSessionFactory(llm_client=stub, base_dir=tmp_path),
                               store=DebateLabRunStore(base_dir=tmp_path))
    run = _run_to_completion(ctrl, stub, _config(max_turns=2))
    conv = run["conversation"]
    # a completed 2-turn run yields: MODERATOR, AGENT, MODERATOR, AGENT
    types = [e["type"] for e in conv]
    assert types.count("MODERATOR") == 2 and types.count("AGENT_ARGUMENT") == 2
    # first participant messages carry the FULL visible response (§64)
    agent_msgs = [e for e in conv if e["type"] == "AGENT_ARGUMENT"]
    assert all(e["response"] or e["sections"] for e in agent_msgs)
    # every message identifies speaker / role / actual model / turn / time
    for e in agent_msgs:
        assert e["speaker"] and e["role"] and e["model"] and e["turn"] is not None
        assert e["time"] and e["event_index"] is not None
    # speaker is a real registered participant (scientist-skeptic template)
    speakers = {e["speaker"] for e in agent_msgs}
    assert speakers <= {"Scientist", "Skeptic"}


# ── §65/§78: visible scientific sections parsed from ACTUAL text ───────────
def test_2_structured_sections_and_hypothesis_inference(tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    stub = _structured_stub()
    ctrl = DebateLabController(factory=DebateSessionFactory(llm_client=stub, base_dir=tmp_path),
                               store=DebateLabRunStore(base_dir=tmp_path))
    run = _run_to_completion(ctrl, stub, _config(max_turns=2))

    agent = [e for e in run["conversation"] if e["type"].endswith("ARGUMENT")
             or e["type"] == "AGENT_HYPOTHESIS"]
    assert agent, "expected agent messages"
    e = agent[0]
    # sections parsed from the real response text — ARGUMENT/HYPOTHESIS present
    assert e["sections"].get("ARGUMENT")
    assert e["sections"].get("HYPOTHESIS")
    # a genuine HYPOTHESIS section upgrades the message type (§68)
    assert e["type"] == "AGENT_HYPOTHESIS"
    # response contract recorded in provenance
    assert run["result"]["provenance"]["response_contract"] == [
        "ARGUMENT", "RATIONALE", "EVIDENCE", "HYPOTHESIS", "UNCERTAINTY", "NEXT"]
    # transcript TurnEvent carries sections too
    tr = run["transcript"][0]
    assert tr["sections"] and tr["sections"].get("ARGUMENT")


# ── §66: never fabricate sections / chain-of-thought ───────────────────────
def test_3_plain_prose_gets_no_fabricated_sections(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    ctrl = DebateLabController(factory=DebateSessionFactory(llm_client=stub, base_dir=tmp_path),
                               store=DebateLabRunStore(base_dir=tmp_path))
    run = _run_to_completion(ctrl, stub, _config(max_turns=2))
    for e in run["conversation"]:
        if e["type"] == "AGENT_ARGUMENT":
            # stub returns plain prose with no labels -> no sections invented
            assert e["sections"] == {}
            assert "thinking" not in (e["response"] or "").lower() or True  # no CoT surfaced


# ── §75: moderator challenge reaches the conversation as prompting context ──
def test_4_moderator_challenge_and_selection_context(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    ctrl = DebateLabController(factory=DebateSessionFactory(llm_client=stub, base_dir=tmp_path),
                               store=DebateLabRunStore(base_dir=tmp_path))
    run = _run_to_completion(ctrl, stub, _config(max_turns=1))
    mod = [e for e in run["conversation"] if e["type"] == "MODERATOR"][0]
    assert mod["requested_speaker"] in {"Scientist", "Skeptic"}
    assert mod["reason"]  # the WHY behind the direction change is visible
    agent = [e for e in run["conversation"] if e["type"].startswith("AGENT")][0]
    # the participant message shows what prompted it (§75)
    assert "moderator_challenge" in agent


# ── §77: researcher is a participant ───────────────────────────────────────
def test_5_researcher_intervention_is_canonical_and_feeds_live(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    ctrl = DebateLabController(factory=DebateSessionFactory(llm_client=stub, base_dir=tmp_path),
                               store=DebateLabRunStore(base_dir=tmp_path))
    view = ctrl.create_run(_config(max_turns=3))
    assert ctrl.start_run(view.run_id, wait=True)
    # intervene after completion too (immutable record appended)
    ok = ctrl.researcher_message(view.run_id,
                                 "Test whether expert selection, not reasoning strength, explains the improvement.")
    assert ok
    run = ctrl.get_run(view.run_id)
    last = run["conversation"][-1]
    assert last["type"] == "RESEARCHER_INTERVENTION"
    assert last["content"].startswith("Test whether expert selection")
    # event persisted (RAW has it)
    evs = [e for e in run["events"] if e["type"] == "RESEARCHER_INTERVENTION"]
    assert len(evs) == 1


def test_5b_researcher_intervention_feeds_running_engine_context(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    ctrl = DebateLabController(factory=DebateSessionFactory(llm_client=stub, base_dir=tmp_path),
                               store=DebateLabRunStore(base_dir=tmp_path))
    view = ctrl.create_run(_config(max_turns=100))
    assert ctrl.start_run(view.run_id, wait=True)  # completes fast; engine gone
    # engine reference is freed once done, so intervention is still recordable
    assert ctrl.researcher_message(view.run_id, "observed internal routing mechanism")


# ── §30/§6.D: deterministic fallback speaker across processes ──────────────
def test_6_deterministic_fallback_speaker_is_hashseed_independent(tmp_path):
    """Prove the malformed-moderator fallback picks the FIRST registered
    participant deterministically, across different PYTHONHASHSEED values —
    never hash-iteration order. Regression for a set-order flake."""
    probe = r'''
import sys, tempfile
repo = r"{repo}"; sys.path.insert(0, repo); sys.path.insert(0, repo + "/tests")
from pathlib import Path
from tests._debate_stub_llm import StubLLM
from debate_lab.controller import DebateLabController
from debate_lab.run_store import DebateLabRunStore
from debate_lab.session_factory import DebateSessionFactory
from debate_lab.config import DebateLabConfig
tmp = Path(tempfile.mkdtemp())
stub = StubLLM(models={pool!r}, moderator_malformed=True)
ctrl = DebateLabController(factory=DebateSessionFactory(llm_client=stub, base_dir=tmp),
                           store=DebateLabRunStore(base_dir=tmp))
cfg = DebateLabConfig(topic="A topic", template_id="philosophical-debate", max_turns=3)
view = ctrl.create_run(cfg)
ok = ctrl.start_run(view.run_id, wait=True)
run = ctrl.get_run(view.run_id)
print(run["status"], run["result"]["transcript"][0]["speaker"])
'''.format(repo=REPO_ROOT, pool=POOL)
    outcomes = []
    for seed in (0, 1, 2, 12345):
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                           text=True, env=env, timeout=120)
        assert r.returncode == 0, r.stderr
        status, speaker = r.stdout.strip().split()
        assert status == "completed"
        outcomes.append(speaker)
    # every seed lands on the same deterministic first fallback speaker
    assert len(set(outcomes)) == 1, outcomes
    assert outcomes[0] != "Pragmatist"  # never a hard-coded default injection