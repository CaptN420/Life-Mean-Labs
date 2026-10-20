"""
Tests for life_mean_studio.engine.health — service health probes.

These tests use a local HTTP server to simulate the LLM backend, the
dashboard and the orchestrator. No real services are contacted.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import TestCase, main

from life_mean_studio.engine.health import (
    ServiceHealth,
    check_dashboard,
    check_llm_backend,
    check_orchestrator,
    check_storage,
    load_available_models,
    run_all_health_checks,
)
from life_mean_studio.engine.storage import StudioStorage


class _FakeLLMHandler(BaseHTTPRequestHandler):
    """Serves /models with a configurable behavior via class attributes."""

    behavior = "ok"  # ok | unauthorized | malformed | missing

    def do_GET(self):
        if not self.path.endswith("/models"):
            self.send_response(404)
            self.end_headers()
            return
        if self.behavior == "unauthorized":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "token required"}')
        elif self.behavior == "malformed":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"not json at all")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({
                "data": [
                    {"id": "model-a"},
                    {"id": "model-b"},
                ]
            }).encode())

    def log_message(self, *args):
        pass


class _FakeDashboardHandler(BaseHTTPRequestHandler):
    behavior = "ok"

    def do_GET(self):
        if self.behavior == "notfound":
            self.send_response(404)
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>dashboard</html>" * 100)

    def log_message(self, *args):
        pass


class _FakeServer:
    """Context helper to run an HTTPServer on an ephemeral port in a thread."""

    def __init__(self, handler_cls):
        self.httpd = HTTPServer(("127.0.0.1", 0), handler_cls)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class TestServiceHealthDataclass(TestCase):
    def test_to_dict(self):
        h = ServiceHealth("Test", "ok", detail="fine", latency_ms=12.3, data={"a": 1})
        d = h.to_dict()
        self.assertEqual(d["name"], "Test")
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["latency_ms"], 12.3)
        self.assertEqual(d["data"]["a"], 1)


class TestCheckLLMBackend(TestCase):
    def test_ok(self):
        with _FakeServer(_FakeLLMHandler) as server:
            _FakeLLMHandler.behavior = "ok"
            base = f"http://127.0.0.1:{server.port}/v1"
            import life_mean_studio.engine.health as h
            h.DEFAULT_LLM_BASE = base  # not used, but keeps state consistent
            # Monkey-patch credential load to point at our fake server
            original = h._load_llm_credentials
            h._load_llm_credentials = lambda: (base, "test-key")
            try:
                result = check_llm_backend()
            finally:
                h._load_llm_credentials = original
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.data["model_count"], 2)
            self.assertEqual(result.data["models"], ["model-a", "model-b"])

    def test_unauthorized(self):
        with _FakeServer(_FakeLLMHandler) as server:
            _FakeLLMHandler.behavior = "unauthorized"
            base = f"http://127.0.0.1:{server.port}/v1"
            import life_mean_studio.engine.health as h
            original = h._load_llm_credentials
            h._load_llm_credentials = lambda: (base, "bad-key")
            try:
                result = check_llm_backend()
            finally:
                h._load_llm_credentials = original
            self.assertEqual(result.status, "error")
            self.assertIn("401", result.detail)

    def test_malformed(self):
        with _FakeServer(_FakeLLMHandler) as server:
            _FakeLLMHandler.behavior = "malformed"
            base = f"http://127.0.0.1:{server.port}/v1"
            import life_mean_studio.engine.health as h
            original = h._load_llm_credentials
            h._load_llm_credentials = lambda: (base, "test-key")
            try:
                result = check_llm_backend()
            finally:
                h._load_llm_credentials = original
            self.assertEqual(result.status, "degraded")

    def test_unreachable(self):
        # Port 1 is closed on virtually all systems -> connection refused fast.
        import life_mean_studio.engine.health as h
        original = h._load_llm_credentials
        h._load_llm_credentials = lambda: ("http://127.0.0.1:1/v1", "")
        try:
            result = check_llm_backend()
        finally:
            h._load_llm_credentials = original
        self.assertEqual(result.status, "error")
        self.assertIn("Unreachable", result.detail)


class TestCheckDashboard(TestCase):
    def test_ok(self):
        with _FakeServer(_FakeDashboardHandler) as server:
            _FakeDashboardHandler.behavior = "ok"
            result = check_dashboard(f"http://127.0.0.1:{server.port}")
            self.assertEqual(result.status, "ok")
            self.assertGreater(result.data["html_bytes"], 0)

    def test_notfound(self):
        with _FakeServer(_FakeDashboardHandler) as server:
            _FakeDashboardHandler.behavior = "notfound"
            result = check_dashboard(f"http://127.0.0.1:{server.port}")
            # Neither / nor /dashboard returns 200 -> nothing reachable.
            self.assertEqual(result.status, "error")


class TestCheckStorage(TestCase):
    def test_nonexistent_db(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nonexistent.db"
            storage = StudioStorage(db_path=str(db))
            result = check_storage(storage)
            self.assertEqual(result.status, "degraded")
            self.assertFalse(result.data["db_exists"])
            storage.close()

    def test_ok_and_counts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "studio.db"
            storage = StudioStorage(db_path=str(db))
            storage.create_workflow("wf1", {"mode": "single"})
            storage.create_prompt("p1", "c", "coding")

            result = check_storage(storage)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.data["counts"]["workflows"], 1)
            self.assertEqual(result.data["counts"]["prompts"], 1)

            storage.close()


class TestRunAll(TestCase):
    def test_summary_shape(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            storage = StudioStorage(db_path=str(Path(tmp) / "studio.db"))
            summary = run_all_health_checks(storage)
            self.assertIn("overall", summary)
            self.assertIn("checks", summary)
            self.assertEqual(len(summary["checks"]), 4)
            names = {c["name"] for c in summary["checks"]}
            self.assertIn("Local Storage", names)
            self.assertIn("LLM Backend", names)
            storage.close()


class TestLoadModels(TestCase):
    def test_returns_list(self):
        with _FakeServer(_FakeLLMHandler) as server:
            _FakeLLMHandler.behavior = "ok"
            base = f"http://127.0.0.1:{server.port}/v1"
            import life_mean_studio.engine.health as h
            original = h._load_llm_credentials
            h._load_llm_credentials = lambda: (base, "test-key")
            try:
                models = load_available_models()
            finally:
                h._load_llm_credentials = original
            self.assertEqual(models, ["model-a", "model-b"])


if __name__ == "__main__":
    main()
