"""Code Lab conversation-first surface (§ item 2): canonical conversation from
real backend events, live full agent responses, RAW readback, workspace file
read, and DELETE — mirroring the Debate Lab conversation-first mandate.

The conversation must NEVER be reconstructed from template/workflow/status:
every entry derives from a real event, and if an agent never produced a
response no text is fabricated.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

from code_lab.controller import CodeLabController
from code_lab.config import CodeLabConfig
from code_lab.workspace import CodeLabWorkspace


# ── controller-level helpers ────────────────────────────────────────────────
class _Engine:
    """Fake engine that emits the scripted events into the controller handler."""

    def __init__(self, events, handler):
        self._events, self._handler = events, handler

    def run(self):
        for ev in self._events:
            self._handler(dict(ev))
        return {"status": "passed"}

    def request_stop(self):
        pass


def _handler_for(ctl, run_id):
    view = ctl._runs[run_id]

    def handler(ev):
        with ctl._lock:
            view.events.append(ev)
            if ev["type"] == "RUN_COMPLETED":
                view.status = "passed"
            elif ev["type"] == "RUN_FAILED":
                view.status = "failed"
            elif ev["type"] == "RUN_STOPPED":
                view.status = "stopped"

    return handler


def _seed_run(ctl, run_id, events, result=None, result_status="passed"):
    cfg = CodeLabConfig(prompt="x", project_name="p", multi_agent=False, seed=1)
    cfg.run_id = run_id
    view = ctl.create_run(cfg)
    ctl._runs[run_id] = view
    h = _handler_for(ctl, run_id)
    for ev in events:
        h(dict(ev))
    if result is not None:
        view.result = result
        view.status = result_status
    return view


def _ev(t, run_id, **kw):
    return {"type": t, "run_id": run_id, "time": time.time(), **kw}


# ── conversation is canonical (events only, never synthesized) ──────────────
class TestConversationCanonical:
    def test_conversation_only_from_real_events(self):
        ctl = CodeLabController()
        events = [
            _ev("RUN_STARTED", "r1", llm_available=True),
            _ev("AGENT_SELECTED", "r1", roles=["PLANNER"], template_id="t"),
            _ev("PLAN_CREATED", "r1", plan={"plan_id": "p1", "steps": ["s1"]}, router="dynamic_router"),
            _ev("FILE_CREATED", "r1", file="fib.py", by_agent="DEVELOPER", operation="write", iteration=1),
            _ev("TEST_PASSED", "r1", iteration=1, passed=4, total=4),
            _ev("VALIDATION_COMPLETED", "r1", results={"deterministic_validation": True}),
            _ev("RUN_COMPLETED", "r1", status="passed", files_created=["fib.py"], iterations=1),
        ]
        _seed_run(ctl, "r1", events)
        conv = ctl.get_run("r1")["conversation"]
        types = [c["type"] for c in conv]
        assert types == ["RUN_STARTED", "AGENT_SELECTED", "PLAN", "FILE_EVENT",
                         "TEST", "VALIDATION", "TERMINAL"], types
        # every entry links back to a real event index
        assert all(c["event_index"] is not None for c in conv)

    def test_deterministic_run_no_agent_fabrication(self):
        ctl = CodeLabController()
        events = [
            _ev("RUN_STARTED", "d1", llm_available=False),
            _ev("VALIDATION_COMPLETED", "d1", results={"deterministic_validation": True}),
            _ev("RUN_COMPLETED", "d1", status="passed"),
        ]
        _seed_run(ctl, "d1", events)
        conv = ctl.get_run("d1")["conversation"]
        agent_types = [c["type"] for c in conv
                       if c["type"] in ("AGENT_RESPONSE", "AGENT_FAILED")]
        assert agent_types == [], "no agent messages may be invented in deterministic mode"

    def test_agent_failed_no_fabricated_response(self):
        ctl = CodeLabController()
        events = [
            _ev("RUN_STARTED", "f1", llm_available=False),
            _ev("AGENT_FAILED", "f1", role="DEVELOPER", stage="generate",
                error_type="empty_response",
                message="Deterministic generator produced no usable output."),
            _ev("RUN_FAILED", "f1", status="failed", error_count=1, stage_reached="generate"),
        ]
        _seed_run(ctl, "f1", events, result=None, result_status="failed")
        conv = ctl.get_run("f1")["conversation"]
        failed = [c for c in conv if c["type"] == "AGENT_FAILED"]
        assert len(failed) == 1
        assert failed[0]["error_type"] == "empty_response"
        assert "no usable output" in failed[0]["message"]
        assert failed[0]["response"] is None, "no response text may be fabricated"
        assert conv[-1]["type"] == "TERMINAL"
        assert conv[-1]["detail"]["status"] == "failed"


class TestConversationFullText:
    def test_agent_response_full_text_live_from_event(self):
        """The AGENT_RESPONSE event carries the full visible response, so the
        conversation shows real text even before the run's final result exists."""
        ctl = CodeLabController()
        text = "def fib(n):\n    return n if n < 2 else fib(n-1) + fib(n-2)"
        events = [
            _ev("RUN_STARTED", "r2", llm_available=True),
            _ev("AGENT_RESPONSE", "r2", role="DEVELOPER", stage="develop",
                model="qwen3.5-0.8b", configured_model=None,
                selection_mode="backend_default", duration_ms=500,
                finish_reason="stop", response=text),
        ]
        _seed_run(ctl, "r2", events)  # result=None -> live path
        conv = ctl.get_run("r2")["conversation"]
        dev = [c for c in conv if c["type"] == "AGENT_RESPONSE"][0]
        assert dev["response"] == text
        assert dev["model"] == "qwen3.5-0.8b"
        assert dev["selection_mode"] == "backend_default"
        assert dev["duration_ms"] == 500

    def test_retry_alignment_per_role_fifo(self):
        """DEVELOPER attempt 1 + attempt 2 map to the two DEVELOPER responses
        in order (per-role FIFO over agent_trace + event payloads)."""
        ctl = CodeLabController()
        events = [
            _ev("AGENT_RESPONSE", "r3", role="PLANNER", stage="plan", model="m", response="PLAN"),
            _ev("AGENT_RESPONSE", "r3", role="DEVELOPER", stage="develop", model="m", response="D1"),
            _ev("AGENT_RESPONSE", "r3", role="DEVELOPER", stage="develop", model="m", response="D2"),
            _ev("AGENT_RESPONSE", "r3", role="CRITIC", stage="critique", model="m", response="C"),
        ]
        result = {"agent_trace": [
            {"agent": "PLANNER", "ok": True, "response": "PLAN"},
            {"agent": "DEVELOPER", "ok": True, "response": "D1"},
            {"agent": "DEVELOPER", "ok": True, "attempt": 2, "response": "D2"},
            {"agent": "CRITIC", "ok": True, "response": "C"},
        ]}
        _seed_run(ctl, "r3", events, result=result)
        conv = ctl.get_run("r3")["conversation"]
        resps = [c for c in conv if c["type"] == "AGENT_RESPONSE"]
        assert [c["response"] for c in resps] == ["PLAN", "D1", "D2", "C"]
        assert resps[2]["attempt"] == 2


class TestRawReadback:
    def test_read_raw_snapshot_and_trajectory(self, tmp_path):
        ctl = CodeLabController(base_dir=Path(tmp_path))
        cfg = CodeLabConfig(prompt="x", project_name="p", multi_agent=False, seed=1)
        cfg.run_id = "raw1"
        view = ctl.create_run(cfg)
        ctl._runs["raw1"] = view
        ws = CodeLabWorkspace(cfg, base_dir=Path(tmp_path)).create()
        ws.write_raw_snapshot("run_raw1", {"run_id": "raw1", "status": "passed"})
        ws.append_raw("trajectory", {"iteration": 1, "ok": True})
        data = ctl.read_raw("raw1")
        assert data["snapshot"]["status"] == "passed"
        assert data["trajectory"] == [{"iteration": 1, "ok": True}]
        assert ctl.read_raw("nope") is None


# ── HTTP routes: conversation / raw / files / delete ────────────────────────
_csrf_token = {"value": None}
_csrf_cookie = {"value": ""}


def _bootstrap_csrf(base):
    if _csrf_token["value"] is not None:
        return
    req = urllib.request.Request(base + "/dashboard")
    with urllib.request.urlopen(req, timeout=15) as resp:
        set_cookie = resp.headers.get("Set-Cookie", "")
    m = re.search(r"lifemean_csrf=([^;]+)", set_cookie)
    if m:
        _csrf_cookie["value"] = "lifemean_csrf=" + m.group(1)
        _csrf_token["value"] = urllib.parse.unquote(m.group(1))
    else:
        _csrf_token["value"] = ""


def _req(base, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if method in ("POST", "PUT", "DELETE"):
        _bootstrap_csrf(base)
        if _csrf_cookie["value"]:
            req.add_header("Cookie", _csrf_cookie["value"])
        if _csrf_token["value"]:
            req.add_header("X-Lifemean-CSRF", _csrf_token["value"])
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        return e.code, payload


def _run_server(tmp_path):
    from experiments.dashboard import DashboardHandler
    DashboardHandler.code_lab_controller = CodeLabController(base_dir=Path(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{port}"


class TestHttpRoutes:
    def test_http_run_conversation_raw_files_delete(self, tmp_path):
        srv, base = _run_server(tmp_path)
        try:
            status, body = _req(
                base, "/api/code-lab/runs", method="POST",
                body={"prompt": "Create a Python function is_prime(n) with unit tests.",
                      "run_tests": True, "multi_agent": False,
                      "template_id": "coding-standard"},
            )
            assert status == 200, body
            run_id = body["run_id"]
            for _ in range(60):
                time.sleep(0.5)
                _, run = _req(base, f"/api/code-lab/runs/{run_id}")
                if run.get("status") in ("passed", "failed", "stopped"):
                    break
            # GET run carries the canonical conversation (backend-derived)
            assert "conversation" in run, run.keys()
            agent_types = {c["type"] for c in run["conversation"]}
            assert "AGENT_RESPONSE" not in agent_types and "AGENT_FAILED" not in agent_types, \
                "deterministic HTTP run must not fabricate agent messages"
            assert "TERMINAL" in agent_types

            # RAW from disk: snapshot + trajectory, honest execution_mode
            _, raw = _req(base, f"/api/code-lab/runs/{run_id}/raw")
            assert raw["snapshot"] and raw["snapshot"]["execution_mode"] == "deterministic"
            assert isinstance(raw["trajectory"], list)

            # Workspace files are readable
            _, files = _req(base, f"/api/code-lab/runs/{run_id}/files")
            assert files["files"], files
            src = files["files"][0]
            _, fbody = _req(base, f"/api/code-lab/runs/{run_id}/file/{src}")
            assert fbody["content"] and "def " in fbody["content"]

            # DELETE removes run + workspace, subsequent GET is 404
            status, d = _req(base, f"/api/code-lab/runs/{run_id}", method="DELETE")
            assert status == 200, d
            status, _ = _req(base, f"/api/code-lab/runs/{run_id}")
            assert status == 404
        finally:
            srv.shutdown()
            srv.server_close()
