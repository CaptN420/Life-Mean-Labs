"""
Workflow Manager — Handles workflow persistence and validation.

This module provides the interface for managing workflows in Studio storage.
It does NOT execute workflows — it only manages their configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from . import WorkflowConfig, DEFAULT_WORKFLOWS
from ..engine.storage import StudioStorage

logger = logging.getLogger("LifeMean.Studio.Workflows")


class WorkflowManager:
    """
    Manages workflow configurations in Studio storage.
    
    Usage:
        storage = StudioStorage()
        manager = WorkflowManager(storage)
        
        # Create a workflow
        config = WorkflowConfig(name="test", mode="single")
        workflow_id = manager.create(config)
        
        # List workflows
        workflows = manager.list_all()
        
        # Get a workflow
        config = manager.get(workflow_id)
    """
    
    def __init__(self, storage: StudioStorage):
        self.storage = storage
    
    def create(self, config: WorkflowConfig) -> str:
        """
        Create and persist a workflow.
        
        Args:
            config: Workflow configuration
            
        Returns:
            Workflow ID
            
        Raises:
            ValueError: If validation fails
        """
        errors = config.validate()
        if errors:
            raise ValueError(f"Invalid workflow config: {', '.join(errors)}")
        
        return self.storage.create_workflow(
            name=config.name,
            config=config.to_dict(),
            description=config.description,
        )
    
    def get(self, workflow_id: str) -> Optional[WorkflowConfig]:
        """Get a workflow configuration by ID."""
        data = self.storage.get_workflow(workflow_id)
        if not data:
            return None
        return WorkflowConfig.from_dict(data["config"])
    
    def list_all(self) -> List[Dict[str, Any]]:
        """List all workflows with their configs."""
        return self.storage.list_workflows()
    
    def update(self, workflow_id: str, updates: Dict[str, Any]) -> bool:
        """Update a workflow configuration."""
        # Validate updates if config is being changed
        if "config" in updates:
            current = self.get(workflow_id)
            if current:
                merged = current.to_dict()
                merged.update(updates["config"])
                updated_config = WorkflowConfig.from_dict(merged)
                errors = updated_config.validate()
                if errors:
                    raise ValueError(f"Invalid workflow config: {', '.join(errors)}")
        
        return self.storage.update_workflow(workflow_id, updates)
    
    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow."""
        return self.storage.delete_workflow(workflow_id)
    
    def get_default(self, template_name: str) -> Optional[WorkflowConfig]:
        """Get a default workflow template by name."""
        template = DEFAULT_WORKFLOWS.get(template_name)
        if template:
            # Validate before returning
            errors = template.validate()
            if not errors:
                return template
            logger.warning("Default template '%s' has validation errors: %s", template_name, errors)
        return None
    
    def seed_defaults(self):
        """Seed the database with default workflow templates."""
        for name, config in DEFAULT_WORKFLOWS.items():
            # Check if already exists
            existing = self.storage.list_workflows()
            if not any(w["name"] == config.name for w in existing):
                self.create(config)
                logger.info("Seeded default workflow: %s", name)
