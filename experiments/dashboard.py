"""Web-based experiment dashboard for synthetic data generation.

Provides a lightweight HTTP server with a web interface for
experiment configuration, monitoring, and control.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from experiments.config import ExperimentConfig
from experiments.ui_controller import ExperimentUIController

try:
    from code_lab.controller import CodeLabController
    _CODE_LAB_AVAILABLE = True
except Exception:  # pragma: no cover
    CodeLabController = None
    _CODE_LAB_AVAILABLE = False

logger = logging.getLogger("ExperimentDashboard")


from experimental.api import ExperimentalApiMixin
from compare.api import CompareApiMixin


def _experimental_id_from_path(path: str, suffix: str):
    """Extract the design_id before a literal '/run' or '/transition' suffix
    (string slicing — never str.strip, which strips the leading '/' and any
    matching hex chars)."""
    if not path.endswith(suffix):
        return None
    core = path[: -len(suffix)]
    return core.split("/")[-1] if core else None


class DashboardHandler(ExperimentalApiMixin, CompareApiMixin, BaseHTTPRequestHandler):
    """HTTP request handler for the experiment dashboard."""

    ui_controller: ExperimentUIController = None  # Set by server
    code_lab_controller: Any = None  # Set by server (from code_lab)

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)

        if parsed.path == "/api/experiments":
            self._send_json(self.ui_controller.get_dashboard_data())
        elif parsed.path == "/api/config":
            self._send_json({"modes": list(ExperimentConfig.__dataclass_fields__.keys())})
        elif parsed.path == "/api/settings":
            self._settings_get()
        elif parsed.path == "/api/role-templates":
            self._role_templates_get()
        elif parsed.path == "/api/code-lab/runs":
            self._code_lab_list()
        elif parsed.path.startswith("/api/code-lab/runs/") and parsed.path.endswith("/files"):
            self._code_lab_files(parsed.path)
        elif parsed.path.startswith("/api/code-lab/runs/") and parsed.path.endswith("/events"):
            self._code_lab_events(parsed.path)
        elif parsed.path == "/api/code-lab/timeline":
            self._code_lab_timeline()
        elif parsed.path.startswith("/api/code-lab/runs/"):
            self._code_lab_get(parsed.path)
        elif parsed.path == "/api/experimental/capabilities":
            self._experimental_capabilities()
        elif parsed.path == "/api/experimental/designs":
            self._experimental_designs()
        elif parsed.path.startswith("/api/experimental/designs/"):
            _id = ExperimentalApiMixin.match_design_id(parsed.path)
            if _id:
                self._experimental_design_get(_id)
            else:
                self._send_error(404, "Not found")
        elif parsed.path == "/api/compare/available":
            self._compare_available()
        elif parsed.path == "/api/compare/tree":
            self._compare_tree()
        elif parsed.path == "/api/compare/browser":
            self._compare_browser()
        elif parsed.path == "/api/compare/browser/rebuild":
            self._compare_browser(refresh=True)
        elif _id_match := re.match(r"^/api/compare/run/([^/]+)$", parsed.path):
            self._compare_run(_id_match.group(1))
        elif parsed.path == "/dashboard":
            self._serve_dashboard()
        else:
            self._send_error(404, "Not found")

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return

        if parsed.path == "/api/experiments":
            self._create_experiment(data)
        elif parsed.path == "/api/settings":
            self._settings_put(data)
        elif parsed.path == "/api/settings/credentials":
            self._settings_credentials_put(data)
        elif parsed.path == "/api/code-lab/runs":
            self._code_lab_create(data)
        elif parsed.path.startswith("/api/code-lab/runs/") and parsed.path.endswith("/start"):
            self._code_lab_start(parsed.path)
        elif parsed.path.startswith("/api/code-lab/runs/") and parsed.path.endswith("/stop"):
            self._code_lab_stop(parsed.path)
        elif parsed.path.startswith("/api/experiments/") and parsed.path.endswith("/start"):
            exp_id = parsed.path.split("/")[-2]
            if self.ui_controller.get_experiment(exp_id) is None:
                self._send_error(404, f"Experiment {exp_id} not found", code="not_found")
            else:
                self.ui_controller.start_experiment(exp_id)
                self._send_json({"status": "started"})
        elif parsed.path.startswith("/api/experiments/") and parsed.path.endswith("/stop"):
            exp_id = parsed.path.split("/")[-2]
            if self.ui_controller.get_experiment(exp_id) is None:
                self._send_error(404, f"Experiment {exp_id} not found", code="not_found")
            else:
                self.ui_controller.stop_experiment(exp_id)
                self._send_json({"status": "stopped"})
        elif parsed.path == "/api/experimental/designs":
            self._experimental_design_create(data)
        elif parsed.path == "/api/compare":
            self._compare_report(data)
        elif parsed.path == "/api/compare/subject":
            self._compare_subject_report(data)
        elif parsed.path == "/api/compare/tree/register":
            self._compare_tree_register(data)
        elif parsed.path == "/api/compare/tree/bootstrap":
            self._compare_tree_bootstrap(data)
        elif parsed.path.startswith("/api/experimental/designs/") and parsed.path.endswith("/transition"):
            _id = _experimental_id_from_path(parsed.path, "/transition")
            if _id:
                self._experimental_design_transition(_id, data)
            else:
                self._send_error(404, "Not found")
        elif parsed.path.startswith("/api/experimental/designs/") and parsed.path.endswith("/run"):
            _id = _experimental_id_from_path(parsed.path, "/run")
            if _id:
                self._experimental_design_run(_id)
            else:
                self._send_error(404, "Not found")
        else:
            self._send_error(404, "Not found")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        parsed = urlparse(self.path)

        if parsed.path.startswith("/api/code-lab/runs/"):
            run_id = parsed.path.strip("/").split("/")[-1]
            if self.code_lab_controller is not None and self.code_lab_controller.cleanup_run(run_id):
                self._send_json({"status": "deleted", "run_id": run_id})
            else:
                self._send_error(404, f"Code Lab run {run_id} not found")
        elif parsed.path.startswith("/api/experiments/"):
            exp_id = parsed.path.strip("/").split("/")[-1]
            if self.ui_controller.delete_experiment(exp_id):
                self._send_json({"status": "deleted", "experiment_id": exp_id})
            else:
                self._send_error(404, f"Experiment {exp_id} not found")
        elif parsed.path.startswith("/api/settings/personas/"):
            role = parsed.path.rstrip("/").split("/")[-1]
            from experiments.settings import delete_persona
            try:
                result = delete_persona(role)
                self._send_json({"status": "deleted", "role": role, "settings": result})
            except Exception as e:
                self._send_error(500, str(e), code="server")
        else:
            self._send_error(404, "Not found")

    def do_PUT(self) -> None:
        """Handle PUT requests (e.g. settings update)."""
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return
        if parsed.path == "/api/settings":
            self._settings_put(data)
        else:
            self._send_error(404, "Not found")

    # ── Code Lab API (Phase 10) ────────────────────────────────────────────
    def _code_lab_list(self) -> None:
        if self.code_lab_controller is None:
            self._send_json({"total_runs": 0, "running_count": 0, "runs": []})
        else:
            self._send_json(self.code_lab_controller.get_dashboard_data())

    def _code_lab_get(self, path: str) -> None:
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-1]
        data = self.code_lab_controller.get_run(run_id)
        if data is None:
            self._send_error(404, f"Run {run_id} not found")
        else:
            self._send_json(data)

    def _code_lab_files(self, path: str) -> None:
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        files = self.code_lab_controller.list_files(run_id)
        if files is None:
            self._send_error(404, f"Run {run_id} not found")
        else:
            self._send_json({"run_id": run_id, "files": files})

    def _code_lab_events(self, path: str) -> None:
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        data = self.code_lab_controller.get_run(run_id)
        if data is None:
            self._send_error(404, f"Run {run_id} not found")
        else:
            self._send_json({"run_id": run_id, "events": data.get("events", [])})

    def _code_lab_timeline(self, limit: int = 200) -> None:
        """GET /api/code-lab/timeline — lab-wide consolidated event timeline.

        Backend-real events aggregated across every Code Lab run (roadmap M0 /
        §22 live timeline). Returns {events:[...], count} with large payload
        fields stripped by the controller; the UI polls this for a live feed.
        """
        if self.code_lab_controller is None:
            self._send_json({"events": [], "count": 0})
            return
        self._send_json(self.code_lab_controller.get_timeline(limit=limit))

    def _code_lab_create(self, data: Dict[str, Any]) -> None:
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        try:
            from code_lab.config import CodeLabConfig
            # Booleans may arrive as strings.
            for key in ("multi_agent", "run_tests", "deterministic_validation", "reflection"):
                if key in data:
                    data[key] = str(data[key]).lower() in ("true", "1", "on", "yes")
            # Role Template is Settings-owned configuration: if the request does
            # not specify one, inherit the Settings default for Code Lab (§10-11).
            # The engine still validates executor compatibility before running.
            from experiments import settings as _settings
            if not data.get("template_id"):
                data["template_id"] = _settings.default_role_template("code_lab")
            # DISPATCH by executor_type: Code Lab only runs code_lab templates.
            # A philosophical_debate / general_reasoning template dispatches to
            # its OWN executor (refused here when not connected) BEFORE any
            # CodeLabConfig/CodeLabEngine is constructed — Code Lab stays
            # strictly coding-specific, never a sink for every template.
            from role_templates.executor import require_code_lab
            try:
                require_code_lab(data.get("template_id"))
            except ValueError as _de:
                self._send_error(400, str(_de), code="wrong_executor")
                return
            # Coding Pool (Settings-owned): inherit the per-role CL models unless
            # the request explicitly overrides role_models (S5/S6). Empty value =
            # dynamic routing, recorded honestly by the agent layer.
            if not data.get("role_models"):
                data["role_models"] = dict(_settings.get_coding_pool())
            cfg = CodeLabConfig.from_dict(data)
            view = self.code_lab_controller.create_run(cfg)
            # Start automatically like the experiment controller's auto-start.
            self.code_lab_controller.start_run(cfg.run_id)
            self._send_json({"run_id": cfg.run_id, "status": "created", "started": True})
        except (ValueError, TypeError) as e:
            self._send_error(400, f"Invalid Code Lab config: {e}", code="invalid")
        except Exception:
            self._send_error(500, "Failed to create Code Lab run", code="server")

    def _code_lab_start(self, path: str) -> None:
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        if self.code_lab_controller.start_run(run_id):
            self._send_json({"status": "started", "run_id": run_id})
        else:
            self._send_error(404, f"Run {run_id} not found")

    def _code_lab_stop(self, path: str) -> None:
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        if self.code_lab_controller.stop_run(run_id):
            self._send_json({"status": "stopping", "run_id": run_id})
        else:
            self._send_error(404, f"Run {run_id} not found")

    def _create_experiment(self, data: Dict[str, Any]) -> None:
        """Create a new experiment."""
        try:
            # Parse difficulty_range from string or array to tuple
            if "difficulty_range" in data:
                dr = data["difficulty_range"]
                if isinstance(dr, str):
                    try:
                        parsed = json.loads(dr)
                    except json.JSONDecodeError:
                        raise ValueError("Difficulty range must be two numbers like [1, 5]")
                    if not isinstance(parsed, (list, tuple)) or len(parsed) != 2:
                        raise ValueError("Difficulty range must contain exactly two values")
                    data["difficulty_range"] = tuple(parsed)
                elif isinstance(dr, list):
                    data["difficulty_range"] = tuple(dr)

            # Parse numeric fields
            if "num_tasks" in data:
                try:
                    data["num_tasks"] = int(data["num_tasks"])
                except (ValueError, TypeError):
                    raise ValueError("Number of tasks must be a positive integer")
            if "seed" in data:
                try:
                    data["seed"] = int(data["seed"])
                except (ValueError, TypeError):
                    raise ValueError("Seed must be an integer")

            # Parse boolean fields
            if "deterministic" in data:
                data["deterministic"] = str(data["deterministic"]).lower() in ("true", "1", "on")
            if "debate" in data:
                data["debate"] = str(data["debate"]).lower() in ("true", "1", "on")
            # "mode" is a UI convenience: map to the backing flags so the UI
            # selector is the single source of truth (GOAL 8/13).
            mode = data.pop("mode", None)
            if mode is not None:
                m = str(mode).lower()
                if m in ("debate", "debate_multi", "multi_agent"):
                    data["deterministic"] = False
                    data["debate"] = True
                elif m in ("deterministic", "deterministic_only", "manual"):
                    data["deterministic"] = True
                    data["debate"] = False
                # unknown mode -> ignore (falls through to existing flags)

            # Validate inputs with clear messages instead of raw tracebacks.
            num_tasks = data.get("num_tasks", 100)
            if not isinstance(num_tasks, int) or num_tasks <= 0:
                raise ValueError("Number of tasks must be a positive integer")

            if "difficulty_range" in data and data["difficulty_range"]:
                dr = tuple(data["difficulty_range"])
                if len(dr) != 2:
                    raise ValueError("Difficulty range must contain exactly two values")
                if not all(isinstance(x, (int, float)) for x in dr):
                    raise ValueError("Difficulty range values must be numbers")
                if int(dr[0]) > int(dr[1]):
                    raise ValueError(
                        f"Difficulty range must be ascending (min <= max), got {dr[0]} > {dr[1]}"
                    )

            # Keep only fields ExperimentConfig actually accepts: a stray UI or
            # legacy key (e.g. a checkbox forwarded as `_deterministic_force`)
            # must NEVER become an opaque 500. Unknown keys are ignored so the
            # selectors already mapped above (mode -> deterministic/debate) stay
            # the single source of truth.
            from dataclasses import fields as _dc_fields
            known = {f.name for f in _dc_fields(ExperimentConfig)}
            data = {k: v for k, v in data.items() if k in known}

            config = ExperimentConfig(**data)
            exp_id = config.experiment_id
            self.ui_controller.register_experiment(exp_id, config.to_dict())
            self._send_json({"experiment_id": exp_id, "status": "created"})
        except (ValueError, json.JSONDecodeError, TypeError) as e:
            self._send_error(400, str(e), code="invalid")
        except Exception:
            # Never surface internal state (paths/traces) to the browser.
            self._send_error(500, "Failed to create experiment", code="server")

    def _role_templates_get(self) -> None:
        """GET /api/role-templates — safe metadata for the built-in Role Templates.

        Returns only id/name/version/description/roles + hash (never instruction
        bodies, never secret content).
        """
        try:
            from role_templates.registry import get_registry
            self._send_json({"templates": get_registry().list_templates()})
        except Exception as e:  # pragma: no cover
            self._send_error(500, f"Failed to list role templates: {e}", code="server")

    def _settings_get(self) -> None:
        """GET /api/settings — sanitized current configuration (no secrets)."""
        from experiments.settings import get_settings
        self._send_json(get_settings())

    def _settings_put(self, data: Dict[str, Any]) -> None:
        """PUT /api/settings — validated safe partial update."""
        from experiments.settings import update_settings
        try:
            result = update_settings(data)
            self._send_json(result)
        except ValueError as e:
            self._send_error(400, str(e), code="invalid_settings")

    def _settings_credentials_put(self, data: Dict[str, Any]) -> None:
        """PUT /api/settings/credentials — store LM Studio base_url + API key.

        The key is written to a git-ignored env file and applied to the running
        process. Never read back.
        """
        from experiments.settings import update_llm_credentials
        try:
            result = update_llm_credentials(
                base_url=data.get("base_url", ""),
                api_key=data.get("api_key", ""),
            )
            self._send_json(result)
        except ValueError as e:
            self._send_error(400, str(e), code="invalid_settings")

    def _serve_dashboard(self) -> None:
        """Serve the dashboard HTML from package resources.

        Uses importlib.resources so it works from a source checkout, an
        editable install, or a built wheel — no repository-relative path
        (GOAL 3). Falls back to a repo-relative path only for dev convenience.
        """
        import importlib.resources as _res

        html = None
        try:
            html = _res.files("experiments.ui").joinpath("dashboard.html").read_text(
                encoding="utf-8"
            )
        except Exception:  # pragma: no cover - dev fallback
            probe = Path(__file__).resolve().parent.parent / "dashboard.html"
            if probe.exists():
                html = probe.read_text(encoding="utf-8")

        if html is not None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self._send_error(404, "Dashboard not found")

    def _send_json(self, data: Dict[str, Any]) -> None:
        """Send a JSON response."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_error(self, status: int, message: str, code: str = "error", request_id: str | None = None) -> None:
        """Send a structured error response.

        Never includes secrets, stack traces, or sensitive local paths — the
        `request_id` lets an operator match the browser message to server logs
        without exposing internals.
        """
        import uuid as _uuid
        body = {
            "error": message,
            "code": code,
            "request_id": request_id or _uuid.uuid4().hex[:12],
        }
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: N802
        """Custom log formatter."""
        logger.debug(f"{self.address_string()} - {format % args}")


def start_dashboard(
    host: str = "127.0.0.1",
    port: int = 8080,
    ui_controller: Optional[ExperimentUIController] = None,
    code_lab_controller: Optional[Any] = None,
) -> None:
    """Start the experiment dashboard server.

    Args:
        host: Host to bind to
        port: Port to listen on
        ui_controller: Optional UI controller instance
        code_lab_controller: Optional Code Lab controller instance
    """
    controller = ui_controller or ExperimentUIController()
    DashboardHandler.ui_controller = controller
    if code_lab_controller is None and _CODE_LAB_AVAILABLE:
        code_lab_controller = CodeLabController()
    DashboardHandler.code_lab_controller = code_lab_controller

    server = HTTPServer((host, port), DashboardHandler)
    logger.info(f"Starting dashboard on http://{host}:{port}")
    print(f"Dashboard available at http://{host}:{port}/dashboard")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping dashboard")
        server.shutdown()


def run_dashboard_thread(
    host: str = "127.0.0.1",
    port: int = 8080,
    ui_controller: Optional[ExperimentUIController] = None,
    code_lab_controller: Optional[Any] = None,
) -> threading.Thread:
    """Start the dashboard in a background thread.

    Args:
        host: Host to bind to
        port: Port to listen on
        ui_controller: Optional UI controller instance
        code_lab_controller: Optional Code Lab controller instance

    Returns:
        Thread instance
    """
    thread = threading.Thread(
        target=start_dashboard,
        args=(host, port, ui_controller, code_lab_controller),
        daemon=True,
    )
    thread.start()
    return thread


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Life_mean experiment dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default 8080)")
    args = parser.parse_args()
    start_dashboard(host=args.host, port=args.port)
