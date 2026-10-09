"""Task schemas for synthetic data generation.

Defines the GeneratedTask dataclass and related schemas.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskSchema:
    """Schema definition for a task type.

    Defines the structure, constraints, and validation rules for a task.
    """

    schema_id: str
    name: str
    domain: str  # math, physics, chemistry, coding, logic
    difficulty_range: tuple = (1, 5)
    reasoning_types: List[str] = field(default_factory=lambda: ["calculation"])
    constraints: List[str] = field(default_factory=list)
    required_fields: List[str] = field(default_factory=list)
    metadata_schema: Dict[str, Any] = field(default_factory=dict)

    def validate(self, task_dict: Dict[str, Any]) -> bool:
        """Validate a task dictionary against this schema."""
        for field_name in self.required_fields:
            if field_name not in task_dict:
                return False
        return True


@dataclass
class GeneratedTask:
    """A synthetically generated task with full provenance.

    Every generated task includes:
    - Unique identifier
    - Source tracking (generator vs benchmark)
    - Domain and difficulty metadata
    - Ground truth (computed deterministically)
    - Provenance metadata
    """

    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    source: str = "generator"  # "generator" or "benchmark"
    domain: str = "math"
    difficulty: int = 3
    reasoning_type: str = "calculation"
    description: str = ""
    constraints: List[str] = field(default_factory=list)
    expected_steps: int = 1
    ground_truth: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Provenance
    generator_version: str = "1.0.0"
    seed: int = 42
    generation_strategy: str = "template"  # template, mutation, adversarial

    # Runtime metadata (populated during execution)
    run_id: Optional[str] = None
    experiment_id: Optional[str] = None
    validation_result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "task_id": self.task_id,
            "source": self.source,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "reasoning_type": self.reasoning_type,
            "description": self.description,
            "constraints": self.constraints,
            "expected_steps": self.expected_steps,
            "ground_truth": self.ground_truth,
            "metadata": self.metadata,
            "generator_version": self.generator_version,
            "seed": self.seed,
            "generation_strategy": self.generation_strategy,
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "validation_result": self.validation_result,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratedTask":
        """Deserialize from dictionary."""
        return cls(
            task_id=data.get("task_id", f"task_{uuid.uuid4().hex[:8]}"),
            source=data.get("source", "generator"),
            domain=data.get("domain", "math"),
            difficulty=data.get("difficulty", 3),
            reasoning_type=data.get("reasoning_type", "calculation"),
            description=data.get("description", ""),
            constraints=data.get("constraints", []),
            expected_steps=data.get("expected_steps", 1),
            ground_truth=data.get("ground_truth"),
            metadata=data.get("metadata", {}),
            generator_version=data.get("generator_version", "1.0.0"),
            seed=data.get("seed", 42),
            generation_strategy=data.get("generation_strategy", "template"),
            run_id=data.get("run_id"),
            experiment_id=data.get("experiment_id"),
            validation_result=data.get("validation_result"),
        )

    def validate(self) -> bool:
        """Validate the task has required fields."""
        if not self.task_id:
            return False
        if not self.domain:
            return False
        if not self.description:
            return False
        if self.ground_truth is None and self.source == "generator":
            return False
        return True

    def copy(self) -> "GeneratedTask":
        """Create a shallow copy of this task."""
        return GeneratedTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            source=self.source,
            domain=self.domain,
            difficulty=self.difficulty,
            reasoning_type=self.reasoning_type,
            description=self.description,
            constraints=list(self.constraints),
            expected_steps=self.expected_steps,
            ground_truth=self.ground_truth,
            metadata=dict(self.metadata),
            generator_version=self.generator_version,
            seed=self.seed,
            generation_strategy=self.generation_strategy,
        )
