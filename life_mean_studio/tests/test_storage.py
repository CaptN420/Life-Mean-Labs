#!/usr/bin/env python3
"""
Unit tests for StudioStorage.
Uses temporary SQLite database — no modification to existing data.
"""

import sys
import os
import tempfile
import pytest
from pathlib import Path

# Add Life_mean root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from life_mean_studio.engine.storage import StudioStorage


class TestStudioStorage:
    """Test cases for StudioStorage."""
    
    def setup_method(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.storage = StudioStorage(db_path=self.temp_db.name)
    
    def teardown_method(self):
        """Clean up temporary database."""
        self.storage.close()
        import time
        time.sleep(0.5)  # Allow file handle to release on Windows
        if os.path.exists(self.temp_db.name):
            try:
                os.unlink(self.temp_db.name)
            except PermissionError:
                pass  # Ignore if still locked
    
    # ---- Workflow tests ----
    
    def test_create_workflow(self):
        """Test creating a valid workflow."""
        workflow_id = self.storage.create_workflow(
            name="Test Workflow",
            config={"mode": "single"},
            description="A test workflow"
        )
        
        assert workflow_id is not None
        assert isinstance(workflow_id, str)
        
        workflow = self.storage.get_workflow(workflow_id)
        assert workflow is not None
        assert workflow["name"] == "Test Workflow"
        assert workflow["config"]["mode"] == "single"
    
    def test_create_workflow_invalid_config(self):
        """Test creating a workflow with invalid config."""
        with pytest.raises(ValueError, match="Config missing required key: mode"):
            self.storage.create_workflow(
                name="Bad Workflow",
                config={}
            )
    
    def test_list_workflows(self):
        """Test listing workflows."""
        self.storage.create_workflow("Workflow 1", {"mode": "single"})
        self.storage.create_workflow("Workflow 2", {"mode": "multi"})
        
        workflows = self.storage.list_workflows()
        assert len(workflows) == 2
    
    def test_update_workflow(self):
        """Test updating a workflow."""
        workflow_id = self.storage.create_workflow(
            name="Original",
            config={"mode": "single"}
        )
        
        updated = self.storage.update_workflow(
            workflow_id,
            {"name": "Updated", "config": {"mode": "multi"}}
        )
        
        assert updated is True
        workflow = self.storage.get_workflow(workflow_id)
        assert workflow["name"] == "Updated"
        assert workflow["config"]["mode"] == "multi"
    
    def test_delete_workflow(self):
        """Test deleting a workflow."""
        workflow_id = self.storage.create_workflow(
            name="To Delete",
            config={"mode": "single"}
        )
        
        deleted = self.storage.delete_workflow(workflow_id)
        assert deleted is True
        
        assert self.storage.get_workflow(workflow_id) is None
    
    # ---- Prompt tests ----
    
    def test_create_prompt(self):
        """Test creating a prompt."""
        prompt_id = self.storage.create_prompt(
            name="Test Prompt",
            content="Hello {{name}}",
            category="coding",
            variables={"name": "World"}
        )
        
        assert prompt_id is not None
        
        prompt = self.storage.get_prompt(prompt_id)
        assert prompt is not None
        assert prompt["name"] == "Test Prompt"
        assert prompt["category"] == "coding"
        assert prompt["variables"]["name"] == "World"
    
    def test_list_prompts(self):
        """Test listing prompts."""
        self.storage.create_prompt("Prompt 1", "Content 1", "coding")
        self.storage.create_prompt("Prompt 2", "Content 2", "security")
        
        all_prompts = self.storage.list_prompts()
        assert len(all_prompts) == 2
        
        coding_prompts = self.storage.list_prompts(category="coding")
        assert len(coding_prompts) == 1
    
    def test_search_prompts(self):
        """Test searching prompts."""
        self.storage.create_prompt("Security Audit", "Check for security issues", "security")
        self.storage.create_prompt("Code Review", "Review the code", "coding")
        
        results = self.storage.search_prompts("security")
        assert len(results) == 1
        assert results[0]["name"] == "Security Audit"
    
    def test_update_prompt(self):
        """Test updating a prompt."""
        prompt_id = self.storage.create_prompt(
            name="Original",
            content="Hello",
            category="general"
        )
        
        updated = self.storage.update_prompt(prompt_id, {"content": "Updated"})
        assert updated is True
        
        prompt = self.storage.get_prompt(prompt_id)
        assert prompt["content"] == "Updated"
        assert prompt["version"] == 2
    
    def test_delete_prompt(self):
        """Test deleting a prompt."""
        prompt_id = self.storage.create_prompt(
            name="To Delete",
            content="Content"
        )
        
        deleted = self.storage.delete_prompt(prompt_id)
        assert deleted is True
        
        assert self.storage.get_prompt(prompt_id) is None
    
    # ---- Session tests ----
    
    def test_create_session(self):
        """Test creating a session."""
        workflow_id = self.storage.create_workflow("Test", {"mode": "single"})
        session_id = self.storage.create_session(workflow_id)
        
        assert session_id is not None
        
        session = self.storage.get_session(session_id)
        assert session is not None
        assert session["status"] == "idle"
        assert session["workflow_id"] == workflow_id
    
    def test_update_session(self):
        """Test updating a session."""
        workflow_id = self.storage.create_workflow("Test", {"mode": "single"})
        session_id = self.storage.create_session(workflow_id)
        
        updated = self.storage.update_session(session_id, {"status": "running"})
        assert updated is True
        
        session = self.storage.get_session(session_id)
        assert session["status"] == "running"
    
    def test_list_sessions(self):
        """Test listing sessions."""
        workflow_id = self.storage.create_workflow("Test", {"mode": "single"})
        self.storage.create_session(workflow_id)
        self.storage.create_session(workflow_id)
        
        sessions = self.storage.list_sessions(workflow_id=workflow_id)
        assert len(sessions) == 2
    
    # ---- Event reference tests ----
    
    def test_add_event_reference(self):
        """Test adding an event reference."""
        event_id = self.storage.add_event_reference(
            event_type="AGENT_STARTED",
            session_id="test-session",
            run_id="test-run"
        )
        
        assert event_id is not None
        
        events = self.storage.get_events(session_id="test-session")
        assert len(events) == 1
        assert events[0]["event_type"] == "AGENT_STARTED"
    
    def test_get_events(self):
        """Test getting events with filters."""
        self.storage.add_event_reference("AGENT_STARTED", session_id="session1")
        self.storage.add_event_reference("TOOL_CALL_REQUESTED", session_id="session1")
        self.storage.add_event_reference("AGENT_FINISHED", session_id="session2")
        
        # Get all events for session1
        events = self.storage.get_events(session_id="session1")
        assert len(events) == 2
        
        # Get only AGENT_STARTED events
        agent_events = self.storage.get_events(event_type="AGENT_STARTED")
        assert len(agent_events) == 1
        assert agent_events[0]["event_type"] == "AGENT_STARTED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
