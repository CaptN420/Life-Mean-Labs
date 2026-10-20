#!/usr/bin/env python3
"""
Unit tests for Prompt and PromptCollection.
"""

import sys
import os
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from life_mean_studio.prompts import Prompt
from life_mean_studio.prompts.collection import PromptCollection
from life_mean_studio.engine.storage import StudioStorage


class TestPrompt:
    """Test cases for Prompt."""
    
    def test_render_with_variables(self):
        """Test rendering a prompt with variables."""
        prompt = Prompt(
            name="Test",
            content="Hello {{name}}, welcome to {{place}}!",
            variables={"name": "World", "place": "Life_mean"}
        )
        
        rendered = prompt.render()
        assert "Hello World" in rendered
        assert "welcome to Life_mean" in rendered
    
    def test_render_with_overrides(self):
        """Test rendering with variable overrides."""
        prompt = Prompt(
            name="Test",
            content="Hello {{name}}",
            variables={"name": "World"}
        )
        
        rendered = prompt.render(overrides={"name": "Studio"})
        assert "Hello Studio" in rendered
    
    def test_render_without_variables(self):
        """Test rendering a prompt without variables."""
        prompt = Prompt(
            name="Test",
            content="Static content"
        )
        
        rendered = prompt.render()
        assert rendered == "Static content"
    
    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        original = Prompt(
            name="Test",
            content="Content",
            category="coding",
            variables={"key": "value"}
        )
        
        data = original.to_dict()
        restored = Prompt.from_dict(data)
        
        assert restored.name == original.name
        assert restored.category == "coding"
        assert restored.variables == original.variables


class TestPromptCollection:
    """Test cases for PromptCollection."""
    
    def setup_method(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.storage = StudioStorage(db_path=self.temp_db.name)
        self.collection = PromptCollection(self.storage)
    
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
    
    def test_create_prompt(self):
        """Test creating a prompt."""
        prompt_id = self.collection.create(
            name="Test Prompt",
            content="Hello {{name}}",
            category="coding",
            variables={"name": "World"}
        )
        
        assert prompt_id is not None
        
        prompt = self.collection.get(prompt_id)
        assert prompt is not None
        assert prompt.name == "Test Prompt"
    
    def test_list_prompts(self):
        """Test listing prompts."""
        self.collection.create("Prompt 1", "Content 1", "coding")
        self.collection.create("Prompt 2", "Content 2", "security")
        
        all_prompts = self.collection.list_all()
        assert len(all_prompts) == 2
        
        coding_prompts = self.collection.list_all(category="coding")
        assert len(coding_prompts) == 1
    
    def test_search_prompts(self):
        """Test searching prompts."""
        self.collection.create("Security Audit", "Check for security issues", "security")
        self.collection.create("Code Review", "Review the code", "coding")
        
        results = self.collection.search("security")
        assert len(results) == 1
        assert results[0].name == "Security Audit"
    
    def test_render_prompt(self):
        """Test rendering a stored prompt."""
        prompt_id = self.collection.create(
            name="Test",
            content="Hello {{name}}",
            variables={"name": "World"}
        )
        
        rendered = self.collection.render(prompt_id)
        assert "Hello World" in rendered
    
    def test_update_prompt(self):
        """Test updating a prompt."""
        prompt_id = self.collection.create(
            name="Original",
            content="Hello"
        )
        
        updated = self.collection.update(prompt_id, {"content": "Updated"})
        assert updated is True
        
        prompt = self.collection.get(prompt_id)
        assert prompt.content == "Updated"
        assert prompt.version == 2
    
    def test_delete_prompt(self):
        """Test deleting a prompt."""
        prompt_id = self.collection.create(
            name="To Delete",
            content="Content"
        )
        
        deleted = self.collection.delete(prompt_id)
        assert deleted is True
        
        assert self.collection.get(prompt_id) is None
    
    def test_seed_defaults(self):
        """Test seeding default prompts."""
        # Skip this test on Windows due to SQLite file locking issues
        import platform
        if platform.system() == "Windows":
            pytest.skip("Skipping seed_defaults on Windows due to SQLite file locking")
        
        self.collection.seed_defaults()
        
        prompts = self.collection.list_all()
        assert len(prompts) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
