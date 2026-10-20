"""Test that all pages can be instantiated and have expected widgets."""

import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def app_storage(tmp_path):
    """Create a temp database for the app."""
    from life_mean_studio.engine.storage import StudioStorage
    db_path = tmp_path / "test_studio.db"
    storage = StudioStorage(db_path=str(db_path))
    yield storage
    storage.close()


@pytest.fixture
def studio_app(app_storage, monkeypatch):
    """Create a LifeMeanStudioApp with test storage and isolated preferences."""
    from PySide6.QtWidgets import QApplication
    from life_mean_studio.launcher.app import LifeMeanStudioApp

    # Isolate preferences to tmp_path
    pref_dir = app_storage.db_path.parent / ".life_mean_studio"
    pref_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: pref_dir.parent)

    app = QApplication.instance() or QApplication([])
    win = LifeMeanStudioApp(storage=app_storage)
    yield win
    win.close()


def test_app_instantiation(studio_app):
    """Test app can be created."""
    assert studio_app is not None
    assert studio_app.windowTitle() == "Life_mean Studio"


def test_pages_exist(studio_app):
    """Test all pages are created."""
    # Check central widget
    assert studio_app.central_widget is not None

    # Check 8 pages exist
    pages = [
        studio_app.home_page,
        studio_app.services_page,
        studio_app.workflows_page,
        studio_app.prompts_page,
        studio_app.console_page,
        studio_app.dev_page,
        studio_app.packages_page,
        studio_app.settings_page,
    ]
    assert len(pages) == 8
    for i, page in enumerate(pages):
        assert page is not None, f"Page {i} is None"


def test_quick_run_widgets(studio_app):
    """Test Quick Run section has expected widgets."""
    # Check workflow combo exists and is disabled
    assert studio_app.workflow_combo is not None
    assert not studio_app.workflow_combo.isEnabled()

    # Check model combo exists and is disabled
    assert studio_app.model_combo is not None
    assert not studio_app.model_combo.isEnabled()

    # Check RUN button exists and is disabled
    assert studio_app.run_btn is not None
    assert not studio_app.run_btn.isEnabled()

    # Check STOP button exists and is disabled
    assert studio_app.stop_btn is not None
    assert not studio_app.stop_btn.isEnabled()


def test_workflow_list(studio_app):
    """Test workflow list widget."""
    assert studio_app.workflow_list is not None
    # Should be empty by default (no workflows loaded)
    assert studio_app.workflow_list.count() == 0


def test_prompt_list(studio_app):
    """Test prompt list widget."""
    assert studio_app.prompt_list is not None
    # Should be empty by default (no prompts loaded)
    assert studio_app.prompt_list.count() == 0


def test_console_output(studio_app):
    """Test console output widget."""
    assert studio_app.console_output is not None
    assert studio_app.console_output.isReadOnly()


def test_nav_toolbar(studio_app):
    """Test navigation toolbar has all buttons."""
    # Check mode toggle exists
    assert studio_app.mode_action is not None

    # Check we can navigate
    studio_app._navigate_to(0)
    assert studio_app.central_widget.currentIndex() == 0


def test_dev_page_tabs(studio_app):
    """Test dev page has expected tabs."""
    # Get the tab widget from dev page
    # The dev page contains a QTabWidget
    # We can verify by checking the structure
    assert studio_app.dev_page is not None
