"""Experiment context and provenance tracking.

Defines ExperimentContext for tracking experiment metadata,
generation provenance, and traceability chains.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExperimentContext:
    """Context for a synthetic data generation experiment.

    Tracks experiment metadata, generation provenance, and traceability.
    Every dataset example should be traceable through this context.
    """

    # Core identifiers
    experiment_id: str = field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:8]}")
    generation_id: str = field(default_factory=lambda: f"gen_{uuid.uuid4().hex[:8]}")
    dataset_id: Optional[str] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None

    # Generation provenance
    generated: bool = True
    generator_version: str = "1.0.0"
    generator_strategy: str = "template"  # template, mutation, adversarial
    seed: int = 42

    # Execution configuration (mirrors ExperimentConfig)
    deterministic_enabled: bool = True
    llm_enabled: bool = False
    tools_enabled: bool = True
    thinker_enabled: bool = False
    reflection_enabled: bool = False
    debate_enabled: bool = False
    diversification_enabled: bool = False

    # Task metadata
    domain: str = "math"
    difficulty: int = 3

    # Runtime tracking
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update(self, **kwargs: Any) -> None:
        """Update context fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "generation_id": self.generation_id,
            "dataset_id": self.dataset_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "generated": self.generated,
            "generator_version": self.generator_version,
            "generator_strategy": self.generator_strategy,
            "seed": self.seed,
            "deterministic_enabled": self.deterministic_enabled,
            "llm_enabled": self.llm_enabled,
            "tools_enabled": self.tools_enabled,
            "thinker_enabled": self.thinker_enabled,
            "reflection_enabled": self.reflection_enabled,
            "debate_enabled": self.debate_enabled,
            "diversification_enabled": self.diversification_enabled,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentContext":
        """Deserialize from dictionary."""
        return cls(
            experiment_id=data.get("experiment_id", f"exp_{uuid.uuid4().hex[:8]}"),
            generation_id=data.get("generation_id", f"gen_{uuid.uuid4().hex[:8]}"),
            dataset_id=data.get("dataset_id"),
            task_id=data.get("task_id"),
            run_id=data.get("run_id"),
            generated=data.get("generated", True),
            generator_version=data.get("generator_version", "1.0.0"),
            generator_strategy=data.get("generator_strategy", "template"),
            seed=data.get("seed", 42),
            deterministic_enabled=data.get("deterministic_enabled", True),
            llm_enabled=data.get("llm_enabled", False),
            tools_enabled=data.get("tools_enabled", True),
            thinker_enabled=data.get("thinker_enabled", False),
            reflection_enabled=data.get("reflection_enabled", False),
            debate_enabled=data.get("debate_enabled", False),
            diversification_enabled=data.get("diversification_enabled", False),
            domain=data.get("domain", "math"),
            difficulty=data.get("difficulty", 3),
            metadata=data.get("metadata", {}),
        )

    def create_child_context(self, task_id: str, run_id: Optional[str] = None) -> "ExperimentContext":
        """Create a child context for a specific task/run."""
        child = ExperimentContext(
            experiment_id=self.experiment_id,
            generation_id=self.generation_id,
            dataset_id=self.dataset_id,
            task_id=task_id,
            run_id=run_id or f"run_{uuid.uuid4().hex[:8]}",
            generator_version=self.generator_version,
            generator_strategy=self.generator_strategy,
            seed=self.seed,
            deterministic_enabled=self.deterministic_enabled,
            llm_enabled=self.llm_enabled,
            tools_enabled=self.tools_enabled,
            thinker_enabled=self.thinker_enabled,
            reflection_enabled=self.reflection_enabled,
            debate_enabled=self.debate_enabled,
            diversification_enabled=self.diversification_enabled,
            domain=self.domain,
            difficulty=self.difficulty,
            metadata={**self.metadata, "parent_generation_id": self.generation_id},
        )
        return child


@dataclass
class ProvenanceChain:
    """Complete traceability chain from dataset example to origin.

    Every dataset example should be traceable:
    Dataset Example -> Run -> Task -> Generator configuration -> Router decision -> Workers -> Tools -> Thinker/Reflection/Debate -> Validation evidence
    """

    experiment_id: str
    generation_id: str
    task_id: str
    run_id: str
    dataset_id: Optional[str] = None
    generator_version: str = "1.0.0"
    generator_strategy: str = "template"
    seed: int = 42
    routing_decision: Optional[Dict[str, Any]] = None
    workers_used: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    thinker_used: bool = False
    reflection_used: bool = False
    debate_used: bool = False
    validation_result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "generation_id": self.generation_id,
            "dataset_id": self.dataset_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "generator_version": self.generator_version,
            "generator_strategy": self.generator_strategy,
            "seed": self.seed,
            "routing_decision": self.routing_decision,
            "workers_used": self.workers_used,
            "tools_used": self.tools_used,
            "thinker_used": self.thinker_used,
            "reflection_used": self.reflection_used,
            "debate_used": self.debate_used,
            "validation_result": self.validation_result,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProvenanceChain":
        """Deserialize from dictionary."""
        return cls(
            experiment_id=data.get("experiment_id", ""),
            generation_id=data.get("generation_id", ""),
            dataset_id=data.get("dataset_id"),
            task_id=data.get("task_id", ""),
            run_id=data.get("run_id", ""),
            generator_version=data.get("generator_version", "1.0.0"),
            generator_strategy=data.get("generator_strategy", "template"),
            seed=data.get("seed", 42),
            routing_decision=data.get("routing_decision"),
            workers_used=data.get("workers_used", []),
            tools_used=data.get("tools_used", []),
            thinker_used=data.get("thinker_used", False),
            reflection_used=data.get("reflection_used", False),
            debate_used=data.get("debate_used", False),
            validation_result=data.get("validation_result"),
        )
