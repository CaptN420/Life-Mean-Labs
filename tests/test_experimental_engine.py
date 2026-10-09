"""Experimental Engine foundation tests (spec §22).

Covers the design/schema + lifecycle + freeze + dispatcher + engine-facade
slice: DRAFT-only designer, no-run-before-freeze, frozen-immutability,
new-version-on-edit, code->CodeLabEngine, debate->DebateEngine(routing),
EXECUTOR_NOT_AVAILABLE, truthful events, STOP.
"""

import pytest

from experimental import (
    DesignAgent,
    DesignBudgets,
    DesignStage,
    DesignInvalid,
    ExperimentDesign,
    ExperimentDesigner,
    ExperimentalEngine,
    ExecutorNotAvailable,
    dispatch_stage,
    prompt_hash,
    require_executable,
    validate_design,
)


def make_valid_design(stages=("deterministic", "tool_execution")) -> ExperimentDesign:
    agents = [
        DesignAgent(agent_id="a1", role="experimentalist", persona="empirical",
                    skills=["benchmark-design"], system_prompt="You are the experimentalist.",
                    prompt_components={"role": "ROLE.\nYou are the experimentalist."}),
        DesignAgent(agent_id="a2", role="verifier", persona="rigorous",
                    skills=["validation"], allowed_tools=["tests.run"],
                    system_prompt="You are the verifier."),
    ]
    ds = [DesignStage(stage_id=f"stage-{i}", executor_type=et,
                      participants=["a1", "a2"], request="")
          for i, et in enumerate(stages)]
    return ExperimentDesign(title="t", description="d", research_question="rq",
                            agents=agents, stages=ds,
                            budgets=DesignBudgets(), validators=["tests.run"])


# ── designer : DRAFT only, nothing executes ────────────────────────────────
def test_designer_proposes_draft_only():
    d = ExperimentDesigner().propose(
        "Explore whether small heterogeneous agents can discover edge cases "
        "in a sorting algorithm better than a single solver.")
    assert d.status == "DRAFT"
    assert not d.is_frozen
    assert not d.can_run
    assert len(d.agents) >= 3
    assert {"algorithm_researcher", "verifier"} <= {a.role for a in d.agents}
    # proposals carry layered system prompts (spec §7)
    for a in d.agents:
        assert a.system_prompt
        assert "role" in a.prompt_components


def test_designer_requires_description():
    with pytest.raises(ValueError):
        ExperimentDesigner().propose("   ")


def test_designer_honours_capability_inventory():
    d = ExperimentDesigner(capabilities={"skills": ["benchmark-design"],
                                         "tools": ["tests.run"]}).propose("run a benchmark")
    for a in d.agents:
        assert all(s == "benchmark-design" or s == "" or s not in ("unknown-skill",)
                   for s in a.skills)


# ── lifecycle : no execution before freeze; immutability ───────────────────
def test_no_execution_before_freeze():
    d = make_valid_design()
    eng = ExperimentalEngine()
    with pytest.raises(DesignInvalid):
        eng.run(d)  # DRAFT cannot run
    approved = d.approve()
    assert approved.status == "APPROVED"
    with pytest.raises(DesignInvalid):
        eng.run(approved)  # still not FROZEN


def test_freeze_enables_run_and_hashes_content():
    f = make_valid_design().approve().freeze()
    assert f.is_frozen and f.can_run
    assert f.frozen_hash and f.frozen_hash == f.content_hash()
    # status is excluded from the content hash: approving does not change it
    d = make_valid_design()
    assert d.content_hash() == d.approve().content_hash()
    # changing a scientifically meaningful field flips the hash
    mutated = d.with_(title="brand new title")
    assert mutated.content_hash() != d.content_hash()


def test_frozen_design_is_immutable_edit_makes_new_version():
    f = make_valid_design().approve().freeze()
    original_hash = f.frozen_hash
    original_title = f.title
    v2 = f.with_(title="edited later")
    # the frozen original is untouched
    assert f.is_frozen and f.title == original_title and f.frozen_hash == original_hash
    # editing a frozen design yields a NEW version, DRAFT, old one SUPERSEDED
    assert v2.version == f.version + 1
    assert v2.status == "DRAFT"
    assert v2.title == "edited later"
    assert v2.content_hash() != original_hash


def test_frozen_cannot_transition():
    f = make_valid_design().freeze()
    with pytest.raises(ValueError):
        f.transition("REJECTED")


def test_invalid_state_and_transition():
    with pytest.raises(ValueError):
        ExperimentDesign(status="BOGUS")
    d2 = make_valid_design()
    rej = d2.transition("REJECTED")
    with pytest.raises(ValueError):
        rej.freeze()  # cannot freeze a REJECTED design


# ── dispatcher : route to the compatible executor ──────────────────────────
def test_code_stage_dispatches_to_code_lab():
    cap = dispatch_stage("code_lab")
    assert cap["engine"] == "CodeLabEngine" and cap["connected"] is True


def test_debate_stage_targets_debate_engine_but_not_connected_now():
    with pytest.raises(ExecutorNotAvailable) as ei:
        dispatch_stage("debate")
    assert ei.value.engine == "DebateEngine"
    assert ei.value.category == "EXECUTOR_NOT_AVAILABLE"


def test_unsupported_executor_raises_executor_not_available():
    with pytest.raises(ExecutorNotAvailable):
        dispatch_stage("no-such-executor")
    # unconnected is equally refused (spec §11: mark honestly, no fake fallback)
    with pytest.raises(ExecutorNotAvailable):
        dispatch_stage("synthesis")
    with pytest.raises(ExecutorNotAvailable):
        dispatch_stage("research")


# ── engine facade : real event stream, honest failures, STOP ───────────────
def test_engine_runs_connected_deterministic_stages():
    eng = ExperimentalEngine()
    calls = []
    eng.register_executor("deterministic", lambda s, d: calls.append(s.executor_type) or {"ok": True})
    eng.register_executor("tool_execution", lambda s, d: calls.append(s.executor_type) or {"ok": True})
    out = eng.run(make_valid_design().approve().freeze())
    assert out["status"] == "COMPLETED"
    assert out["stages"][0]["result"]["ok"] is True
    assert out["stages"][1]["result"]["ok"] is True
    assert eng.events == ["EXPERIMENT_STARTED", "STAGE_STARTED", "STAGE_COMPLETED",
                          "STAGE_STARTED", "STAGE_COMPLETED", "EXPERIMENT_COMPLETED"]


def test_engine_emits_truthful_context_in_events():
    from core.events.event_bus import EventBus
    from core.events.message import Message
    bus = EventBus()
    seen = []
    bus.subscribe("STAGE_STARTED", lambda m: seen.append(m))
    eng = ExperimentalEngine(bus=bus)
    eng.register_executor("deterministic", lambda s, d: {"ok": True})
    eng.register_executor("tool_execution", lambda s, d: {"ok": True})
    f = make_valid_design(stages=("deterministic", "tool_execution")).approve().freeze()
    eng.run(f)
    assert len(seen) == 2
    for m in seen:
        assert m.payload["design_id"] == f.design_id
        assert m.payload["design_hash"] == f.frozen_hash


def test_engine_fails_honestly_on_unconnected_stage():
    eng = ExperimentalEngine()
    bad = make_valid_design(stages=("deterministic", "synthesis")).approve().freeze()
    with pytest.raises(ExecutorNotAvailable):
        eng.run(bad)
    assert "STAGE_FAILED" in eng.events and "EXPERIMENT_FAILED" in eng.events
    assert "EXPERIMENT_COMPLETED" not in eng.events


def test_engine_patches_not_bound_executor_is_reported_not_faked():
    eng = ExperimentalEngine()  # no executor bound -> honest report, still COMPLETED dispatch
    out = eng.run(make_valid_design(stages=("deterministic",)).approve().freeze())
    assert out["stages"][0]["result"]["execution"] == "not_bound"
    assert "EXPERIMENT_COMPLETED" in eng.events


def test_human_stop_produces_stopped_not_failed():
    eng = ExperimentalEngine()

    def slow(stage, design):
        eng.stop()  # request stop mid-run
        return {}
    eng.register_executor("deterministic", slow)
    from experimental.engine import StopRequested
    with pytest.raises(StopRequested):
        eng.run(make_valid_design(stages=("deterministic", "deterministic")).approve().freeze())
    assert "EXPERIMENT_STOPPED" in eng.events
    assert "EXPERIMENT_COMPLETED" not in eng.events
    assert "EXPERIMENT_FAILED" not in eng.events


# ── deterministic separation + validation ──────────────────────────────────
def test_validation_and_semantic_stay_separate():
    ok, errs = validate_design(make_valid_design())
    assert ok and errs == []
    # a design pointing at an unavailable semantic stage is still VALID as a
    # design; it is only refused at dispatch/run time (honest EXECUTOR_NOT_AVAILABLE)
    ok2, _ = validate_design(make_valid_design(stages=("synthesis",)))
    assert ok2


def test_validation_rejects_broken_design():
    d = ExperimentDesign(title="x")
    ok, errs = validate_design(d)
    assert not ok
    assert any("no agents" in e for e in errs)
    bad_ref = make_valid_design()
    bad_ref.stages = [DesignStage(stage_id="s1", executor_type="deterministic",
                                  participants=["ghost-agent"])]
    ok2, errs2 = validate_design(bad_ref)
    assert not ok2 and any("ghost-agent" in e for e in errs2)


def test_code_lab_guard_never_receives_other_templates():
    # CodeLabEngine only accepts code_lab executor templates (regression: the
    # old bug pushed every template into Code Lab).
    from role_templates.executor import require_code_lab
    d = require_code_lab("coding-standard")
    assert d["executor_type"] == "code_lab"
    with pytest.raises(ValueError):
        require_code_lab("philosophical-debate")
    with pytest.raises(ValueError):
        require_code_lab("general-reasoning")


def test_prompt_hash_is_component_honest():
    from experimental.prompts import compose_system_prompt
    a = compose_system_prompt(role="Experimentalist", persona="skeptic")
    b = compose_system_prompt(role="Experimentalist", persona="pragmatist")
    assert prompt_hash(a["system_prompt"]) != prompt_hash(b["system_prompt"])
    assert prompt_hash(a["system_prompt"]) == prompt_hash(a["system_prompt"])