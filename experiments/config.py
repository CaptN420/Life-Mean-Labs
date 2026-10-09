"""Experiment configuration for synthetic data generation.

Defines the ExperimentConfig dataclass for tracking experiment modes,
parameters, and reproducibility metadata.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass
class ExperimentConfig:
    """Configuration for a synthetic data generation experiment.

    Controls which components are enabled and tracks reproducibility metadata.
    """

    # Core modes
    deterministic: bool = True
    llm_reasoning: bool = False
    tools: bool = True
    thinkers: bool = False
    reflection: bool = False
    debate: bool = False
    diversification: bool = False

    # Generation parameters
    domain: str = "math"
    difficulty_range: Tuple[int, int] = (1, 5)
    num_tasks: int = 100
    seed: int = 42

    # Reproducibility
    generator_version: str = "1.0.0"
    prompt_version: str = "1.0.0"

    # Experiment tracking
    experiment_id: str = ""
    run_id: str = ""

    def __post_init__(self):
        """Validate and set defaults."""
        if not self.experiment_id:
            self.experiment_id = f"exp_{uuid.uuid4().hex[:8]}"
        if not self.run_id:
            self.run_id = f"run_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "deterministic": self.deterministic,
            "llm_reasoning": self.llm_reasoning,
            "tools": self.tools,
            "thinkers": self.thinkers,
            "reflection": self.reflection,
            "debate": self.debate,
            "diversification": self.diversification,
            "domain": self.domain,
            "difficulty_range": list(self.difficulty_range),
            "num_tasks": self.num_tasks,
            "seed": self.seed,
            "generator_version": self.generator_version,
            "prompt_version": self.prompt_version,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentConfig":
        """Deserialize from dictionary."""
        return cls(
            deterministic=data.get("deterministic", True),
            llm_reasoning=data.get("llm_reasoning", False),
            tools=data.get("tools", True),
            thinkers=data.get("thinkers", False),
            reflection=data.get("reflection", False),
            debate=data.get("debate", False),
            diversification=data.get("diversification", False),
            domain=data.get("domain", "math"),
            difficulty_range=tuple(data.get("difficulty_range", [1, 5])),
            num_tasks=data.get("num_tasks", 100),
            seed=data.get("seed", 42),
            generator_version=data.get("generator_version", "1.0.0"),
            prompt_version=data.get("prompt_version", "1.0.0"),
            experiment_id=data.get("experiment_id", ""),
            run_id=data.get("run_id", ""),
        )

    def mode_description(self) -> str:
        """Return human-readable description of the experiment mode."""
        modes = []
        if self.deterministic and not self.llm_reasoning:
            modes.append("DETERMINISTIC")
        elif not self.deterministic and self.llm_reasoning:
            modes.append("LLM_ONLY")
        elif self.deterministic and self.llm_reasoning:
            modes.append("HYBRID")
        else:
            modes.append("BASE")

        if self.thinkers:
            modes.append("THINKERS")
        if self.reflection:
            modes.append("REFLECTION")
        if self.debate:
            modes.append("DEBATE")
        if self.diversification:
            modes.append("DIVERSIFIED")

        return "+".join(modes)


# Predefined experiment modes for easy comparison
EXPERIMENT_MODES = {
    "A": ExperimentConfig(deterministic=True, llm_reasoning=False),
    "B": ExperimentConfig(deterministic=False, llm_reasoning=True),
    "C": ExperimentConfig(deterministic=True, llm_reasoning=True),
    "D": ExperimentConfig(thinkers=True, reflection=True, debate=True),
    "E": ExperimentConfig(diversification=True),
}


def get_experiment_mode(mode: str) -> ExperimentConfig:
    """Get a predefined experiment mode by name."""
    return EXPERIMENT_MODES.get(mode, ExperimentConfig())
