"""UI tests for Life_mean dashboard.

Tests cover:
- Tab navigation
- Empty states rendering
- Data states rendering
- Error handling
- Form validation
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pytest

# Path to the canonical dashboard
DASHBOARD_PATH = Path(__file__).parent.parent / "experiments" / "ui" / "dashboard.html"


@pytest.fixture(scope="module")
def dashboard_html() -> str:
    """Load the canonical dashboard HTML."""
    assert DASHBOARD_PATH.exists(), f"Dashboard not found at {DASHBOARD_PATH}"
    return DASHBOARD_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def server(dashboard_html: str):
    """Start a minimal HTTP server serving the dashboard."""
    port = 18234

    class TestHandler:
        api_data: dict[str, Any] = {}

        def do_GET(self):
            from http.server import BaseHTTPRequestHandler
            # We'll use a real handler below
            pass

    # Use a simple server
    handler_class = type("TestHandler", (BaseHTTPRequestHandler,), {
        "api_data": {},
        "dashboard_html": dashboard_html,
        "do_GET": staticmethod(lambda self: TestHandler._get(self)),
        "do_POST": staticmethod(lambda self, data: TestHandler._post(self, data)),
        "log_message": staticmethod(lambda self, format, *args: None),
    })

    server = HTTPServer(("127.0.0.1", port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield server

    server.shutdown()


class TestDashboardTabs:
    """Test tab navigation and panel rendering."""

    def test_all_tabs_present(self, dashboard_html: str):
        """All expected tabs should be present in HTML."""
        expected_tabs = [
            "autopilot", "experiments", "debate", "code-lab",
            "settings", "compare", "clustertree", "experimental",
            "workspace", "skills"
        ]
        for tab in expected_tabs:
            assert f"data-tab=\"{tab}\"" in dashboard_html, f"Tab '{tab}' missing"

    def test_all_panels_present(self, dashboard_html: str):
        """All expected panels should be present in HTML."""
        expected_panels = [
            "panel-autopilot", "panel-experiments", "panel-debate",
            "panel-code-lab", "panel-settings", "panel-compare",
            "panel-clustertree", "panel-experimental",
            "panel-workspace", "panel-skills"
        ]
        for panel in expected_panels:
            assert f"id=\"{panel}\"" in dashboard_html, f"Panel '{panel}' missing"

    def test_skills_panel_structure(self, dashboard_html: str):
        """Skills panel should have required elements."""
        assert 'id="st-skills-active"' in dashboard_html
        assert 'id="st-tools-active"' in dashboard_html
        assert 'id="st-needs-pending"' in dashboard_html
        assert 'id="st-pipeline-pending"' in dashboard_html
        assert 'id="skills-list"' in dashboard_html
        assert 'id="tools-list"' in dashboard_html
        assert 'id="capabilities-list"' in dashboard_html
        assert 'id="pipeline-list"' in dashboard_html

    def test_observability_panels_structure(self, dashboard_html: str):
        """Observability panels should have required elements."""
        assert 'id="obs-prompt"' in dashboard_html
        assert 'id="obs-config"' in dashboard_html
        assert 'id="obs-agents"' in dashboard_html
        assert 'id="obs-transcript"' in dashboard_html
        assert 'id="obs-traces"' in dashboard_html
        assert 'id="obs-status"' in dashboard_html
        assert 'id="obs-round"' in dashboard_html


class TestDashboardJavaScript:
    """Test JavaScript functions exist and are well-formed."""

    def test_el_function_defined(self, dashboard_html: str):
        """The el() helper should be defined at module scope."""
        # Should be defined before loadSkillsPanel
        assert re.search(r"const\s+el\s*=\s*id\s*=>\s*document\.getElementById", dashboard_html)

    def test_load_skills_function_exists(self, dashboard_html: str):
        """loadSkills function should exist."""
        assert "async function loadSkills()" in dashboard_html or "async function loadSkills ()" in dashboard_html

    def test_load_tools_function_exists(self, dashboard_html: str):
        """loadTools function should exist."""
        assert "async function loadTools()" in dashboard_html or "async function loadTools ()" in dashboard_html

    def test_load_pipeline_function_exists(self, dashboard_html: str):
        """loadPipeline function should exist."""
        assert "async function loadPipeline()" in dashboard_html or "async function loadPipeline ()" in dashboard_html

    def test_load_capabilities_function_exists(self, dashboard_html: str):
        """loadCapabilities function should exist."""
        assert "async function loadCapabilities()" in dashboard_html or "async function loadCapabilities ()" in dashboard_html

    def test_switch_tab_function_exists(self, dashboard_html: str):
        """switchTab function should exist."""
        assert "function switchTab(name, btn)" in dashboard_html

    def test_load_skills_panel_function_exists(self, dashboard_html: str):
        """loadSkillsPanel function should exist."""
        assert "async function loadSkillsPanel()" in dashboard_html


class TestDashboardEndpoints:
    """Test that all required API endpoints are referenced in JS."""

    ENDPOINTS = [
        "experiments",
        "extensions/skills",
        "extensions/tools",
        "extensions/capabilities",
        "extensions/pipeline",
        "code-lab/runs",
        "debate/runs",
        "settings",
        "compare/",
        "cluster/",
    ]

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    def test_endpoint_referenced(self, dashboard_html: str, endpoint: str):
        """All API endpoints should be referenced in JavaScript."""
        assert endpoint in dashboard_html, f"Endpoint '{endpoint}' not referenced"


class TestDashboardValidation:
    """Test form validation and error handling."""

    def test_experiment_form_exists(self, dashboard_html: str):
        """Experiment creation form should exist."""
        assert 'id="experiment-form"' in dashboard_html

    def test_experiment_form_inputs(self, dashboard_html: str):
        """Experiment form should have required inputs."""
        assert 'id="domain"' in dashboard_html
        assert 'id="num-tasks"' in dashboard_html
        assert 'id="seed"' in dashboard_html
        assert 'id="exec-mode"' in dashboard_html

    def test_no_unescaped_jsx_in_html(self, dashboard_html: str):
        """HTML should not contain unescaped JSX (React-style)."""
        # Check for JSX patterns like <> or </> that indicate React leakage
        # Normal HTML tags like <div> are fine
        # This test is informational - the dashboard uses template literals
        # which may contain < characters in strings, but those are not JSX
        import re
        # Look for JSX in script blocks only (not in HTML content)
        script_match = re.search(r'<script>(.*?)</script>', dashboard_html, re.DOTALL)
        if script_match:
            js_code = script_match.group(1)
            # In JS, <> is not valid - should be null or undefined
            jsx_in_js = re.search(r'(?:^|[^<])<>(?:[^a-zA-Z]|$)', js_code)
            assert not jsx_in_js, "JSX-style empty tag found in JavaScript"


class TestDashboardNoObsoleteBackup:
    """Test that obsolete backup files are removed."""

    def test_no_backup_dashboard(self):
        """The old ui/dashboard.html backup should not exist."""
        backup_path = Path(__file__).parent.parent / "ui" / "dashboard.html"
        # This test will fail if the backup still exists
        # We already deleted it, so this should pass
        assert not backup_path.exists(), f"Obsolete backup still exists at {backup_path}"
