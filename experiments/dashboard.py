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

try:
    from debate_lab.controller import DebateLabController
    _DEBATE_LAB_AVAILABLE = True
except Exception:  # pragma: no cover
    DebateLabController = None
    _DEBATE_LAB_AVAILABLE = False

logger = logging.getLogger("ExperimentDashboard")


from experimental.api import ExperimentalApiMixin
from compare.api import CompareApiMixin
from life_mean_extensions.api import ExtensionsApiMixin


def _experimental_id_from_path(path: str, suffix: str):
    """Extract the design_id before a literal '/run' or '/transition' suffix
    (string slicing — never str.strip, which strips the leading '/' and any
    matching hex chars)."""
    if not path.endswith(suffix):
        return None
    core = path[: -len(suffix)]
    return core.split("/")[-1] if core else None


class DashboardHandler(ExperimentalApiMixin, CompareApiMixin, ExtensionsApiMixin, BaseHTTPRequestHandler):
    """HTTP request handler for the experiment dashboard."""

    ui_controller: ExperimentUIController = None  # Set by server
    code_lab_controller: Any = None  # Set by server (from code_lab)
    debate_lab_controller: Any = None  # Set by server (from debate_lab)
    extension_layer: Dict[str, Any] = None  # Set by server (from life_mean_extensions)

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
        elif parsed.path.startswith("/api/code-lab/runs/") and parsed.path.endswith("/raw"):
            self._code_lab_raw(parsed.path)
        elif _clfile := re.match(r"^/api/code-lab/runs/([^/]+)/file/(.+)$", parsed.path):
            self._code_lab_read_file(_clfile.group(1), _clfile.group(2))
        elif parsed.path.startswith("/api/code-lab/runs/") and parsed.path.endswith("/files"):
            self._code_lab_files(parsed.path)
        elif parsed.path.startswith("/api/code-lab/runs/") and parsed.path.endswith("/events"):
            self._code_lab_events(parsed.path)
        elif parsed.path == "/api/code-lab/timeline":
            self._code_lab_timeline()
        elif parsed.path.startswith("/api/code-lab/runs/"):
            self._code_lab_get(parsed.path)
        elif parsed.path == "/api/debate/runs":
            self._debate_lab_list()
        elif parsed.path == "/api/debate/timeline":
            self._debate_lab_timeline()
        elif parsed.path == "/api/debate/templates":
            self._debate_lab_templates()
        elif parsed.path.startswith("/api/debate/runs/") and parsed.path.endswith("/events"):
            self._debate_lab_events(parsed.path)
        elif parsed.path.startswith("/api/debate/runs/"):
            self._debate_lab_get(parsed.path)
        elif _feedback_match := re.match(r"^/api/experimental/feedback/([A-Za-z0-9]+)$", parsed.path):
            self._experimental_feedback_get(_feedback_match.group(1))
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
        # ── Extensions API (modular self-extension layer) ────────────────────
        elif parsed.path == "/api/extensions/skills":
            self._extensions_skills_list()
        elif _ext_id := self.match_extension_id(parsed.path):
            if _ext_id[0] == "skills":
                self._extensions_skill_get(_ext_id[1])
            elif _ext_id[0] == "tools":
                self._extensions_tool_get(_ext_id[1])
            else:
                self._send_error(404, "Not found")
        elif parsed.path == "/api/extensions/tools":
            self._extensions_tools_list()
        elif parsed.path == "/api/extensions/capabilities":
            self._extensions_capabilities_list()
        elif parsed.path == "/api/extensions/pipeline":
            self._extensions_pipeline_list()
        elif parsed.path == "/api/cluster/tree":
            self._cluster_tree()
        elif parsed.path == "/api/cluster/graph":
            self._cluster_graph()
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
        elif parsed.path == "/api/debate/runs":
            self._debate_lab_create(data)
        elif parsed.path.startswith("/api/debate/runs/") and parsed.path.endswith("/start"):
            self._debate_lab_start(parsed.path)
        elif parsed.path.startswith("/api/debate/runs/") and parsed.path.endswith("/stop"):
            self._debate_lab_stop(parsed.path)
        elif parsed.path.startswith("/api/debate/runs/") and parsed.path.endswith("/message"):
            self._debate_lab_message(parsed.path, data)
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
        elif parsed.path == "/api/experimental/harness":
            self._experimental_harness(data)
        elif parsed.path == "/api/experimental/harness/start":
            self._experimental_harness_start(data)
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
        # ── Extensions API (modular self-extension layer) ────────────────────
        elif parsed.path == "/api/extensions/skills":
            self._extensions_skill_create(data)
        elif parsed.path == "/api/extensions/tools":
            self._extensions_tool_create(data)
        elif parsed.path == "/api/extensions/capabilities/analyze":
            self._extensions_capabilities_analyze(data)
        elif _ext_id := self.match_extension_id(parsed.path):
            if _ext_id[0] == "skills":
                # Match /approve, /activate, /disable, /delete
                sub = parsed.path.split("/")[-1]
                if sub == "approve":
                    self._extensions_skill_approve(_ext_id[1], data)
                elif sub == "activate":
                    self._extensions_skill_activate(_ext_id[1])
                elif sub == "disable":
                    self._extensions_skill_disable(_ext_id[1])
                else:
                    self._send_error(404, "Not found")
            elif _ext_id[0] == "tools":
                sub = parsed.path.split("/")[-1]
                if sub == "approve":
                    self._extensions_tool_approve(_ext_id[1], data)
                elif sub == "activate":
                    self._extensions_tool_activate(_ext_id[1])
                elif sub == "disable":
                    self._extensions_tool_disable(_ext_id[1])
                else:
                    self._send_error(404, "Not found")
            else:
                self._send_error(404, "Not found")
        elif _pipe_id := self.match_pipeline_id(parsed.path):
            sub = parsed.path.split("/")[-1]
            if sub == "approve":
                self._extensions_pipeline_approve(_pipe_id, data)
            elif sub == "activate":
                self._extensions_pipeline_activate(_pipe_id)
            else:
                self._send_error(404, "Not found")
        elif parsed.path.startswith("/api/extensions/capabilities/") and parsed.path.endswith("/resolve"):
            need_id = parsed.path.split("/")[-2]
            self._extensions_capabilities_resolve(need_id, data)
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
        elif parsed.path.startswith("/api/debate/runs/"):
            run_id = parsed.path.strip("/").split("/")[-1]
            if self.debate_lab_controller is None:
                self._send_error(404, "Debate Lab not enabled")
            elif not self.debate_lab_controller.delete_run(run_id):
                self._send_error(409, "DELETE_BLOCKED_ACTIVE_RUN: run is still active",
                                 code="delete_blocked_active_run")
            else:
                self._send_json({"status": "deleted", "run_id": run_id})
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

    def _code_lab_raw(self, path: str) -> None:
        """GET /api/code-lab/runs/{id}/raw — immutable RAW snapshot + trajectory.

        Reads directly from the run's RAW directory on disk (source of truth).
        """
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        data = self.code_lab_controller.read_raw(run_id)
        if data is None:
            self._send_error(404, f"Run {run_id} not found")
        else:
            self._send_json(data)

    def _code_lab_read_file(self, run_id: str, rel_path: str) -> None:
        """GET /api/code-lab/runs/{id}/file/{relpath} — read one workspace file."""
        if self.code_lab_controller is None:
            self._send_error(404, "Code Lab not enabled")
            return
        content = self.code_lab_controller.read_file(run_id, rel_path)
        if content is None:
            self._send_error(404, f"File {rel_path!r} not found in run {run_id}")
        else:
            self._send_json({"run_id": run_id, "path": rel_path, "content": content})

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

    # ── Debate Lab API (Final Integration Pass) ───────────────────────────
    def _debate_lab_list(self) -> None:
        if self.debate_lab_controller is None:
            self._send_json({"total_runs": 0, "running_count": 0, "runs": []})
        else:
            self._send_json(self.debate_lab_controller.get_dashboard_data())

    def _debate_lab_get(self, path: str) -> None:
        if self.debate_lab_controller is None:
            self._send_error(404, "Debate Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-1]
        data = self.debate_lab_controller.get_run(run_id)
        if data is None:
            self._send_error(404, f"Run {run_id} not found")
        else:
            self._send_json(data)

    def _debate_lab_events(self, path: str) -> None:
        if self.debate_lab_controller is None:
            self._send_error(404, "Debate Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        data = self.debate_lab_controller.get_run(run_id)
        if data is None:
            self._send_error(404, f"Run {run_id} not found")
        else:
            self._send_json({"run_id": run_id, "events": data.get("events", [])})

    def _debate_lab_timeline(self, limit: int = 200) -> None:
        """GET /api/debate/timeline — lab-wide backend-real event timeline."""
        if self.debate_lab_controller is None:
            self._send_json({"events": [], "count": 0})
            return
        self._send_json(self.debate_lab_controller.get_timeline(limit=limit))

    def _debate_lab_templates(self) -> None:
        """GET /api/debate/templates — Debate-compatible RoleTemplates only
        (spec §22/§4): executor_type in {debate, philosophical_debate}."""
        try:
            from debate_lab.validation import template_summary
            from role_templates.registry import get_registry
            reg = get_registry()
            templates = [
                template_summary(tpl) for tpl in reg._latest.values()
                if (tpl.executor_type or "") in ("debate", "philosophical_debate")
            ]
            self._send_json({"templates": templates})
        except Exception as e:  # pragma: no cover
            self._send_error(500, f"Failed to list debate templates: {e}", code="server")

    def _debate_lab_create(self, data: Dict[str, Any]) -> None:
        if self.debate_lab_controller is None:
            self._send_error(404, "Debate Lab not enabled")
            return
        try:
            from debate_lab.config import DebateLabConfig
            from experiments import settings as _settings
            if "prevent_repetition" in data:
                data["prevent_repetition"] = (
                    str(data["prevent_repetition"]).lower() in ("true", "1", "on", "yes"))
            if not data.get("template_id"):
                data["template_id"] = _settings.default_role_template("philosophical_debate")
            # DISPATCH by executor_type: Debate Lab only runs debate-compatible
            # templates (spec §31). A code_lab template is refused here BEFORE
            # any DebateEngine is constructed; no cross-engine fallback.
            from role_templates.executor import require_debate
            try:
                require_debate(data.get("template_id"))
            except ValueError as _de:
                self._send_error(400, str(_de), code="wrong_executor")
                return
            cfg = DebateLabConfig.from_dict(data)
            view = self.debate_lab_controller.create_run(cfg)
            self._send_json({"run_id": cfg.run_id, "status": "created", "started": False})
        except (ValueError, TypeError) as e:
            self._send_error(400, f"Invalid Debate Lab config: {e}", code="invalid")
        except Exception:
            self._send_error(500, "Failed to create Debate Lab run", code="server")

    def _debate_lab_start(self, path: str) -> None:
        if self.debate_lab_controller is None:
            self._send_error(404, "Debate Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        if self.debate_lab_controller.start_run(run_id):
            self._send_json({"status": "started", "run_id": run_id})
        else:
            self._send_error(404, f"Run {run_id} not found or already running")

    def _debate_lab_stop(self, path: str) -> None:
        if self.debate_lab_controller is None:
            self._send_error(404, "Debate Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        if self.debate_lab_controller.stop_run(run_id):
            self._send_json({"status": "stopping", "run_id": run_id})
        else:
            self._send_error(404, f"Run {run_id} not found")

    def _debate_lab_message(self, path: str, data: Dict[str, Any]) -> None:
        """POST /api/debate/runs/{run_id}/message — researcher intervention
        (§77): a real canonical event, labeled RESEARCHER_INTERVENTION, and fed
        into the live debate context while the run is active."""
        if self.debate_lab_controller is None:
            self._send_error(404, "Debate Lab not enabled")
            return
        run_id = path.strip("/").split("/")[-2]
        content = str(data.get("content", "") or "").strip()
        if not content:
            self._send_error(400, "RESEARCHER_MESSAGE_EMPTY: message content is required",
                             code="invalid")
            return
        if not self.debate_lab_controller.researcher_message(run_id, content):
            self._send_error(404, f"Run {run_id} not found")
            return
        self._send_json({"status": "recorded", "run_id": run_id,
                         "type": "RESEARCHER_INTERVENTION"})

    def _validate_experiment_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce whitelist and strict type conversion for experiment creation."""
        known_keys = {"num_tasks", "seed", "deterministic", "debate", "difficulty_range", "mode"}
        validated = {}
        
        for key in known_keys:
            if key not in data:
                continue
            
            val = data[key]
            if key == "num_tasks":
                try:
                    validated[key] = int(val)
                except (ValueError, TypeError):
                    raise ValueError("Number of tasks must be a positive integer")
            elif key == "seed":
                try:
                    validated[key] = int(val)
                except (ValueError, TypeError):
                    raise ValueError("Seed must be an integer")
            elif key in ("deterministic", "debate"):
                validated[key] = str(val).lower() in ("true", "1", "on")
            elif key == "difficulty_range":
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                    except json.JSONDecodeError:
                        raise ValueError("Difficulty range must be two numbers like [1, 5]")
                    parsed = parsed
                else:
                    parsed = val
                
                if not isinstance(parsed, (list, tuple)) or len(parsed) != 2:
                    raise ValueError("Difficulty range must contain exactly two values")
                validated[key] = tuple(parsed)
            elif key == "mode":
                m = str(val).lower()
                if m in ("debate", "debate_multi", "multi_agent"):
                    validated["deterministic"] = False
                    validated["debate"] = True
                elif m in ("deterministic", "deterministic_only", "manual"):
                    validated["deterministic"] = True
                    validated["debate"] = False
            else:
                validated[key] = val

        from dataclasses import fields as _dc_fields
        config_fields = {f.name for f in _dc_fields(ExperimentConfig)}
        
        for k, v in data.items():
            if k in config_fields and k not in validated:
                validated[k] = v

        if "difficulty_range" in validated and validated["difficulty_range"]:
            dr = validated["difficulty_range"]
            if not all(isinstance(x, (int, float)) for x in dr):
                raise ValueError("Difficulty range values must be numbers")
            if int(dr[0]) > int(dr[1]):
                raise ValueError(
                    f"Difficulty range must be ascending (min <= max), got {dr[0]} > {dr[1]}"
                )

        nt = validated.get("num_tasks", 100)
        if not isinstance(nt, int) or nt <= 0:
            raise ValueError("Number of tasks must be a positive integer")

        return validated

    def _create_experiment(self, data: Dict[str, Any]) -> None:
        """Create a new experiment."""
        try:
            data = self._validate_experiment_input(data)

            config = ExperimentConfig(**data)
            exp_id = config.experiment_id
            self.ui_controller.register_experiment(exp_id, config.to_dict())
            self._send_json({"experiment_id": exp_id, "status": "created"})
        except (ValueError, json.JSONDecodeError, TypeError) as e:
            self._send_error(400, str(e), code="invalid")
        except Exception:
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

    def _cluster_tree(self) -> None:
        """GET /api/cluster/tree — hierarchical 'cluster tree' of the lab:
        experiments grouped by subject (topic tree) + a run-directory explorer
        over the on-disk run workspaces. Read-only, bounded walk, no secrets.
        """
        import os as _os
        from pathlib import Path as _P

        try:
            subjects = self._subjects()
            subject_tree = {
                "tree": subjects.tree(),
                "topics": subjects.topics(),
                "root": str(subjects.root),
            }
        except Exception as exc:  # pragma: no cover - honest degradation
            subject_tree = {"tree": {}, "topics": [], "root": "",
                            "error": str(exc)[:120]}

        def _walk(base, max_entries=200):
            if not base.is_dir():
                return {"dirs": {}, "files": []}
            node = {"dirs": {}, "files": []}
            try:
                entries = sorted(_os.listdir(base))
            except OSError:
                return node
            for name in entries:
                if len(node["dirs"]) + len(node["files"]) >= max_entries:
                    node["files"].append("… (truncated)")
                    break
                p = base / name
                try:
                    if p.is_dir():
                        node["dirs"][name] = _walk(p, max_entries)
                    else:
                        node["files"].append(name)
                except OSError:  # pragma: no cover - unreadable entry
                    continue
            return node

        cwd = _P.cwd()
        runs = {
            "code_lab_runs": _walk(cwd / "code_lab_runs"),
            "debate_lab_runs": _walk(cwd / "debate_lab_runs"),
        }
        self._send_json({"subject_tree": subject_tree, "runs": runs})

    def _cluster_graph(self) -> None:
        """GET /api/cluster/graph — deterministic cluster graph (CG1+CG2).

        Reuses the CG1 model: runs from the compare index, conditions from RAW
        (read-only), a SubjectTree, and the fingerprint-keyed cache. Returns
        nodes/edges/clusters + counts. No LLM, no RAW writes.
        """
        from pathlib import Path as _P
        try:
            from compare.index import load_index
            from compare.conditions_index import load_conditions_index
            from compare.graph import build_graph_payload
        except Exception as exc:  # pragma: no cover - import hardening
            self._send_error(500, f"cluster graph unavailable: {exc}",
                             code="cluster_graph_unavailable")
            return
        try:
            index = load_index()
            rows = index.get("experiments", [])
            try:
                subjects = self._subjects()
            except Exception:
                subjects = None
            # Use cached conditions index instead of re-reading every RAW file.
            conditions = load_conditions_index()
            payload = build_graph_payload(
                rows, subjects, conditions,
                cache_path=_P("data/cluster_graph.json"))
            payload["sources"] = {
                "index": index.get("generated_at") or "cached",
                "runs_considered": len(rows),
                "conditions_loaded": sum(1 for c in conditions.values() if c),
            }
        except Exception as exc:  # pragma: no cover - honest degradation
            self._send_error(500, f"cluster graph failed: {exc}",
                             code="cluster_graph_error")
            return
        self._send_json(payload)

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
    debate_lab_controller: Optional[Any] = None,
) -> None:
    """Start the experiment dashboard server.

    Args:
        host: Host to bind to
        port: Port to listen on
        ui_controller: Optional UI controller instance
        code_lab_controller: Optional Code Lab controller instance
        debate_lab_controller: Optional Debate Lab controller instance
    """
    controller = ui_controller or ExperimentUIController()
    DashboardHandler.ui_controller = controller
    if code_lab_controller is None and _CODE_LAB_AVAILABLE:
        code_lab_controller = CodeLabController()
    DashboardHandler.code_lab_controller = code_lab_controller
    if debate_lab_controller is None and _DEBATE_LAB_AVAILABLE:
        debate_lab_controller = DebateLabController()
    DashboardHandler.debate_lab_controller = debate_lab_controller
    # Wire up the modular self-extension layer
    try:
        from life_mean_extensions.pipeline import create_extension_layer
        DashboardHandler.extension_layer = create_extension_layer()
        logger.info("Extensions layer initialized")
    except Exception as exc:  # pragma: no cover - graceful degradation
        logger.warning("Extensions layer unavailable: %s", exc)
        DashboardHandler.extension_layer = None

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
    debate_lab_controller: Optional[Any] = None,
) -> threading.Thread:
    """Start the dashboard in a background thread.

    Args:
        host: Host to bind to
        port: Port to listen on
        ui_controller: Optional UI controller instance
        code_lab_controller: Optional Code Lab controller instance
        debate_lab_controller: Optional Debate Lab controller instance

    Returns:
        Thread instance
    """
    thread = threading.Thread(
        target=start_dashboard,
        args=(host, port, ui_controller, code_lab_controller, debate_lab_controller),
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
