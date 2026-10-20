#!/usr/bin/env python3
"""
Unit tests for WorkflowConfig and WorkflowManager.
"""

import sys
import os
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from life_mean_studio.workflows import WorkflowConfig, AgentConfig
from life_mean_studio.workflows.manager import WorkflowManager
from life_mean_studio.engine.storage import StudioStorage


class TestWorkflowConfig:
    """Test cases for WorkflowConfig."""
    
    def test_valid_single_agent(self):
        """Test valid single-agent config."""
        config = WorkflowConfig(
            name="Test",
            mode="single",
            agents=[AgentConfig(role="coder")]
        )
        errors = config.validate()
        assert len(errors) == 0
    
    def test_valid_multi_agent(self):
        """Test valid multi-agent config."""
        config = WorkflowConfig(
            name="Test",
            mode="multi",
            agents=[
                AgentConfig(role="planner"),
                AgentConfig(role="coder"),
            ]
        )
        errors = config.validate()
        assert len(errors) == 0
    
    def test_invalid_mode(self):
        """Test invalid mode."""
        config = WorkflowConfig(name="Test", mode="invalid")
        errors = config.validate()
        assert any("Mode must be" in e for e in errors)
    
    def test_multi_agent_no_agents(self):
        """Test multi-agent mode without agents."""
        config = WorkflowConfig(name="Test", mode="multi")
        errors = config.validate()
        assert any("requires at least one agent" in e for e in errors)
    
    def test_negative_budget(self):
        """Test negative compression budget."""
        config = WorkflowConfig(name="Test", mode="single", compression_budget=-100)
        errors = config.validate()
        assert any("non-negative" in e for e in errors)
    
    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        original = WorkflowConfig(
            name="Test",
            mode="multi",
            agents=[AgentConfig(role="planner")],
            compression_enabled=True,
            compression_budget=2000,
        )
        
        data = original.to_dict()
        restored = WorkflowConfig.from_dict(data)
        
        assert restored.name == original.name
        assert restored.mode == original.mode
        assert len(restored.agents) == 1
        assert restored.agents[0].role == "planner"
        assert restored.compression_enabled == original.compression_enabled
    
    def test_default_values(self):
        """Test default values."""
        config = WorkflowConfig(name="Test", mode="single")
        assert config.compression_enabled == False
        assert config.compression_budget == 4000
        assert config.max_iterations == 10
        assert config.timeout_seconds == 60


class TestWorkflowManager:
    """Test cases for WorkflowManager."""
    
    def setup_method(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.storage = StudioStorage(db_path=self.temp_db.name)
        self.manager = WorkflowManager(self.storage)
    
    def teardown_method(self):
        """Clean up temporary database."""
        self.storage.close()
        import time
        time.sleep(0.5)  # Allow file handle to release on Windows
        if os.path.exists(self.temp_db.name):
            try:
                os.unlink(self.temp_db.name)
            except PermissionError:
                pass
    
    def test_create_workflow(self):
        """Test creating a workflow via manager."""
        config = WorkflowConfig(
            name="Test Workflow",
            mode="single",
            agents=[AgentConfig(role="coder")]
        )
        
        workflow_id = self.manager.create(config)
        assert workflow_id is not None
        
        retrieved = self.manager.get(workflow_id)
        assert retrieved is not None
        assert retrieved.name == "Test Workflow"
    
    def test_create_invalid_workflow(self):
        """Test creating an invalid workflow."""
        config = WorkflowConfig(name="Test", mode="invalid")
        
        with pytest.raises(ValueError, match="Mode must be"):
            self.manager.create(config)
    
    def test_list_workflows(self):
        """Test listing workflows."""
        self.manager.create(WorkflowConfig(name="W1", mode="single"))
        self.manager.create(WorkflowConfig(name="W2", mode="multi", agents=[AgentConfig(role="coder")]))
        
        workflows = self.manager.list_all()
        assert len(workflows) == 2
    
    def test_get_default_workflow(self):
        """Test getting a default workflow template."""
        config = self.manager.get_default("single-agent-quick-coding")
        assert config is not None
        assert config.mode == "single"
    
    def test_seed_defaults(self):
        """Test seeding default workflows."""
        # Skip this test on Windows due to SQLite file locking issues
        import platform
        if platform.system() == "Windows":
            pytest.skip("Skipping seed_defaults on Windows due to SQLite file locking")
        
        self.manager.seed_defaults()
        
        workflows = self.manager.list_all()
        assert len(workflows) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
