"""Tests for workspace UI interface."""

import json
import re
from pathlib import Path

import pytest


WORKSPACE_DIR = Path(__file__).parent.parent / "experiments" / "ui"


class TestWorkspaceFiles:
    """Verify workspace files exist and are valid."""

    def test_workspace_html_exists(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        assert html_path.exists(), "workspace.html must exist"

    def test_workspace_css_exists(self):
        css_path = WORKSPACE_DIR / "workspace.css"
        assert css_path.exists(), "workspace.css must exist"

    def test_workspace_js_exists(self):
        js_path = WORKSPACE_DIR / "workspace.js"
        assert js_path.exists(), "workspace.js must exist"

    def test_workspace_html_valid_structure(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")

        # Basic HTML structure
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

        # Required sections
        assert 'data-tool="topbar"' in content
        assert 'data-tool="left-panel"' in content
        assert 'data-tool="center-panel"' in content
        assert 'data-tool="right-panel"' in content
        assert 'data-tool="bottom-panel"' in content

    def test_workspace_css_valid(self):
        css_path = WORKSPACE_DIR / "workspace.css"
        content = css_path.read_text(encoding="utf-8")

        # Check for required CSS variables
        assert "--bg-primary:" in content
        assert "--accent:" in content

    def test_workspace_js_syntax(self):
        js_path = WORKSPACE_DIR / "workspace.js"
        content = js_path.read_text(encoding="utf-8")

        # Must be valid JS (basic check)
        assert "function workspace" in content or "const workspace" in content


class TestWorkspaceAPI:
    """Test the programmatic API exposed by workspace.js."""

    def test_workspace_exposes_api(self):
        js_path = WORKSPACE_DIR / "workspace.js"
        content = js_path.read_text(encoding="utf-8")

        # Required API methods
        required_methods = [
            "readFile",
            "writeFile",
            "runCode",
            "runPrompt",
            "runWorkflow",
            "getState",
            "setValue",
            "getValue",
        ]

        for method in required_methods:
            assert f"async {method}" in content or f" {method}(" in content, \
                f"API method '{method}' must be exposed"

    def test_workspace_returns_structured_response(self):
        js_path = WORKSPACE_DIR / "workspace.js"
        content = js_path.read_text(encoding="utf-8")

        # Response structure (shorthand or explicit)
        assert "ok:" in content or "ok," in content
        assert "action" in content
        assert "data:" in content or "data," in content
        assert "error:" in content or "error," in content
        assert "timestamp:" in content or "timestamp," in content


class TestWorkspaceDataAttributes:
    """Test that data attributes are present for machine parsing."""

    def test_data_tool_attributes(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")

        # Required data-tool attributes
        required_tools = [
            "topbar",
            "left-panel",
            "center-panel",
            "right-panel",
            "bottom-panel",
            "code-editor",
            "console-output",
            "state-display",
        ]

        for tool in required_tools:
            assert f'data-tool="{tool}"' in content, \
                f"data-tool='{tool}' must be present"

    def test_data_action_attributes(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")

        # Required data-action attributes
        required_actions = [
            "switch_view",
            "start_run",
            "stop_run",
            "change_model",
            "change_workflow",
            "clear_console",
        ]

        for action in required_actions:
            assert f"data-action=\"{action}\"" in content or \
                   f"data-action='{action}'" in content, \
                f"data-action='{action}' must be present"


class TestWorkspaceViews:
    """Test that all required views exist."""

    def test_editor_view_exists(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")
        assert 'data-view-id="editor"' in content

    def test_workflow_view_exists(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")
        assert 'data-view-id="workflow"' in content

    def test_history_view_exists(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")
        assert 'data-view-id="history"' in content

    def test_settings_view_exists(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")
        assert 'data-view-id="settings"' in content


class TestWorkspaceAccessibility:
    """Test basic accessibility requirements."""

    def test_html_has_lang_attribute(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")
        assert 'lang=' in content

    def test_html_has_title(self):
        html_path = WORKSPACE_DIR / "workspace.html"
        content = html_path.read_text(encoding="utf-8")
        assert "<title>" in content
        assert "</title>" in content
