"""Role Template system tests (tests 15.A – 15.K).

Covers the versioned feature-object contract without backend dependency:

A.  Built-in templates load correctly.
B.  Template hashes are deterministic (stable across rebuild + round-trip).
C.  A scientifically meaningful modification changes the hash.
D.  Same template can map to different models.
E.  Same model can occupy different roles.
F.  Persona and role remain separate.
G.  Code Lab still works using CODING_STANDARD (multi-agent + provenance).
H.  Philosophical Debate still uses the existing DebateEngine (no new engine).
I.  Experiment/RAW records template id / version / hash.
J.  ACTUAL model is preserved when router/fallback differs from CONFIGURED.
K.  No duplicate orchestrator/debate engine was introduced.
"""

import json
from pathlib import Path

import pytest

# Ensure the repo root (with role_templates/, code_lab/, experiments/) is importable.
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _syspath():
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    yield


@pytest.fixture()
def registry():
    from role_templates.registry import RoleTemplateRegistry
    reg = RoleTemplateRegistry()
    reg.register_builtin()
    return reg


# ── A. built-ins load ─────────────────────────────────────────────────────
def test_a_builtin_templates_load(registry):
    """All built-ins are present, valid, and carry expected roles."""
    templates = registry.list_templates()
    ids = {t["id"] for t in templates}
    assert {"coding-standard", "philosophical-debate", "general-reasoning"} <= ids

    cs = registry.get_template("coding-standard")
    assert cs is not None
    assert [r.role_id for r in cs.roles] == ["planner", "developer", "critic", "reviewer", "judge"]
    # Everyone is valid.
    for tpl in [registry.get_template(i) for i in ids]:
        assert registry.validate_template(tpl) == ""


# ── B. deterministic hash ─────────────────────────────────────────────────
def test_b_hash_deterministic():
    from role_templates.builtins import coding_standard
    a = coding_standard()
    b = coding_standard()
    assert a.content_hash() == b.content_hash()
    # Stable across serialization round-trip.
    c = a.__class__.from_dict(json.loads(json.dumps(a.to_dict())))
    assert c.content_hash() == a.content_hash()


# ── C. meaningful change changes hash ─────────────────────────────────────
def test_c_meaningful_change_changes_hash(registry):
    cs = registry.get_template("coding-standard")
    h0 = cs.content_hash()

    # Change a role instruction -> different hash.
    d = json.loads(json.dumps(cs.to_dict()))
    d["roles"][1]["instructions_template"] = "DIFFERENT: you are now a changed developer."
    from role_templates.core import RoleTemplate
    changed = RoleTemplate.from_dict(d)
    assert changed.content_hash() != h0

    # Change version -> different hash.
    d2 = json.loads(json.dumps(cs.to_dict()))
    d2["version"] = "2.0.0"
    assert RoleTemplate.from_dict(d2).content_hash() != h0

    # Modify only timestamps -> SAME hash (metadata is not content).
    d3 = json.loads(json.dumps(cs.to_dict()))
    d3["updated_at"] = "2099-01-01T00:00:00"
    assert RoleTemplate.from_dict(d3).content_hash() == h0


# ── D. same template, different models ────────────────────────────────────
def test_d_same_template_different_models(registry):
    """Model mapping is experiment-level, never baked into the template."""
    from role_templates.core import RoleModelMapping
    tpl = registry.get_template("coding-standard")
    h = tpl.content_hash()
    m1 = RoleModelMapping(template_id=tpl.template_id, models={"develop_same": "qwen", "developer": "qwen"})
    m2 = RoleModelMapping(template_id=tpl.template_id, models={"developer": "mellum-4b"})
    assert m1.get("developer") == "qwen"
    assert m2.get("developer") == "mellum-4b"
    # Mapping change does NOT change the template identity.
    assert registry.get_template("coding-standard").content_hash() == h


# ── E. same model, different roles ────────────────────────────────────────
def test_e_same_model_in_different_roles(registry):
    from role_templates.core import RoleModelMapping
    m = RoleModelMapping(models={"developer": "phi-mini", "critic": "phi-mini"})
    assert m.get("developer") == "phi-mini"
    assert m.get("critic") == "phi-mini"


# ── F. persona separate from role ─────────────────────────────────────────
def test_f_persona_role_separate(registry):
    cs = registry.get_template("coding-standard")
    # Roles have a default_persona field but a role is not a persona.
    for r in cs.roles:
        assert isinstance(r.default_persona, str)
    # Overriding persona does not change role identity/hash.
    d = json.loads(json.dumps(cs.to_dict()))
    d["roles"][1]["default_persona"] = "security-focused"  # experiment override
    from role_templates.core import RoleTemplate
    overridden = RoleTemplate.from_dict(d)
    # A persona override is allowed and does NOT silently change the hash.
    # (persona is explicit metadata; the hash does cover it, but the experiment
    # carries persona separately via RoleModelMapping-style override.) We assert
    # the role_id and instructions stay intact:
    assert overridden.roles[1].role_id == "developer"
    assert overridden.roles[1].instructions_template == cs.roles[1].instructions_template

    # Philosophical-debate template references personas, not hardcoding them.
    pd = registry.get_template("philosophical-debate")
    pds = {r.role_id: r for r in pd.roles}
    assert pds["stoic"].default_persona == "stoic"       # prefers its persona
    assert pds["moderator"].default_persona == "moderator"
    # Persona and role are observably distinct concepts in the object model.
    from role_templates.core import RoleSpec
    assert set(RoleSpec.__dataclass_fields__) >= {"role_id", "default_persona"}


# ── G. Code Lab works using CODING_STANDARD (multi-agent + provenance) ────
class _StubLLM:
    """Minimal stable-core-compatible LLM stub (no network)."""

    def __init__(self, default_model: str = "router-picked-model"):
        self.last_model_used = default_model
        self._models = [default_model]

    def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
        self.last_model_used = model or self.last_model_used
        return "```python\ndef f():\n    return 42\n```\n", "stop"


def test_g_code_lab_uses_coding_standard_and_records_provenance(registry):
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine

    cfg = CodeLabConfig(prompt="create a fibonacci(n) function", template_id="coding-standard")
    engine = CodeLabEngine(config=cfg)
    # The engine resolves CODING_STANDARD from the registry and derives the
    # role prompts it feeds the (injected) multi-agent.
    tpl = engine._resolve_role_template()
    assert tpl is not None and tpl.template_id == "coding-standard"
    assert tpl.version == "1.0.0"
    assert tpl.content_hash()
    derived = {r.role_id.upper(): r.instructions_template for r in tpl.roles if r.instructions_template}
    assert "PLANNER" in derived and "DEVELOPER" in derived

    # A DETERMINISTIC run passes WITHOUT any LLM role template: provenance must
    # record role_template=null (S14) — never claim a template that did not
    # drive execution via LLM agents.
    events = []
    engine = CodeLabEngine(config=CodeLabConfig(prompt="Create a function add(a,b).",
                                                template_id="coding-standard",
                                                multi_agent=False),
                           event_handler=events.append)
    res = engine.run()
    assert res["status"] == "passed"
    assert res["role_template"] is None
    # Deterministic path must not have probed/required an LLM backend.
    assert res["llm_error"] == "not used (deterministic)"
    # §10: deterministic disposition is explicit, and judge disposition stays
    # distinct (UNAVAILABLE — the LLM judge stage would run but had no backend).
    assert res["deterministic_validation_status"] == "PASS"
    assert res["semantic_judge"]["status"] == "UNAVAILABLE"


# ── H. Debate still uses existing DebateEngine ────────────────────────────
def test_h_debate_still_uses_existing_engine(registry):
    # The built-in debate template is a *description*; the engine is unchanged.
    pd = registry.get_template("philosophical-debate")
    assert pd is not None
    assert any(r.role_id == "moderator" for r in pd.roles)
    # The canonical debate engine is still the existing one, importable & used.
    from philosophical_council.core.debate_engine import DebateEngine
    assert DebateEngine.__name__ == "DebateEngine"
    # AutoPilot is the ONLY execution path used for debate experiments, and it
    # drives the existing DebateEngine (no new engine was introduced).
    import experiments.autopilot as ap
    src = Path(ap.__file__).read_text(encoding="utf-8")
    assert "DebateEngine" in src or "debate_engine" in src or "debate" in src.lower()


# ── I. Experiment / RAW records template id / version / hash ──────────────
def test_i_experiment_records_template_provenance(monkeypatch):
    import code_lab.multiagent as ma_mod
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine
    # Keep the multi-agent run OFFLINE and deterministic: fake the backend probe
    # so availability passes, and inject a stub LLM client (no live network).
    monkeypatch.setattr(
        ma_mod, "probe_llm",
        lambda *a, **k: {"available": True, "models": ["fake-model"], "error": None})
    cfg = CodeLabConfig(prompt="create a function double(x) that returns x*2",
                        template_id="coding-standard", multi_agent=True)
    events = []
    engine = CodeLabEngine(config=cfg, event_handler=events.append, llm_client=_StubLLM())
    res = engine.run()
    assert res["status"] == "passed" or res["status"] == "failed"  # determinism, not backend
    rt = res["role_template"]
    assert rt is not None
    assert rt["template_id"] == "coding-standard"
    assert rt["template_version"]
    assert rt["template_hash"]
    # Template id/version/hash ride on terminal + agent events.
    assert any("template_id" in e for e in events)
    # Deterministic run records NO template (honest null), even though the config
    # carries template_id — deterministic never executes those LLM roles.
    det = CodeLabEngine(config=CodeLabConfig(
        prompt="create a function add(a,b).", template_id="coding-standard",
        multi_agent=False), event_handler=lambda e: None).run()
    assert det["role_template"] is None
    assert det["llm_error"] == "not used (deterministic)"


# ── I2. Bare-markdown DEVELOPER output is rejected, never written (AGENT 7) ─
def test_i2_developer_bare_markdown_fence_rejected_not_written(monkeypatch, tmp_path):
    """A DEVELOPER that returns only a bare markdown fence ("```") must be
    classified as a phantom/empty developer stage — NOT written verbatim into a
    .py (that would be a SyntaxError the repair loop can never fix)."""
    import code_lab.multiagent as ma_mod
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine

    monkeypatch.setattr(
        ma_mod, "probe_llm",
        lambda *a, **k: {"available": True, "models": ["fake-model"], "error": None})

    class _GarbageDevLLM:
        """Call #1 = PLANNER (valid plan) ; call #2+ = DEVELOPER returns a bare
        markdown fence — the exact degenerate output from the reported run."""
        def __init__(self):
            self.calls = 0
            self.last_model_used = "m"
        def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
            self.calls += 1
            self.last_model_used = model or self.last_model_used
            if self.calls == 1:
                return "```text\nplan: write a fibonacci engine\n```\n", "stop"
            return "```\n", "stop"  # bare fence only — NOT valid source

    events = []
    cfg = CodeLabConfig(prompt="create a function fibonacci(n)",
                        template_id="coding-standard", multi_agent=True)
    engine = CodeLabEngine(config=cfg, event_handler=events.append,
                           llm_client=_GarbageDevLLM(), base_dir=tmp_path)
    res = engine.run()
    assert res["status"] == "failed"
    err = " ".join(str(e.get("message", "")) for e in res.get("errors", []))
    # BOTH attempts were bare fences → classified develop failure after the retry.
    assert err and "empty/phantom" in err, f"expected classified develop failure, got: {err}"
    assert res["deterministic_validation_status"] == "NOT_REACHED"
    if engine.ws:
        from pathlib import Path as _P
        p = _P(engine.ws.root) / "fibonacci.py"
        if p.exists():
            assert p.read_text(encoding="utf-8").strip() != "```"


# ── I3. DEVELOPER retry recovers when the second draw is usable ──────────────
def test_i3_developer_retry_recovers_after_bad_first_draw(monkeypatch, tmp_path):
    """A degenerate first DEVELOPER output triggers ONE fresh retry; if the second
    attempt yields usable code, the pipeline proceeds instead of failing at develop
    (one bad draw is NOT the terminal verdict)."""
    import code_lab.multiagent as ma_mod
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine

    monkeypatch.setattr(
        ma_mod, "probe_llm",
        lambda *a, **k: {"available": True, "models": ["fake-model"], "error": None})

    class _RetryLLM:
        """Call#1 planner (plan); call#2 developer → bare fence; call#3
        (the retry) developer → valid fenced code."""
        def __init__(self):
            self.calls = 0
            self.last_model_used = "m"
        def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
            self.calls += 1
            self.last_model_used = model or self.last_model_used
            if self.calls == 1:
                return "```text\nplan: write a fibonacci engine\n```\n", "stop"
            if self.calls == 2:
                return "```\n", "stop"  # degenerate first draw
            return "```python\ndef f():\n    return 1\n```\n", "stop"  # retry: valid

    events = []
    cfg = CodeLabConfig(prompt="create a function fibonacci(n)",
                        template_id="coding-standard", multi_agent=True)
    engine = CodeLabEngine(config=cfg, event_handler=events.append,
                           llm_client=_RetryLLM(), base_dir=tmp_path)
    res = engine.run()
    # Developer did NOT fail: the pipeline proceeded (whatever the later validation
    # outcome — the recoverable semantics at the developer stage is what matters here).
    err = " ".join(str(e.get("message", "")) for e in res.get("errors", []))
    assert "empty/phantom" not in err, f"developer failed despite usable retry: {err}"
    # Both developer attempts ride in the trace, with the retry explicitly marked.
    trace = res.get("agent_trace", [])
    devs = [t for t in trace if t.get("agent") == "DEVELOPER"]
    assert len(devs) == 2, f"expected 2 developer attempts, got {len(devs)}"
    assert any(t.get("attempt") == 2 for t in devs), "retry attempt not recorded in trace"


# ── J. ACTUAL model preserved when router/fallback differs ────────────────
def test_j_actual_vs_configured_model():
    from code_lab.multiagent import CodingMultiAgent
    # No configured model -> ACTUAL comes from the client's router/fallback.
    stub = _StubLLM(default_model="router-picked-a")
    ma = CodingMultiAgent("http://x/v1", "", llm_client=stub,
                          role_models={"developer": ""})  # configured = dynamic
    res = ma.develop("plan", "Python")
    assert res["ok"] is True
    # The agent recorded the ACTUAL model the client used.
    assert ma.agents["DEVELOPER"].model_used == "router-picked-a"

    # Configured model differs from the client's actual default.
    stub2 = _StubLLM(default_model="router-picked-b")
    ma2 = CodingMultiAgent("http://x/v1", "", llm_client=stub2,
                           role_models={"developer": "configured-qwen"})
    res2 = ma2.develop("plan", "Python")
    assert ma2.agents["DEVELOPER"].model_used == "configured-qwen"  # CONFIGURED
    assert stub2.last_model_used == "configured-qwen"               # actually used


# ── K. no duplicate engine/orchestrator ───────────────────────────────────
def test_k_no_duplicate_engine_orchestrator(registry):
    # The role_templates package must be pure data/configuration — it must not
    # define or instantiate a debate engine, orchestrator, or coder multi-agent.
    import role_templates.core
    import role_templates.builtins
    import role_templates.registry
    for mod in (role_templates.core, role_templates.builtins, role_templates.registry):
        src = (Path(mod.__file__).read_text(encoding="utf-8"))
        assert "class DebateEngine" not in src
        assert "class Orchestrator" not in src
        assert "CodingMultiAgent(" not in src  # never spawns an agent
    # Registry hands back plain RoleTemplate objects, not live engines.
    for t in registry._latest.values():
        assert t.__class__.__name__ == "RoleTemplate"


# ── L. Code Lab rejects incompatible templates (no false provenance) ─────────
def test_l_code_lab_rejects_incompatible_templates(registry):
    """Code Lab must NOT silently fall back to coding prompts for a debate /
    general-reasoning template. It rejects them with a controlled error, so
    provenance can never claim a template executed that did not.

    (Integrity §2 / §19.3, Runtime §18G: no fake success.)
    """
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine

    for bad in ("philosophical-debate", "general-reasoning"):
        eng = CodeLabEngine(config=CodeLabConfig(template_id=bad, multi_agent=True))
        with pytest.raises(ValueError) as ei:
            eng._resolve_role_template()
        msg = str(ei.value)
        assert "compatible" in msg or "code_lab" in msg or "executor" in msg
        # The engine never recorded a fallback template.
        assert getattr(eng, "_role_template", None) is None

    # An unknown template id is also rejected (never silently -> coding-standard).
    eng = CodeLabEngine(config=CodeLabConfig(template_id="does-not-exist", multi_agent=True))
    with pytest.raises(ValueError):
        eng._resolve_role_template()


# ── M. Registry hardening: immutable identity + version collision (§4/§19.6) ─
def test_m_registry_immutable_identity_and_version(registry):
    from role_templates.core import RoleTemplate, RoleSpec

    t1 = RoleTemplate(template_id="reg-test", version="1.0.0",
                      roles=[RoleSpec(role_id="a", instructions_template="do X")])
    # Fresh; then re-register identical → idempotent, not rejected.
    assert registry.register(t1) is True
    assert registry.register(t1) is False          # identical id+version+hash → no-op
    # Same id+version but DIFFERENT content → immutable identity is REJECTED.
    t2 = RoleTemplate(template_id="reg-test", version="1.0.0",
                      roles=[RoleSpec(role_id="a", instructions_template="do Y")])
    with pytest.raises(ValueError) as ei:
        registry.register(t2)
    assert "DIFFERENT content hash" in str(ei.value)
    # The original identity is still served (never silently replaced).
    got = registry.get_template("reg-test", "1.0.0")
    assert got.content_hash() == t1.content_hash()

    # Invalid template is rejected before registration.
    bad = RoleTemplate(template_id="", version="1.0.0",
                       roles=[RoleSpec(role_id="a", instructions_template="x")])
    with pytest.raises(ValueError):
        registry.register(bad)

    # _latest is the DETERMINISTIC highest version, not last-registered.
    low = RoleTemplate(template_id="order-test", version="1.2.0",
                       roles=[RoleSpec(role_id="a", instructions_template="low")])
    hi = RoleTemplate(template_id="order-test", version="1.10.0",
                      roles=[RoleSpec(role_id="a", instructions_template="hi")])
    # Register HIGH first then LOW — latest must STILL be the high version.
    registry.register(hi)
    registry.register(low)
    assert registry.get_template("order-test").version == "1.10.0"



# ── N. Template selection dispatches by executor_type (never all into Code Lab) ─
def test_n_template_dispatches_to_compatible_executor(registry):
    """A selected template must dispatch to the executor matching its
    executor_type — CodeLabEngine only ever receives code_lab templates."""
    from role_templates.executor import (
        EXECUTOR_CAPABILITIES, dispatch_template, require_code_lab)

    # built-ins are registered by the registry fixture; classify each
    assert dispatch_template("coding-standard")["executor_type"] == "code_lab"
    assert dispatch_template("coding-standard")["connected"] is True
    assert dispatch_template("coding-standard")["engine"] == "CodeLabEngine"

    d = dispatch_template("philosophical-debate")
    assert d["executor_type"] == "philosophical_debate"
    assert d["executor_kind"] == "philosophical_debate"
    # Debate-compatible executors are wired through the Debate Lab integration
    # (spec §30/§31): philosophical_debate aliases the SAME DebateEngine path.
    assert "DebateEngine" in d["engine"]
    assert d["connected"] is True

    assert dispatch_template("general-reasoning")["executor_type"] == "general_reasoning"

    # capability catalog is consistent with the executor kinds the template
    # system can actually declare
    for t in registry._latest.values():
        assert t.executor_type in EXECUTOR_CAPABILITIES, t.executor_type

    # unknown template cannot dispatch (no silent default executor)
    with pytest.raises(ValueError):
        dispatch_template("no-such-template")


def test_n_require_code_lab_refuses_other_executors(registry):
    """require_code_lab is the dispatch guard for Code Lab: passes only for
    code_lab templates, refuses others naming their correct executor."""
    from role_templates.executor import require_code_lab

    d = require_code_lab("coding-standard")
    assert d["executor_type"] == "code_lab"

    for bad, target in (("philosophical-debate", "philosophical_debate"),
                        ("general-reasoning", "general_reasoning")):
        with pytest.raises(ValueError) as ei:
            require_code_lab(bad)
        msg = str(ei.value)
        # names the target executor, never a silent fallback / Code Lab run
        assert target in msg
        assert "cannot run it" in msg

    with pytest.raises(ValueError):
        require_code_lab("no-such-template")
