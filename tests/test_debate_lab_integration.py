"""Debate Lab integration tests — spec §37 items 1–28 (Final Integration Pass).

Proves the DEBATE LAB is template-driven, model-routable, observable and uses
the EXISTING DebateEngine (no duplicate engine), while keeping the historical
philosophical template working and AutoPilot / Code Lab / memory green.

Every test is backend-independent: the LLM is a deterministic StubLLM.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests._debate_stub_llm import BlockingLLM, StubLLM  # noqa: E402

PHILOSOPHERS = {"Existentialist", "Stoic", "Nihilist", "Spiritual", "Skeptic", "Pragmatist"}
POOL = ["model-a", "model-b", "model-c"]


# ── fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture()
def registry():
    from role_templates.registry import RoleTemplateRegistry
    reg = RoleTemplateRegistry()
    reg.register_builtin()
    return reg


@pytest.fixture()
def stub():
    return StubLLM(models=POOL)


@pytest.fixture()
def controller(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    factory = DebateSessionFactory(llm_client=stub, base_dir=tmp_path)
    return DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))


def _config(**kw):
    from debate_lab.config import DebateLabConfig
    base = dict(topic="Should scientific discovery optimize novelty or reproducibility first?")
    base.update(kw)
    return DebateLabConfig(**base)


def _run(controller, stub, config, wait=True):
    view = controller.create_run(config)
    if config.model_pool:
        from philosophical_council.core.router import ModelRouter
        router = ModelRouter(available_models=config.model_pool)
        router.set_method(config.model_routing_method)
        stub._router = router
    ok = controller.start_run(view.run_id, wait=wait)
    assert ok, "start_run should succeed"
    return view, controller.get_run(view.run_id)


def _wait_terminal(controller, run_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = controller.get_run(run_id)
        if r and r["status"] in ("completed", "stopped", "failed"):
            return r
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not reach a terminal state")


# ── 1. Dashboard no longer routes Debate via AutoPilot ────────────────────
def test_1_dashboard_no_autopilot_debate_text():
    html = (REPO_ROOT / "experiments" / "ui" / "dashboard.html").read_text(encoding="utf-8")
    assert "DEBATE LAB" in html
    assert "No AutoPilot" in html
    old_hint = "Run experiments in"
    assert old_hint not in html or "Debate / Multi-Agent</strong> mode from the" not in html
    assert "from the <em>Autopilot</em> tab" not in html


# ── 2. A Debate run is created directly through the Debate API ─────────────
def test_2_debate_run_created_directly(controller, stub):
    cfg = _config(template_id="philosophical-debate", max_turns=2)
    view, run = _run(controller, stub, cfg)
    assert run["status"] == "completed"
    assert run["result"]["turns_committed"] == 2


# ── 3. Debate Lab reuses the EXISTING DebateEngine ─────────────────────────
def test_3_reuses_existing_debate_engine(controller, stub):
    from philosophical_council.core.debate_engine import DebateEngine
    factory = controller._factory
    session = factory.build(_config(template_id="scientist-skeptic", max_turns=1))
    assert isinstance(session.engine, DebateEngine)


# ── 4. No DebateLabEngine / NewDebateEngine exists ─────────────────────────
def test_4_no_debate_lab_engine_class():
    import debate_lab
    import inspect
    assert not hasattr(debate_lab, "DebateLabEngine")
    assert not hasattr(debate_lab, "NewDebateEngine")
    mods = ["debate_lab.engine", "debate_lab.new_engine"]
    import importlib.util
    for m in mods:
        assert importlib.util.find_spec(m) is None, m
    # and the real engine module is unchanged
    from philosophical_council.core.debate_engine import DebateEngine
    assert DebateEngine.__module__ == "philosophical_council.core.debate_engine"


# ── 5. Historical philosophical-debate template dispatches to DebateEngine ─
def test_5_philosophical_template_runs(controller, stub, registry):
    cfg = _config(template_id="philosophical-debate", max_turns=3)
    view, run = _run(controller, stub, cfg)
    assert run["status"] == "completed"
    assert run["result"]["provenance"]["template_id"] == "philosophical-debate"
    # agents really are the philosophical personas
    assert {t["speaker"] for t in run["result"]["transcript"]} <= PHILOSOPHERS


# ── 6. Generic Scientist + Skeptic template runs (no hidden philosophers) ──
def test_6_generic_template_runs(controller, stub):
    cfg = _config(template_id="scientist-skeptic", max_turns=4, model_pool=POOL)
    view, run = _run(controller, stub, cfg)
    assert run["status"] == "completed"
    speakers = {t["speaker"] for t in run["result"]["transcript"]}
    assert speakers == {"Scientist", "Skeptic"}
    # no hidden dependency on the six philosophers: the run used ONLY its own
    # registered participants ("Skeptic" legitimately overlaps by name with a
    # philosophical school; the meaningful check is that no OTHER philosopher
    # appears and the team is exactly the template's own roster).
    assert not (speakers & (PHILOSOPHERS - {"Skeptic"}))
    assert {t["speaker_role"] for t in run["result"]["transcript"]} <= {"scientist", "skeptic"}


# ── 7. Generic moderator allowed-speaker contract generated dynamically ────
def test_7_moderator_allowed_speakers_dynamic(controller, stub):
    session = controller._factory.build(_config(template_id="scientist-skeptic", max_turns=1))
    moderator = session.engine._moderator
    assert set(moderator.allowed_speakers) == {"Scientist", "Skeptic"}
    prompt = moderator.system_prompt
    assert "Scientist" in prompt and "Skeptic" in prompt
    assert "Existentialist" not in prompt and "Pragmatist" not in prompt
    # engine session speakers match the ACTUAL registered participants
    assert session.engine._valid_speakers == {"Scientist", "Skeptic"}


# ── 8. Malformed moderator output never defaults to Pragmatist ─────────────
def test_8_malformed_moderator_no_pragmatist(tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    bad = StubLLM(models=POOL, moderator_malformed=True)
    factory = DebateSessionFactory(llm_client=bad, base_dir=tmp_path)
    ctrl = DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))
    cfg = _config(template_id="philosophical-debate", max_turns=3)
    view = ctrl.create_run(cfg)
    assert ctrl.start_run(view.run_id, wait=True)
    run = ctrl.get_run(view.run_id)
    assert run["status"] == "completed"
    transcript = run["result"]["transcript"]
    speakers = {t["speaker"] for t in transcript}
    # every speaker is a real registered participant — never an injected one
    assert speakers <= PHILOSOPHERS
    # the fallback does NOT *default* to Pragmatist: the first fallback turn
    # picks the first admissible registered participant (alphabetically
    # Existentialist for the philosophical template), not Pragmatist.
    assert transcript[0]["speaker"] != "Pragmatist"
    fb_mod = [e for e in run["result"]["moderator_inferences"]
              if e.get("selection_mode") == "deterministic_fallback"]
    for e in fb_mod[:1]:
        assert e["actual_speaker"] != "Pragmatist"


# ── 9. Deterministic fallback chooses a valid registered participant ───────
def test_9_deterministic_fallback_valid_participant(controller, stub):
    session = controller._factory.build(_config(template_id="scientist-skeptic", max_turns=1))
    engine = session.engine
    # Force a fallback path through the session participants.
    speaker = engine._default_fallback_speaker()
    assert speaker in {"Scientist", "Skeptic"}
    # A real malformed run must also only ever fall back onto participants.
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    bad = StubLLM(models=POOL, moderator_malformed=True)
    factory = DebateSessionFactory(llm_client=bad, base_dir=tempfile.mkdtemp())
    ctrl = DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tempfile.mkdtemp()))
    view = ctrl.create_run(_config(template_id="scientist-skeptic", max_turns=3))
    assert ctrl.start_run(view.run_id, wait=True)
    run = ctrl.get_run(view.run_id)
    speakers = {t["speaker"] for t in run["result"]["transcript"]}
    assert speakers <= {"Scientist", "Skeptic"}


# ── 10. Generic agent prompt has no forced philosophical language ──────────
def test_10_generic_prompt_no_philosophical_language(controller):
    session = controller._factory.build(_config(template_id="scientist-skeptic", max_turns=1))
    for agent in session.engine._agents.values():
        sp = agent.system_prompt
        assert "philosophical position" not in sp.lower()
        assert "philosophical response" not in sp.lower()
        assert sp.strip()  # not empty
        assert "ROLE:" in sp  # layered generic prompt keeps ROLE distinct


# ── 11. Debate memory alternatives use current session participants ────────
def test_11_memory_alternatives_session_participants(controller):
    from philosophical_council.core.constants import VALID_SPEAKERS
    session = controller._factory.build(_config(template_id="scientist-skeptic", max_turns=1))
    state = session.engine.argument_state
    assert state.known_speakers == {"Scientist", "Skeptic"}
    alts = state.get_alternatives(exclude=None)
    assert set(alts) <= {"Scientist", "Skeptic"}
    # "Skeptic" legitimately overlaps by name with a philosophical school; the
    # meaningful check is that no OTHER philosopher leaks into alternatives.
    assert not (set(alts) & (set(VALID_SPEAKERS) - {"Skeptic"}))


# ── 12. Exact per-role configured model is honored ─────────────────────────
def test_12_role_model_honored(controller, stub):
    cfg = _config(template_id="scientist-skeptic", max_turns=3,
                  role_models={"scientist": "model-b"})
    view, run = _run(controller, stub, cfg)
    sci = [e for e in run["result"]["participant_inferences"] if e["role"] == "scientist"]
    assert sci, "scientist should have participated"
    for e in sci:
        assert e["configured_model"] == "model-b"
        assert e["actual_model"] == "model-b"
        assert e["selection_mode"] == "configured"


# ── 13. Actual model used is recorded ──────────────────────────────────────
def test_13_actual_model_recorded(controller, stub):
    cfg = _config(template_id="scientist-skeptic", max_turns=2, model_pool=POOL)
    view, run = _run(controller, stub, cfg)
    for e in run["result"]["participant_inferences"]:
        assert e.get("actual_model"), e
        assert e.get("selection_mode") in ("configured", "dynamic_router", "backend_default")
    for e in run["result"]["moderator_inferences"]:
        assert e.get("actual_model"), e
        assert e.get("selection_mode") in ("configured", "dynamic_router", "backend_default")
        assert e.get("parse_mode")


# ── 14. Blank per-role model uses ONLY models from the configured pool ─────
def test_14_blank_role_model_uses_pool_only(controller, stub):
    cfg = _config(template_id="scientist-skeptic", max_turns=3, model_pool=POOL,
                  role_models={})  # all blank → dynamic routing
    view, run = _run(controller, stub, cfg)
    for e in run["result"]["participant_inferences"]:
        assert e["actual_model"] in POOL, e
        assert e["selection_mode"] == "dynamic_router"


# ── 15. Model routing method in the UI is actually honored ─────────────────
def test_15_routing_method_honored(controller, stub):
    from philosophical_council.core.router import ModelRouter
    cfg = _config(template_id="scientist-skeptic", max_turns=2,
                  model_pool=POOL, model_routing_method="round_robin")
    view, run = _run(controller, stub, cfg)
    assert run["result"]["provenance"]["model_routing_method"] == "round_robin"
    start_ev = next(e for e in run["events"] if e["type"] == "RUN_STARTED")
    assert start_ev["model_routing_method"] == "round_robin"
    # the router actually had the method set
    router = stub._router
    assert router is not None
    assert router._method == "round_robin"
    # UI select lists exactly the real methods
    html = (REPO_ROOT / "experiments" / "ui" / "dashboard.html").read_text(encoding="utf-8")
    for m in ("context_aware", "round_robin", "weighted", "random"):
        assert f'value="{m}"' in html


# ── 16. No fake "llm" model-routing mode falls through to round-robin ──────
def test_16_no_fake_llm_routing():
    from debate_lab.config import DebateLabConfig, DebateLabConfigError, REAL_MODEL_ROUTING_METHODS
    assert "llm" not in REAL_MODEL_ROUTING_METHODS
    with pytest.raises(DebateLabConfigError):
        DebateLabConfig(topic="x", model_routing_method="llm")
    # the UI's routing select must not offer "llm"
    html = (REPO_ROOT / "experiments" / "ui" / "dashboard.html").read_text(encoding="utf-8")
    routing_block = html.split('id="dl-routing"')[1].split("</select>")[0]
    assert "value=\"llm\"" not in routing_block


# ── 17. Code Lab rejects a Debate template before engine construction ──────
def test_17_code_lab_rejects_debate_template():
    from role_templates.executor import require_code_lab
    for tid in ("scientist-skeptic", "philosophical-debate"):
        with pytest.raises(ValueError) as ei:
            require_code_lab(tid)
        assert "Code Lab cannot run it" in str(ei.value)


# ── 18. Debate Lab rejects a Code Lab template before engine construction ──
def test_18_debate_lab_rejects_code_lab_template(controller):
    from debate_lab.config import DebateLabConfig
    from debate_lab.validation import TemplateInvalidForDebate
    from role_templates.executor import require_debate
    with pytest.raises(ValueError):
        require_debate("coding-standard")
    with pytest.raises(TemplateInvalidForDebate):
        controller.create_run(_config(template_id="coding-standard", max_turns=2))


# ── 19. max_turns=5 produces no more than 5 committed turns ────────────────
def test_19_max_turns_budget(controller, stub):
    cfg = _config(template_id="scientist-skeptic", max_turns=5, model_pool=POOL)
    view, run = _run(controller, stub, cfg)
    assert run["result"]["turns_committed"] == 5
    assert len(run["result"]["transcript"]) == 5


# ── 20. config accepts max_turns=1000 ──────────────────────────────────────
def test_20_max_turns_1000_accepted():
    from debate_lab.config import DebateLabConfig
    cfg = DebateLabConfig(topic="t", max_turns=1000)
    assert cfg.max_turns == 1000
    # no hidden AutoPilot constant leaks into Debate Lab config
    assert cfg.max_turns != 5


# ── 21. Stop prevents any NEW LLM call after stop is observed ──────────────
def test_21_stop_blocks_new_calls(tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    # Cycling speakers → no repetition retries → exactly one moderator call and
    # one participant call per step (so the in-flight-step bound is +2, exact).
    slow = StubLLM(models=POOL, chat_delay=0.03, speaker_cycle=["Scientist", "Skeptic"])
    factory = DebateSessionFactory(llm_client=slow, base_dir=tmp_path)
    ctrl = DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))
    cfg = _config(template_id="scientist-skeptic", max_turns=1000)
    view = ctrl.create_run(cfg)
    assert ctrl.start_run(view.run_id)
    # wait until at least one turn committed
    deadline = time.time() + 30
    while time.time() < deadline:
        r = ctrl.get_run(view.run_id)
        if any(e["type"] == "TURN_COMMITTED" for e in r["events"]):
            break
        time.sleep(0.05)
    calls_at_stop = slow.call_count
    assert ctrl.stop_run(view.run_id)
    r = _wait_terminal(ctrl, view.run_id)
    # after stop is observed the worker schedules no NEW turn. The only calls
    # that may still complete are the moderator+participant pair of the single
    # step_once that was already in flight when stop was requested.
    assert slow.call_count <= calls_at_stop + 2, slow.call_count
    assert r["status"] == "stopped"
    assert r["result"]["execution_status"] == "STOPPED"
    types = [e["type"] for e in r["events"]]
    stop_idx = types.index("STOP_REQUESTED")
    assert "STOP_REQUESTED" in types
    # nothing after STOP_REQUESTED starts a new moderator/agent/turn
    for after in types[stop_idx + 1:]:
        assert after not in ("MODERATOR_STARTED", "AGENT_STARTED", "TURN_COMMITTED",
                             "MEMORY_CONSOLIDATION_STARTED"), after
    assert r["result"]["turns_committed"] < 1000


# ── 22. Delete does not leave a worker running ─────────────────────────────
def test_22_delete_stops_worker(tmp_path, monkeypatch):
    import debate_lab.controller as ctrl_mod
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    monkeypatch.setattr(ctrl_mod, "DELETE_JOIN_TIMEOUT", 1.0)
    slow = StubLLM(models=POOL, chat_delay=0.02)
    factory = DebateSessionFactory(llm_client=slow, base_dir=tmp_path)
    ctrl = DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))
    cfg = _config(template_id="scientist-skeptic", max_turns=1000)
    view = ctrl.create_run(cfg)
    assert ctrl.start_run(view.run_id)
    deadline = time.time() + 30
    while time.time() < deadline:
        r = ctrl.get_run(view.run_id)
        if any(e["type"] == "TURN_COMMITTED" for e in r["events"]):
            break
        time.sleep(0.05)
    assert ctrl.delete_run(view.run_id), "delete should stop + join the worker"
    assert ctrl.get_run(view.run_id) is None
    thread = ctrl._threads.get(view.run_id)
    assert thread is None or not thread.is_alive()


# ── 22b. Delete is BLOCKED while a worker cannot terminate ─────────────────
def test_22b_delete_blocked_active_run(tmp_path, monkeypatch):
    import debate_lab.controller as ctrl_mod
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    monkeypatch.setattr(ctrl_mod, "DELETE_JOIN_TIMEOUT", 0.5)
    blocking = BlockingLLM(models=POOL)
    factory = DebateSessionFactory(llm_client=blocking, base_dir=tmp_path)
    ctrl = DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))
    cfg = _config(template_id="scientist-skeptic", max_turns=1000)
    view = ctrl.create_run(cfg)
    assert ctrl.start_run(view.run_id)
    time.sleep(0.3)  # worker inside the blocking call
    assert ctrl.delete_run(view.run_id) is False
    assert ctrl.get_run(view.run_id) is not None  # still registered
    # (the worker is stuck inside the blocking call; it is a daemon thread and
    # dies with the test process — no cleanup needed, and no leak persists
    # into the rest of the suite since every test builds its own controller)


# ── 23. Moderator configured/actual model provenance is visible ────────────
def test_23_moderator_provenance(controller, stub):
    cfg = _config(template_id="philosophical-debate", max_turns=3,
                  model_pool=POOL, role_models={"moderator": "model-c"})
    view, run = _run(controller, stub, cfg)
    for e in run["result"]["moderator_inferences"]:
        assert e["configured_model"] == "model-c"
        assert e["actual_model"] == "model-c"
        assert e["selection_mode"] == "configured"
        assert e.get("parse_mode")
    # TurnEvent provenance rides on every committed turn too
    assert run["result"]["provenance"]["configured_role_models"].get("moderator") == "model-c"


# ── 24. Participant configured/actual model provenance is visible ──────────
def test_24_participant_provenance(controller, stub):
    cfg = _config(template_id="scientist-skeptic", max_turns=2,
                  role_models={"skeptic": "model-a"})
    view, run = _run(controller, stub, cfg)
    for e in run["result"]["participant_inferences"]:
        assert "actual_model" in e
        assert "configured_model" in e
        assert "selection_mode" in e


# ── 25. Settings reports CONNECTED from the SAME capability source ─────────
def test_25_settings_single_source_of_truth():
    from role_templates.executor import _executor_connected
    from experiments import settings as S
    rt = S.get_settings()["role_templates"]
    # Settings reads the SAME authoritative capability source as dispatch
    assert rt["philosophical_debate"]["status"] == "EXECUTABLE"
    assert rt["philosophical_debate"]["executable"] is True
    assert _executor_connected("philosophical_debate") is True
    assert _executor_connected("debate") is True
    assert _executor_connected("code_lab") is True
    assert _executor_connected("general_reasoning") is False
    # no contradictory flags anywhere in settings
    src = Path(S.__file__).read_text(encoding="utf-8")
    assert "_EXECUTABLE_EXECUTORS" not in src
    assert "_DEBATE_CONNECTED" not in src


# ── 26/27/28. Existing AutoPilot / Code Lab / memory tests stay green ──────
def test_26_autopilot_debate_still_works():
    """AutoPilot's own DebateEngine path is untouched (no duplicate core)."""
    import philosophical_council.core.debate_engine as de
    # the engine module still exposes the same public entry point AutoPilot uses
    assert hasattr(de, "DebateEngine")
    # historical DebateConfig still builds with the new max_continuations field
    from philosophical_council.config import DebateConfig
    dc = DebateConfig()
    assert dc.max_continuations == 2


def test_27_code_lab_capabilities_intact():
    from role_templates.executor import EXECUTOR_CAPABILITIES
    cap = EXECUTOR_CAPABILITIES["code_lab"]
    assert cap["connected"] is True
    assert cap["engine"] == "CodeLabEngine"


def test_28_memory_consolidation_runs(controller, stub):
    """Memory consolidation is observable and functional during a debate run."""
    cfg = _config(template_id="scientist-skeptic", max_turns=4,
                  mid_term_interval=2, long_term_interval=4)
    view, run = _run(controller, stub, cfg)
    types = [e["type"] for e in run["events"]]
    assert "MEMORY_CONSOLIDATION_STARTED" in types
    assert "MEMORY_CONSOLIDATION_COMPLETED" in types


# ── API-level: create/start/stop/delete/list/templates/timeline ────────────
def test_api_full_lifecycle(controller, stub):
    from debate_lab.config import DebateLabConfig
    cfg = _config(template_id="scientist-skeptic", max_turns=2, model_pool=POOL)
    view = controller.create_run(cfg)
    assert controller.list_runs()[0]["status"] == "pending"
    assert controller.start_run(view.run_id, wait=True)
    assert controller.get_run(view.run_id)["status"] == "completed"
    assert controller.get_timeline()["count"] >= 5
    assert controller.delete_run(view.run_id)
    assert not any(r["run_id"] == view.run_id for r in controller.list_runs())


def test_api_templates_endpoint_dashboard():
    """The dashboard serves only Debate-compatible templates under /api/debate/templates."""
    from experiments.dashboard import DashboardHandler
    from role_templates.registry import get_registry
    from debate_lab.validation import template_summary
    reg = get_registry()
    ids = [t.template_id for t in reg._latest.values()
           if (t.executor_type or "") in ("debate", "philosophical_debate")]
    assert "philosophical-debate" in ids
    assert "scientist-skeptic" in ids
    assert "coding-standard" not in ids
    s = template_summary(reg.get_template("scientist-skeptic"))
    assert [r["role_id"] for r in s["roles"]] == ["moderator", "scientist", "skeptic"]


# ── HTTP-level: create/start/stop/delete through the REAL dashboard API ────
def test_http_debate_api_full_flow(tmp_path):
    """A Debate run is created DIRECTLY through the Debate HTTP API (spec §37 #2)."""
    import json
    import threading
    import urllib.parse
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer

    from experiments.dashboard import DashboardHandler
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory

    stub = StubLLM(models=POOL, speaker_cycle=["Scientist", "Skeptic"])
    factory = DebateSessionFactory(llm_client=stub, base_dir=tmp_path)
    ctrl = DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))
    DashboardHandler.debate_lab_controller = ctrl

    srv = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        csrf_cookie, csrf_token = "", ""
        try:
            import re as _re
            _r = urllib.request.Request(base + "/dashboard")
            with urllib.request.urlopen(_r, timeout=15) as _resp:
                _sc = _resp.headers.get("Set-Cookie", "")
            _m = _re.search(r"lifemean_csrf=([^;]+)", _sc)
            if _m:
                csrf_cookie = "lifemean_csrf=" + _m.group(1)
                csrf_token = urllib.parse.unquote(_m.group(1))
        except Exception:
            pass

        def req(path, method="GET", body=None):
            data = json.dumps(body).encode() if body is not None else None
            r = urllib.request.Request(base + path, data=data, method=method)
            if data is not None:
                r.add_header("Content-Type", "application/json")
            if method in ("POST", "PUT", "DELETE"):
                if csrf_cookie:
                    r.add_header("Cookie", csrf_cookie)
                if csrf_token:
                    r.add_header("X-Lifemean-CSRF", csrf_token)
            try:
                with urllib.request.urlopen(r, timeout=30) as resp:
                    return resp.status, json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode() or "{}")

        # templates endpoint serves ONLY debate-compatible templates
        st, body = req("/api/debate/templates")
        assert st == 200
        assert {"philosophical-debate", "scientist-skeptic"} <= {x["template_id"] for x in body["templates"]}

        # create directly through the Debate API (no AutoPilot)
        st, body = req("/api/debate/runs", method="POST", body={
            "topic": "Should scientific discovery optimize novelty or reproducibility first?",
            "template_id": "scientist-skeptic",
            "max_turns": 2,
            "model_pool": POOL,
        })
        assert st == 200, body
        run_id = body["run_id"]
        assert body["started"] is False  # created -> user clicks START

        st, body = req(f"/api/debate/runs/{run_id}/start", method="POST")
        assert st == 200, body

        # poll to completion
        deadline = time.time() + 30
        status = None
        while time.time() < deadline:
            st, body = req(f"/api/debate/runs/{run_id}")
            assert st == 200
            status = body["status"]
            if status in ("completed", "stopped", "failed"):
                break
            time.sleep(0.05)
        assert status == "completed", body
        assert body["result"]["turns_committed"] == 2

        # timeline reflects backend events
        st, tl = req("/api/debate/timeline")
        assert st == 200 and tl["count"] >= 5

        # delete (safe: worker already terminal)
        st, body = req(f"/api/debate/runs/{run_id}", method="DELETE")
        assert st == 200, body
    finally:
        srv.shutdown()
        srv.server_close()
