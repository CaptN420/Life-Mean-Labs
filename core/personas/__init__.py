"""Persona management system for LIFE_MEAN.

Provides unified persona creation, validation, and template inheritance.
"""

from .manager import PersonaManager, PersonaValidationError
from .network import PersonaNetwork, PersonaNode, RelationshipType, PersonaRelationship
from .schema import (
    DebateSessionConfig,
    ModelHealth,
    ModelSpec,
    PersonaConfig,
    PersonaType,
    ProviderType,
)

__all__ = [
    "PersonaManager",
    "PersonaValidationError",
    "PersonaNetwork",
    "PersonaNode",
    "RelationshipType",
    "PersonaRelationship",
    "DebateSessionConfig",
    "ModelHealth",
    "ModelSpec",
    "PersonaConfig",
    "PersonaType",
    "ProviderType",
]
