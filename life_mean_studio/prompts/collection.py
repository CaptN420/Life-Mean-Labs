"""
Prompt Collection — CRUD operations for the local prompt library.

This module provides the interface for managing prompts in Studio storage.
It does NOT execute prompts or affect LLM behavior directly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from . import Prompt, DEFAULT_PROMPTS
from ..engine.storage import StudioStorage

logger = logging.getLogger("LifeMean.Studio.Prompts")


class PromptCollection:
    """
    Manages the local prompt collection.
    
    Usage:
        storage = StudioStorage()
        collection = PromptCollection(storage)
        
        # Create a prompt
        prompt_id = collection.create(
            name="My Prompt",
            content="Hello {{name}}",
            category="general",
            variables={"name": "World"}
        )
        
        # List prompts
        prompts = collection.list_all(category="coding")
        
        # Search prompts
        results = collection.search("security")
    """
    
    def __init__(self, storage: StudioStorage):
        self.storage = storage
    
    def create(self, name: str, content: str, category: str = "general",
               variables: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a new prompt.
        
        Args:
            name: Prompt name
            content: Prompt content (may contain {{variable}} placeholders)
            category: Prompt category
            variables: Default variable values
            
        Returns:
            Prompt ID
        """
        return self.storage.create_prompt(
            name=name,
            content=content,
            category=category,
            variables=variables,
        )
    
    def get(self, prompt_id: str) -> Optional[Prompt]:
        """Get a prompt by ID."""
        data = self.storage.get_prompt(prompt_id)
        if not data:
            return None
        return Prompt.from_dict(data)
    
    def list_all(self, category: Optional[str] = None) -> List[Prompt]:
        """List all prompts, optionally filtered by category."""
        rows = self.storage.list_prompts(category=category)
        return [Prompt.from_dict(row) for row in rows]
    
    def search(self, query: str, category: Optional[str] = None) -> List[Prompt]:
        """Search prompts by name or content."""
        rows = self.storage.search_prompts(query, category=category)
        return [Prompt.from_dict(row) for row in rows]
    
    def update(self, prompt_id: str, updates: Dict[str, Any]) -> bool:
        """Update a prompt."""
        return self.storage.update_prompt(prompt_id, updates)
    
    def delete(self, prompt_id: str) -> bool:
        """Delete a prompt."""
        return self.storage.delete_prompt(prompt_id)
    
    def render(self, prompt_id: str, overrides: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Render a prompt with variables substituted.
        
        Args:
            prompt_id: Prompt ID
            overrides: Additional variable values
            
        Returns:
            Rendered prompt string, or None if prompt not found
        """
        prompt = self.get(prompt_id)
        if not prompt:
            return None
        return prompt.render(overrides)
    
    def seed_defaults(self):
        """Seed the database with default prompts."""
        for category, prompts in DEFAULT_PROMPTS.items():
            for prompt in prompts:
                # Check if already exists
                existing = self.storage.list_prompts(category=category)
                if not any(p["name"] == prompt.name for p in existing):
                    self.create(
                        name=prompt.name,
                        content=prompt.content,
                        category=prompt.category,
                        variables=prompt.variables,
                    )
                    logger.info("Seeded default prompt: %s (%s)", prompt.name, category)
