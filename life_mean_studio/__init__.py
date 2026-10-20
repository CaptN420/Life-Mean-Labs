"""
Life_mean Studio — Python Foundations

This package provides the foundational layers for a future PySide6 launcher
and optional HTML dashboard. It does NOT modify existing Code Lab, Hermes,
or Pi components.

Architecture:
  - engine/   : Contracts and interfaces for the independent motor
  - launcher/ : Future PySide6 client (stub for now)
  - workflows/ : Workflow schemas and validation
  - prompts/   : Local prompt collection
  - tests/     : Unit tests for new components

Usage:
  from life_mean_studio.engine.storage import StudioStorage
  from life_mean_studio.workflows.schema import WorkflowConfig
  
  # Create storage
  storage = StudioStorage(db_path="life_mean_studio_data.db")
  
  # Work with workflows
  workflow = storage.create_workflow({
      "name": "test",
      "config": {"mode": "single"}
  })
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["engine", "launcher", "workflows", "prompts", "tests"]
