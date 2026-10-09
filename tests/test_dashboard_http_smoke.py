"""HTTP-level smoke tests for the served dashboard (§9).

Stands up the REAL Hermes dashboard HTTP server on an ephemeral port, then
exercises the browser-visible contract end-to-end over actual HTTP:

    create experiment -> start -> execution -> RAW file -> status via API

No browser is used and no LLM is required: the mandatory flow runs in
deterministic mode (GOAL 9 allows an API/server-level test when a browser
driver is not available — this is honestly an HTTP/API test, NOT a browser
test). Also verifies malformed requests get a controlled 4xx JSON error
instead of crashing the server, and that RAW records the runtime execution_mode.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from experiments.dashboard import DashboardHandler, CodeLabController
from experiments.ui_controller import ExperimentUIController


@pytest.fixture(scope="module")
def server():
    ui = ExperimentUIController()
    DashboardHandler.ui_controller = ui
    DashboardHandler.code_lab_controller = CodeLabController()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    yield base, ui
    srv.shutdown()
    srv.server_close()


def _req(base, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        return e.code, payload


def test_served_dashboard_is_canonical(server):
    base, _ = server
    req = urllib.request.Request(base + "/dashboard")
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode()
        assert resp.status == 200
        assert "text/html" in resp.headers.get("Content-Type", "")
        # The served file carries the canonical file:// guard + API base.
        assert "guardFileScheme" in html
        assert "const API_BASE = '/api'" in html


def test_malformed_json_returns_controlled_400(server):
    base, _ = server
    # Invalid JSON body -> 400 JSON error, server keeps running.
    req = urllib.request.Request(
        base + "/api/experiments",
        data=b"{not valid json",
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req, timeout=15)
    assert ei.value.code == 400
    body = json.loads(ei.value.read().decode())
    assert "error" in body and "code" in body and "request_id" in body


def test_deterministic_create_start_raw_end_to_end(server, tmp_path):
    base, ui = server
    # Point RAW at a patchable location is unnecessary — ui_controller writes
    # under <root>/data/raw_debates. We capture the experiment_id then assert
    # the matching RAW file appears. To avoid collisions across runs we rely on
    # a fresh experiment_id each time.
    status, body = _req(
        base, "/api/experiments", method="POST",
        body={"domain": "math", "difficulty_range": [1, 1], "num_tasks": 2,
              "seed": 9, "deterministic": True},
    )
    assert status == 200, body
    assert body["status"] == "created"
    exp_id = body["experiment_id"]
    assert ui.get_experiment(exp_id) is not None

    # Start and wait for completion (bounded poll, no hard sleeps beyond a
    # short interval; the runner is fast with 2 tasks).
    status, sbody = _req(base, f"/api/experiments/{exp_id}/start", method="POST")
    assert status == 200, sbody
    assert sbody["status"] == "started"

    for _ in range(30):
        time.sleep(0.5)
        _, bench = _req(base, "/api/experiments")
        e = bench["experiments"].get(exp_id, {})
        if not e.get("is_running") and e.get("tasks_completed", 0) >= 2:
            break
    # Execution occurred, results exposed via the API the UI reads.
    assert e.get("tasks_completed", 0) >= 2, e

    # RAW belongs to THIS experiment and records the real execution mode.
    raw = Path("data/raw_debates") / f"{exp_id}.jsonl"
    assert raw.exists(), f"RAW not found: {raw}"
    first = json.loads(raw.read_text().splitlines()[0])
    assert first["experiment_id"] == exp_id
    assert first["metadata"]["execution_mode"] == "deterministic"
    assert first["provenance"]["run_id"]


def test_codelab_run_endpoint_live(server):
    base, _ = server
    status, body = _req(
        base, "/api/code-lab/runs", method="POST",
        body={"prompt": "Create a Python function is_prime(n) with unit tests.",
                      "run_tests": True, "multi_agent": False,
                      "template_id": "coding-standard"},
    )
    assert status == 200, body
    assert body["status"] == "created"



def test_experimental_capabilities_endpoint_live(server):
    """The sandbox capabilities route serves over HTTP and reports the honest
    executor connectivity (code connected, debate not connected here)."""
    base, _ = server
    status, body = _req(base, "/api/experimental/capabilities", method="GET")
    assert status == 200, body
    assert "code" in body["connected_executors"]
    assert "debate" not in body["connected_executors"]


def test_experimental_create_draft_never_runs_http(server):
    """Creating a design over HTTP yields a DRAFT that cannot run yet
    (400 DESIGN_INVALID) — the human-gated flow holds over the wire."""
    base, _ = server
    status, body = _req(base, "/api/experimental/designs", method="POST",
                        body={"description": "probe sorting algorithm edge cases"})
    assert status == 200, body
    assert body["status"] == "DRAFT"
    design_id = body["design_id"]
    st2, body2 = _req(base, f"/api/experimental/designs/{design_id}/run", method="POST", body={})
    assert st2 == 400 and body2.get("code") == "DESIGN_INVALID", body2
