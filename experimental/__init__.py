"""Experimental Engine + Experiment Designer (sandbox).

Composition layer over the EXISTING stable core. Core rule:

    Design -> human review -> freeze -> execute -> RAW -> compare

The LLM may propose an experiment; it can never silently start or change it.
This package holds schema, validation, stage dispatch, the designer and the
engine facade — it does NOT reimplement CodeLabEngine, DebateEngine, ToolWorker,
EventBus, SmartRouter, the LLM client or Settings.
"""

from experimental.schema import (
    DESIGN_STATES,
    DesignAgent,
    DesignBudgets,
    DesignStage,
    DesignStateError,
    ExperimentDesign,
)
from experimental.dispatch import (
    EXECUTOR_NOT_AVAILABLE,
    ExecutorNotAvailable,
    dispatch_stage,
    executor_catalog,
)
from experimental.validation import DesignInvalid, require_executable, validate_design
from experimental.designer import (
    DesignerInputError,
    ExperimentDesigner,
    inspect_capabilities,
)
from experimental.engine import ExperimentalEngine, StopRequested
from experimental.executors import build_engine
from experimental.store import ExperimentDesignStore
from experimental.api import ExperimentalApiMixin
from experimental.prompts import compose_system_prompt, prompt_hash

__all__ = [
    "DESIGN_STATES", "DesignAgent", "DesignBudgets", "DesignStage", "DesignStateError",
    "ExperimentDesign", "EXECUTOR_NOT_AVAILABLE", "ExecutorNotAvailable",
    "dispatch_stage", "executor_catalog", "DesignInvalid", "require_executable",
    "validate_design", "DesignerInputError", "ExperimentDesigner", "inspect_capabilities",
    "ExperimentalEngine", "StopRequested", "compose_system_prompt", "prompt_hash",
    "build_engine", "ExperimentDesignStore", "ExperimentalApiMixin",
]
