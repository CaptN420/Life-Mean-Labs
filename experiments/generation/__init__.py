"""Synthetic task generation infrastructure.

Provides task schemas, generators, and mutation utilities for
creating synthetic training data.
"""

from .schemas import GeneratedTask, TaskSchema
from .task_generator import TaskGenerator

__all__ = ["GeneratedTask", "TaskSchema", "TaskGenerator"]
