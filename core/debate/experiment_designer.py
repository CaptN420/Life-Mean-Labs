"""Controlled Experiment Designer — designs minimal experiments to isolate variables.

For each hypothesis, proposes a controlled experiment that:
- Changes only one variable
- Keeps all other conditions constant
- Records measurements and success criteria
- Defines stopping conditions and max cost
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.experiment_designer")


# ── Enums ────────────────────────────────────────────────────────────────────


class ExperimentStatus(str, Enum):
    """Lifecycle status of an experiment."""
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class VariableType(str, Enum):
    """Type of variable in an experiment."""
    INDEPENDENT = "INDEPENDENT"      # The variable being changed
    CONTROLLED = "CONTROLLED"         # Variables kept constant
    MEASURED = "MEASURED"             # Outcomes being measured


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ExperimentVariable:
    """A variable in an experiment."""
    name: str
    type: VariableType
    value: Any
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "value": str(self.value)[:100],
            "description": self.description[:200],
        }


@dataclass
class ControlledExperiment:
    """A controlled experiment design."""
    experiment_id: str
    hypothesis_id: str
    description: str
    independent_variable: ExperimentVariable
    controlled_variables: List[ExperimentVariable] = field(default_factory=list)
    measured_variables: List[ExperimentVariable] = field(default_factory=list)
    success_criteria: str = ""
    stopping_conditions: List[str] = field(default_factory=list)
    max_repetitions: int = 3
    max_cost_estimate: str = "LOW"
    expected_if_true: str = ""
    expected_if_false: str = ""
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "description": self.description[:300],
            "independent_variable": self.independent_variable.to_dict(),
            "controlled_variables": [v.to_dict() for v in self.controlled_variables],
            "measured_variables": [v.to_dict() for v in self.measured_variables],
            "success_criteria": self.success_criteria,
            "stopping_conditions": self.stopping_conditions,
            "max_repetitions": self.max_repetitions,
            "max_cost_estimate": self.max_cost_estimate,
            "expected_if_true": self.expected_if_true[:200],
            "expected_if_false": self.expected_if_false[:200],
            "status": self.status.value,
            "timestamp": self.timestamp,
        }


# ── Controlled Experiment Designer ───────────────────────────────────────────


class ControlledExperimentDesigner:
    """Designs minimal controlled experiments to test hypotheses.

    Changes only one variable at a time.
    If multiple variables change simultaneously, declares inability to isolate cause.
    """

    def __init__(self):
        self._experiments: Dict[str, ControlledExperiment] = {}
        self._next_id = 1

    def design_experiment(
        self,
        hypothesis_id: str,
        description: str,
        independent_variable_name: str,
        independent_variable_value: Any,
        controlled_variables: Optional[List[Dict[str, Any]]] = None,
        success_criteria: str = "",
        max_repetitions: int = 3,
    ) -> ControlledExperiment:
        """Design a controlled experiment to test a hypothesis."""
        exp_id = f"EXP-{self._next_id:03d}"
        self._next_id += 1

        experiment = ControlledExperiment(
            experiment_id=exp_id,
            hypothesis_id=hypothesis_id,
            description=description,
            independent_variable=ExperimentVariable(
                name=independent_variable_name,
                type=VariableType.INDEPENDENT,
                value=independent_variable_value,
            ),
            controlled_variables=[
                ExperimentVariable(**v) for v in (controlled_variables or [])
            ],
            measured_variables=[],
            success_criteria=success_criteria,
            max_repetitions=max_repetitions,
        )

        self._experiments[exp_id] = experiment

        logger.info("Experiment designed: %s for hypothesis %s", exp_id, hypothesis_id)
        return experiment

    def get_experiment(self, experiment_id: str) -> Optional[ControlledExperiment]:
        """Get an experiment by ID."""
        return self._experiments.get(experiment_id)

    def get_experiments_for_hypothesis(
        self, hypothesis_id: str
    ) -> List[ControlledExperiment]:
        """Get all experiments for a hypothesis."""
        return [
            e for e in self._experiments.values()
            if e.hypothesis_id == hypothesis_id
        ]

    def propose_multiple_variable_change(
        self,
        variables: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Flag that multiple variables are changing simultaneously.

        Returns a warning indicating inability to isolate cause.
        """
        return {
            "warning": "Multiple variables changing simultaneously",
            "message": "Cannot isolate cause when multiple variables change",
            "variables": variables,
            "recommendation": "Design separate experiments for each variable",
        }
