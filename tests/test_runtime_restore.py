"""Runtime Restore pass tests (Life_mean RUNTIME_RESTORE).

Proves the product journey works truthfully:
  A. Credential precedence survives "restart" (fresh process reads the Settings
     override, not the stale legacy .env; explicit process env still wins).
  B. Deterministic Code Lab runs with a backend / NO LLM dependency (S7/S8).
  C. Settings-owned Role Template defaults round-trip and validate (S10/18).
  D. Code Lab resolves its template from the Settings default (S18C).
  E. Honest backend diagnostic: a 401 is classified, then "fix" (200) lists models,
     without ever exposing the token (S6/S17).
No live backend or network is required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _syspath():
    import sys as _s
    if str(REPO_ROOT) not in _s.path:
        _s.path.insert(0, str(REPO_ROOT))
    yield


def _write(tmp: Path, rel: str, content: str) -> Path:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── A. Credential precedence across a fresh process (fake restart) ─────────
def test_a_credential_precedence_survives_restart(tmp_path):
    py = sys.executable
    probe = (
        "import code_lab.config\n"
        "from experiments.credentials import resolve_llm_credentials as r\n"
        "print(r()[1])"
    )
    # 1) Settings override must beat a legacy .env in a FRESH process.
    _write(tmp_path, "overrides/llm.env",
           "LIFE_MEAN_LLM_BASE_URL=http://localhost:1234/v1\n"
           "LIFE_MEAN_LLM_API_KEY=settings-saved-token\n")
    _write(tmp_path, ".env", "LIFE_MEAN_LLM_API_KEY=stale-dotenv-token\n")
    env = {k: v for k, v in os.environ.items()
           if k not in ("LIFE_MEAN_LLM_API_KEY", "LIFE_MEAN_LLM_BASE_URL")}
    env["LIFE_MEAN_OVERRIDES_FILE"] = str(tmp_path / "overrides" / "llm.env")
    out = subprocess.run([py, "-c", probe], capture_output=True, text=True,
                         cwd=str(tmp_path), env=env, timeout=60)
    assert "settings-saved-token" in out.stdout
    assert "stale-dotenv-token" not in out.stdout

    # 2) An explicitly-set process env still wins (precedence 1) in a fresh proc.
    env["LIFE_MEAN_LLM_API_KEY"] = "explicit-shell-token"
    out2 = subprocess.run([py, "-c", probe], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=60)
    assert "explicit-shell-token" in out2.stdout


# ── B. Deterministic Code Lab runs with NO backend / LLM dependency ─────────
def test_b_deterministic_run_needs_no_backend():
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine
    # Unreachable backend; deterministic MUST NOT probe it (S7/S8).
    cfg = CodeLabConfig(prompt="create a function add(a,b) returning a+b",
                        multi_agent=False)
    res = CodeLabEngine(config=cfg).run()
    assert res["status"] == "passed"
    assert res["role_template"] is None                 # no fake LLM template
    assert res["llm_error"] == "not used (deterministic)"  # never probed backend
    assert res["llm_available"] is False


# ── C. Settings-owned Role Template defaults round-trip + validate ─────────
def test_c_settings_role_template_defaults(monkeypatch, tmp_path):
    ovpath = tmp_path / "settings.json"
    monkeypatch.setenv("LIFE_MEAN_OVERRIDES_FILE", str(ovpath))
    from experiments import settings as S
    # Initial defaults.
    view = S.get_settings()["role_templates"]
    assert view["code_lab"]["default_id"] == "coding-standard"
    assert view["code_lab"]["executable"] is True
    # Debate Lab integration wired the philosophical debate executor (spec §30):
    # Settings reads the SAME authoritative capability source as dispatch, so
    # debate reports EXECUTABLE — never a contradicting NOT_CONNECTED flag.
    assert view["philosophical_debate"]["status"] == "EXECUTABLE"
    assert view["philosophical_debate"]["executable"] is True
    # Persist a change (same valid default) and read back.
    S.update_settings({"role_templates": {
        "code_lab": "coding-standard", "philosophical_debate": "philosophical-debate"}})
    view = S.get_settings()["role_templates"]
    assert view["code_lab"]["default_id"] == "coding-standard"
    # Unknown template id rejected.
    with pytest.raises(ValueError):
        S.update_settings({"role_templates": {"code_lab": "does-not-exist"}})
    # Unknown subsystem rejected.
    with pytest.raises(ValueError):
        S.update_settings({"role_templates": {"hacker": "coding-standard"}})


# ── D. Code Lab resolves its template from the Settings default ────────────
def test_d_code_lab_resolves_settings_default(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_MEAN_OVERRIDES_FILE", str(tmp_path / "s.json"))
    from experiments import settings as S
    assert S.default_role_template("code_lab") == "coding-standard"
    # A different VALID default is honoured by the public accessor.
    S.update_settings({"role_templates": {"code_lab": "general-reasoning"}})
    assert S.default_role_template("code_lab") == "general-reasoning"


# ── F. Settings snapshot is frozen into RAW (immutable history) ────────────
def test_f_settings_snapshot_frozen_into_raw(tmp_path):
    """A run captures the resolved Settings into RAW so later Settings edits
    never rewrite historical provenance (Settings → snapshot → core → RAW)."""
    from code_lab.config import CodeLabConfig
    from code_lab.engine import CodeLabEngine
    eng = CodeLabEngine(config=CodeLabConfig(
        prompt="create a function add(a,b) returning a+b",
        run_id="snap_rt", multi_agent=False), base_dir=tmp_path)
    res = eng.run()
    assert res["status"] == "passed"
    ss = res.get("settings_snapshot")
    assert ss is not None
    # Exactly the Settings groups the flow names.
    for group in ("backend", "role_templates", "model_pool", "personas", "router"):
        assert group in ss, f"missing settings group {group}"
    # No secret ever: only a configured-flag + base_url.
    assert "api_key_configured" in ss["backend"]
    assert "api_key" not in json.dumps(ss).lower().replace("api_key_configured", "")
    # Deterministic: NO LLM template claimed.
    assert ss.get("resolved_template") is None
    # Frozen into the immutable RAW snapshot.
    raw = (tmp_path / "snap_rt" / "raw" / "run_snap_rt.json")
    assert raw.exists()
    raw_snap = json.loads(raw.read_text(encoding="utf-8")).get("settings_snapshot")
    assert raw_snap is not None and "captured_at" in raw_snap
    assert raw_snap["backend"]["base_url"] == ss["backend"]["base_url"]



# ── H. AGENT_STARTED is emitted BEFORE inference completes (§8/§19.9) ───────
def test_h_agent_started_observable_before_inference():
    import threading
    import time as _t
    from code_lab.multiagent import CodingMultiAgent

    class _BlockingLLM:
        """chat() blocks until released — lets us observe the event stream
        WHILE the model call is still in flight."""
        def __init__(self):
            self.release = threading.Event()
            self.in_chat = threading.Event()
            self.last_model_used = "fake"
        def chat(self, messages, model=None, temperature=0.8, max_tokens=700):
            self.in_chat.set()
            self.release.wait(5)
            return "```python\ndef f():\n    return 1\n```\n", "stop"
        def chat_stream(self, *a, **k):
            raise NotImplementedError

    blk = _BlockingLLM()
    events = []
    ma = CodingMultiAgent("http://x/v1", "", llm_client=blk,
                          on_event=events.append, role_models={"developer": ""})
    th = threading.Thread(target=lambda: ma.develop("plan", "Python"))
    th.start()
    assert blk.in_chat.wait(2), "fake LLM never entered chat()"

    # While the fake model is still BLOCKED, AGENT_STARTED must already be visible
    # (live progress — not an event fabricated after inference completed).
    _t.sleep(0.15)
    types_while_blocked = [e["type"] for e in events]
    assert "AGENT_STARTED" in types_while_blocked, \
        f"AGENT_STARTED not observable during inference ({types_while_blocked})"
    assert "AGENT_RESPONSE" not in types_while_blocked
    assert "AGENT_FAILED" not in types_while_blocked

    blk.release.set()
    th.join(5)
    types_after = [e["type"] for e in events]
    assert "AGENT_RESPONSE" in types_after
    assert types_after.index("AGENT_STARTED") < types_after.index("AGENT_RESPONSE")



def test_g_autopilot_raw_frozen_settings_snapshot(monkeypatch, tmp_path):
    """Both execution modes (deterministic + AutoPilot/Debate) persist the
    resolved Settings snapshot into the append-only RAW (Settings → snapshot →
    RAW), with no secrets."""
    import json as _json
    monkeypatch.chdir(tmp_path)
    from experiments.ui_controller import ExperimentUIController
    uc = ExperimentUIController()

    class _Res:
        def to_dict(self):
            return {"run_id": "r1", "task_id": "t1"}

    uc._persist_results_to_raw("exp_snap", [_Res()], mode="debate")
    raw_file = tmp_path / "data" / "raw_debates" / "exp_snap.jsonl"
    assert raw_file.exists()
    rec = _json.loads(raw_file.read_text(encoding="utf-8").splitlines()[0])
    assert rec["metadata"]["execution_mode"] == "debate"
    ss = rec.get("settings_snapshot")
    assert ss is not None
    for group in ("backend", "role_templates", "model_pool", "personas", "router"):
        assert group in ss
    assert "api_key_configured" in ss["backend"]
    assert "api_key" not in raw_file.read_text(encoding="utf-8").lower().replace("api_key_configured", "")


def _run_fake_backend(fake):
    server = HTTPServer(("127.0.0.1", 0), fake)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def test_e_honest_backend_diagnostic_401_then_fix():
    class FakeBackend(BaseHTTPRequestHandler):
        authenticated = False
        def do_GET(self):
            if not FakeBackend.authenticated:
                self.send_response(401)
                body = json.dumps({"error": {"message": "Invalid token",
                                             "type": "invalid_request_error",
                                             "code": "invalid_api_key"}}).encode()
            else:
                self.send_response(200)
                body = json.dumps({"data": [{"id": "model-a"}, {"id": "model-b"}]}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass

    server, base = _run_fake_backend(FakeBackend)
    try:
        from experiments.settings import _backend_models
        # 401 -> honest NOT authenticated, no silent empty list.
        bm = _backend_models(base, "bad-token")
        assert bm["models"] == []
        assert not bm["metadata"]["authenticated"]
        assert bm["error_code"]  # classified (no_models_or_auth / invalid token)
        # "Fix" the token: backend now authenticates.
        FakeBackend.authenticated = True
        bm2 = _backend_models(base, "good-token")
        assert set(bm2["models"]) == {"model-a", "model-b"}
        assert bm2["metadata"]["authenticated"] is True
        assert bm2["error_code"] is None
        # Token never appears in the diagnostic.
        assert "bad-token" not in json.dumps(bm)
        assert "good-token" not in json.dumps(bm2)
    finally:
        server.shutdown()



def test_settings_model_pools_covers_coding_debate_sandbox():
    """Unified per-domain model pool: Settings owns coding + debate + a reserved
    sandbox domain; role names are validated per domain."""
    import experiments.settings as S
    S.update_settings({"model_pools": {
        "coding": {"planner": "m-A", "developer": "m-B", "critic": "m-C",
                   "reviewer": "m-D", "judge": "m-E"},
        "debate": {"existentialist": "m-X", "moderator": "m-Y"}}})
    mp = S.model_pools()
    assert mp["coding"]["planner"] == "m-A" and mp["coding"]["judge"] == "m-E"
    assert mp["debate"]["existentialist"] == "m-X" and mp["debate"]["moderator"] == "m-Y"
    assert "sandbox" in mp and mp["sandbox"] == {}  # reserved (future), empty
    # domains catalog exposed
    assert set(S._DOMAIN_MODEL_ROLES) == {"coding", "debate", "sandbox"}
    # unknown role / unknown domain are rejected atomically
    with pytest.raises(ValueError):
        S.update_settings({"model_pools": {"coding": {"bogus_role": "m"}}})
    with pytest.raises(ValueError):
        S.update_settings({"model_pools": {"nonexistent_domain": {"a": "b"}}})
    # empty value = dynamic routing (recorded honestly elsewhere)
    S.update_settings({"model_pools": {
        "coding": {r: "" for r in S._CODING_ROLES},
        "debate": {r: "" for r in S._DEBATE_ROLES}}})
    pools = S.model_pools()
    assert all(v == "" for v in pools["coding"].values())
    assert all(v == "" for v in pools["debate"].values())
