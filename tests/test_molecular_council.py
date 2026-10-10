"""Molecular Discovery Council RoleTemplate tests.

Spec: MOLECULAR_DISCOVERY_COUNCIL_V1 — a 7-role, long-running molecular-design
research team. It must:

- be Debate-compatible (dispatches through the SAME stable DebateEngine),
- hard-code NO model ids (only configurable MODEL SLOTS),
- keep MODEL != ROLE != PERSONA,
- inject its global scientific SHARED CONTEXT into every agent prompt,
- carry the scientific response presentation contract (§78),
- NOT auto-start when created.

All tests use the deterministic StubLLM (no backend).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests._debate_stub_llm import StubLLM  # noqa: E402

PHILOSOPHERS = {"Existentialist", "Stoic", "Nihilist", "Spiritual", "Skeptic", "Pragmatist"}
POOL = ["model-a", "model-b", "model-c"]
TEMPLATE_ID = "MOLECULAR_DISCOVERY_COUNCIL_V1"
SLOTS = {"GENERAL_REASONING_MODEL", "CHEMISTRY_SPECIALIST_MODEL", "BIOCHEMISTRY_SPECIALIST_MODEL"}


@pytest.fixture()
def tpl():
    from role_templates.builtins import molecular_discovery_council
    return molecular_discovery_council()


@pytest.fixture()
def stub():
    return StubLLM(models=POOL, speaker_cycle=["Molecular Visionary", "Organic Chemist"])


def _config(**kw):
    from debate_lab.config import DebateLabConfig
    base = dict(topic="Can we design a benign water-purification material from recyclable polymers?",
                template_id=TEMPLATE_ID, model_pool=POOL, max_turns=3)
    base.update(kw)
    return DebateLabConfig(**base)


def _controller(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    factory = DebateSessionFactory(llm_client=stub, base_dir=tmp_path)
    return DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))


# ── structure ──────────────────────────────────────────────────────────────
def test_1_registers_and_is_debate_compatible(tpl):
    from debate_lab.validation import validate_debate_template
    assert tpl.template_id == TEMPLATE_ID
    assert tpl.executor_type == "debate"
    # exactly one moderator + 6 participants, unique role_ids
    assert validate_debate_template(tpl) is None
    role_ids = [r.role_id for r in tpl.roles]
    assert role_ids.count("moderator") == 1
    assert len(role_ids) == len(set(role_ids)) == 7


def test_2_no_hardcoded_model_ids_only_slots(tpl):
    for r in tpl.roles:
        assert r.model_slot in SLOTS, r.model_slot
        # a slot is a NAMED slot, never a concrete model id
        assert not r.model_slot.startswith("model-")
        assert r.default_persona == ""  # generic council: no persona coupling


def test_3_expected_slot_mapping(tpl):
    by_id = {r.role_id: r.model_slot for r in tpl.roles}
    assert by_id["organic-chemist"] == "CHEMISTRY_SPECIALIST_MODEL"
    assert by_id["biochemist"] == "BIOCHEMISTRY_SPECIALIST_MODEL"
    assert by_id["molecular-visionary"] == "GENERAL_REASONING_MODEL"
    assert by_id["mechanistic-skeptic"] == "GENERAL_REASONING_MODEL"
    assert by_id["safety-guardian"] == "GENERAL_REASONING_MODEL"


def test_4_response_contract_and_shared_context(tpl):
    assert tpl.response_contract == [
        "ARGUMENT", "RATIONALE", "EVIDENCE", "HYPOTHESIS", "UNCERTAINTY", "NEXT"]
    sc = tpl.shared_context
    # global scientific rules actually present
    for needle in ("FACT / SUPPORTED_INFERENCE", "CANDIDATE_ID", "SAFE_DIRECTION",
                   "BROAD EXPLORATION", "NEW_WITHIN_THIS_INVESTIGATION"):
        assert needle in sc
    # no operational recipe guidance
    assert "exact quantities" in sc  # explicitly forbidden = present as a rule


def test_5_summary_exposes_slots_and_shared_context(tpl):
    from debate_lab.validation import template_summary
    s = template_summary(tpl)
    assert s["response_contract"] == tpl.response_contract
    assert s["has_shared_context"] is True
    assert {r["model_slot"] for r in s["roles"]} == SLOTS


# ── execution ──────────────────────────────────────────────────────────────
def test_6_council_run_only_council_speakers(stub, tmp_path):
    ctrl = _controller(stub, tmp_path)
    view = ctrl.create_run(_config())
    assert ctrl.start_run(view.run_id, wait=True)
    run = ctrl.get_run(view.run_id)
    assert run["status"] == "completed"
    assert run["result"]["turns_committed"] == 3
    speakers = {e["speaker"] for e in run["events"] if e["type"] == "TURN_COMMITTED"}
    # only registered council roles spoke — no philosophers leaked in
    assert speakers <= {"Molecular Visionary", "Organic Chemist"}
    assert not (speakers & PHILOSOPHERS)
    # provenance carries contract + shared_context hash + slots
    p = run["result"]["provenance"]
    assert p["template_id"] == TEMPLATE_ID
    assert p["response_contract"] == tpl_contract()
    assert p["shared_context_hash"]
    slots = {r["role_id"]: r["model_slot"] for r in p["effective_roles"]}
    assert slots["organic-chemist"] == "CHEMISTRY_SPECIALIST_MODEL"
    assert slots["biochemist"] == "BIOCHEMISTRY_SPECIALIST_MODEL"


def tpl_contract():
    from role_templates.builtins import molecular_discovery_council
    return molecular_discovery_council().response_contract


def test_7_pinned_role_model_honored(stub, tmp_path):
    ctrl = _controller(stub, tmp_path)
    cfg = _config(role_models={"organic-chemist": "model-b"})
    view = ctrl.create_run(cfg)
    assert ctrl.start_run(view.run_id, wait=True)
    run = ctrl.get_run(view.run_id)
    hits = [e for e in run["events"] if e["type"] == "TURN_COMMITTED"
            and e["role"] == "organic-chemist"]
    assert hits and all(e["actual_model"] == "model-b" for e in hits)


def test_8_shared_context_injected_into_participant_prompts(stub, tmp_path):
    ctrl = _controller(stub, tmp_path)
    view = ctrl.create_run(_config())
    assert ctrl.start_run(view.run_id, wait=True)
    run = ctrl.get_run(view.run_id)
    prompts = run["result"]["provenance"]["effective_role_prompts"]
    for rid in ("organic-chemist", "molecular-visionary", "biochemist"):
        assert rid in prompts
    # prompt source is 'layered' (generic, not a persona)
    assert prompts["organic-chemist"]["source"] == "layered"
    assert prompts["organic-chemist"]["model_slot"] == "CHEMISTRY_SPECIALIST_MODEL"


def test_9_shared_context_reaches_moderator(stub, tmp_path):
    from philosophical_council.agents.moderator import ModeratorAgent
    m = ModeratorAgent(allowed_speakers=["Molecular Visionary", "Organic Chemist"],
                       shared_context="GLOBAL SCIENTIFIC RULES\nCANDIDATE_ID: MOL-XXXX")
    assert "TEMPLATE SHARED CONTEXT" in m.system_prompt
    assert "CANDIDATE_ID" in m.system_prompt
    # backward compatible: no shared_context -> unchanged prompt shape
    m2 = ModeratorAgent(allowed_speakers=["A"])
    assert "TEMPLATE SHARED CONTEXT" not in m2.system_prompt


def test_10_create_does_not_auto_start(stub, tmp_path):
    ctrl = _controller(stub, tmp_path)
    view = ctrl.create_run(_config())
    assert view.to_dict()["status"] == "pending"
    # nothing auto-executed before start
    assert ctrl.get_run(view.run_id)["status"] == "pending"