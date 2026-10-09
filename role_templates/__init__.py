"""Versioned Role Template system for Life_mean Lab.

Experimental layer ⇒ configures the EXISTING stable core (it never replaces
an engine/orchestrator/router/debate engine). Built-in templates: CODING_STANDARD,
PHILOSOPHICAL_DEBATE, GENERAL_REASONING.

Core invariant exported through the public API:

    MODEL != ROLE != PERSONA
    ROLE TEMPLATE CONFIGURES THE SYSTEM; IT DOES NOT REPLACE THE STABLE CORE.
"""

from .core import RoleSpec, RoleTemplate, RoleModelMapping
from .registry import RoleTemplateRegistry, get_registry
from .builtins import coding_standard, philosophical_debate, general_reasoning
from .executor import EXECUTOR_CAPABILITIES, dispatch_template, require_code_lab

__all__ = [
    "RoleSpec",
    "RoleTemplate",
    "RoleModelMapping",
    "RoleTemplateRegistry",
    "get_registry",
    "coding_standard",
    "philosophical_debate",
    "general_reasoning",
    "EXECUTOR_CAPABILITIES",
    "dispatch_template",
    "require_code_lab",
]
