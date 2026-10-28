"""
Tests for Life_mean Studio launcher (Phase C).

These tests verify:
- Application can be imported
- UI classes exist
- Storage integration works
- Security constraints are enforced
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestImports:
    """Test that all modules can be imported."""
    
    def test_launcher_module_imports(self):
        """Test launcher module imports."""
        from life_mean_studio.launcher.app import LifeMeanStudioApp
        assert LifeMeanStudioApp is not None
    
    def test_storage_imports(self):
        """Test storage module imports."""
        from life_mean_studio.engine.storage import StudioStorage
        assert StudioStorage is not None
    
    def test_workflow_imports(self):
        """Test workflow modules import."""
        from life_mean_studio.workflows import WorkflowConfig, AgentConfig
        from life_mean_studio.workflows.manager import WorkflowManager
        assert WorkflowConfig is not None
        assert AgentConfig is not None
        assert WorkflowManager is not None
    
    def test_prompt_imports(self):
        """Test prompt modules import."""
        from life_mean_studio.prompts.collection import PromptCollection
        from life_mean_studio.prompts import Prompt
        assert PromptCollection is not None
        assert Prompt is not None


class TestSecurityConstraints:
    """Test security constraints are enforced."""

    def test_run_button_enabled_by_design(self):
        """RUN is enabled — it drives the real engine (no UI stub)."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp
        source = inspect.getsource(LifeMeanStudioApp._create_quick_run_section)
        assert "self.run_btn.setEnabled(True)" in source

    def test_stop_button_disabled_by_default(self):
        """STOP starts disabled (no active run) and is enabled by the runner."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp
        source = inspect.getsource(LifeMeanStudioApp._create_quick_run_section)
        assert "self.stop_btn.setEnabled(False)" in source

    def test_no_subprocess_calls(self):
        """Test that no subprocess calls are made in UI code."""
        import inspect
        from life_mean_studio.launcher import app

        source = inspect.getsource(app)
        assert "subprocess" not in source.lower() or "import subprocess" not in source

    def test_no_network_server_calls(self):
        """Test that no network servers are started."""
        import inspect
        from life_mean_studio.launcher import app

        source = inspect.getsource(app)
        assert "http.server" not in source
        assert "socketserver" not in source

    def test_no_docker_calls(self):
        """Test that no Docker calls are made."""
        import inspect
        from life_mean_studio.launcher import app

        source = inspect.getsource(app)
        # Check for actual docker module imports, not just mentions in comments
        assert "import docker" not in source.lower()


class TestStorageIntegration:
    """Test storage integration."""
    
    def test_storage_creation(self):
        """Test that StudioStorage can be created."""
        from life_mean_studio.engine.storage import StudioStorage
        storage = StudioStorage()
        assert storage is not None
    
    def test_workflow_manager_creation(self):
        """Test that WorkflowManager can be created."""
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.workflows.manager import WorkflowManager
        
        storage = StudioStorage()
        manager = WorkflowManager(storage)
        assert manager is not None
    
    def test_prompt_collection_creation(self):
        """Test that PromptCollection can be created."""
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.prompts.collection import PromptCollection
        
        storage = StudioStorage()
        collection = PromptCollection(storage)
        assert collection is not None


class TestWorkflowCRUD:
    """Test workflow CRUD operations."""

    def test_create_workflow(self):
        """Test creating a workflow."""
        import tempfile
        import os
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.workflows import WorkflowConfig
        from life_mean_studio.workflows.manager import WorkflowManager

        with tempfile.NamedTemporaryFile(suffix="_test.db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = StudioStorage(db_path=tmp_path)
            manager = WorkflowManager(storage)

            config = WorkflowConfig(name="test-workflow", mode="single")
            wf_id = manager.create(config)
            assert wf_id is not None

            # Cleanup
            manager.delete(wf_id)
        finally:
            import time
            time.sleep(0.5)
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass

    def test_list_workflows(self):
        """Test listing workflows."""
        import tempfile
        import os
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.workflows.manager import WorkflowManager

        with tempfile.NamedTemporaryFile(suffix="_test.db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = StudioStorage(db_path=tmp_path)
            manager = WorkflowManager(storage)

            workflows = manager.list_all()
            assert isinstance(workflows, list)
        finally:
            import time
            time.sleep(0.5)
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass

    def test_invalid_workflow_rejected(self):
        """Test that invalid workflows are rejected."""
        import tempfile
        import os
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.workflows import WorkflowConfig
        from life_mean_studio.workflows.manager import WorkflowManager

        with tempfile.NamedTemporaryFile(suffix="_test.db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = StudioStorage(db_path=tmp_path)
            manager = WorkflowManager(storage)

            # Invalid mode
            config = WorkflowConfig(name="test", mode="invalid")
            with pytest.raises(ValueError):
                manager.create(config)
        finally:
            import time
            time.sleep(0.5)
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass


class TestPromptCRUD:
    """Test prompt CRUD operations."""
    
    def test_create_prompt(self):
        """Test creating a prompt."""
        import tempfile
        import os
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.prompts.collection import PromptCollection
        
        # Use a temp database to avoid locking issues
        with tempfile.NamedTemporaryFile(suffix="_test.db", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            storage = StudioStorage(db_path=tmp_path)
            collection = PromptCollection(storage)
            
            prompt_id = collection.create(
                name="test-prompt",
                content="Test content",
                category="general"
            )
            assert prompt_id is not None
            
            # Cleanup
            collection.delete(prompt_id)
        finally:
            import time
            time.sleep(0.5)
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
    
    def test_list_prompts(self):
        """Test listing prompts."""
        import tempfile
        import os
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.prompts.collection import PromptCollection
        
        # Use a temp database to avoid locking issues
        with tempfile.NamedTemporaryFile(suffix="_test.db", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            storage = StudioStorage(db_path=tmp_path)
            collection = PromptCollection(storage)
            
            prompts = collection.list_all()
            assert isinstance(prompts, list)
        finally:
            import time
            time.sleep(0.5)
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass


class TestJinja2Security:
    """Test Jinja2 template security."""
    
    def test_sandboxed_environment(self):
        """Test that Jinja2 sandbox is available."""
        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment()
        assert env is not None
    
    def test_unsafe_template_rejected(self):
        """Test that unsafe templates are rejected."""
        from jinja2.sandbox import SandboxedEnvironment
        
        env = SandboxedEnvironment()
        
        # This should raise an error
        with pytest.raises(Exception):
            env.from_string("{{ config.__class__.__mro__[1].__subclasses__() }}").render()


class TestNavigationStructure:
    """Test navigation structure."""
    
    def test_all_pages_exist(self):
        """Test that all expected pages exist in the code."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp
        
        # Check that methods exist
        assert hasattr(LifeMeanStudioApp, '_create_home_page')
        assert hasattr(LifeMeanStudioApp, '_create_services_page')
        assert hasattr(LifeMeanStudioApp, '_create_workflows_page')
        assert hasattr(LifeMeanStudioApp, '_create_prompts_page')
        assert hasattr(LifeMeanStudioApp, '_create_console_page')
        assert hasattr(LifeMeanStudioApp, '_create_dev_page')
        assert hasattr(LifeMeanStudioApp, '_create_packages_page')
        assert hasattr(LifeMeanStudioApp, '_create_settings_page')


class TestRunControls:
    """Quick Run controls are wired to the real engine (no UI stub)."""

    def test_quick_run_buttons_enabled(self):
        """RUN is enabled by construction; STOP starts disabled (no run yet)."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp

        source = inspect.getsource(LifeMeanStudioApp._create_quick_run_section)
        assert "self.run_btn.setEnabled(True)" in source
        assert "self.stop_btn.setEnabled(False)" in source
        # Handlers are wired, not email
        assert "self.run_btn.clicked.connect(self._on_run)" in source
        assert "self.stop_btn.clicked.connect(self._on_stop)" in source

    def test_runner_wired_in_constructor(self):
        """The app builds a StudioRunner (real engine), not a stub."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp

        source = inspect.getsource(LifeMeanStudioApp.__init__)
        assert "StudioRunner(self.storage)" in source

    def test_service_buttons_disabled(self):
        """Test that service start/stop legacy button stays disabled (no direct
        service control; the Services page only shows real health probes)."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp

        source = inspect.getsource(LifeMeanStudioApp._create_services_page)
        assert "legacy_btn.setEnabled(False)" in source


class TestErrorHandling:
    """Test error handling."""
    
    def test_storage_error_on_invalid_config(self):
        """Test that invalid config raises error."""
        from life_mean_studio.engine.storage import StudioStorage
        from life_mean_studio.workflows import WorkflowConfig
        from life_mean_studio.workflows.manager import WorkflowManager
        
        storage = StudioStorage()
        manager = WorkflowManager(storage)
        
        # Invalid workflow - missing name
        config = WorkflowConfig(mode="single")  # name is required
        with pytest.raises(ValueError):
            manager.create(config)
