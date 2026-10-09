"""Personas registry — all deterministic thinkers.

Adapted from Mia_Brain (captn/thinkers/).
Provides a central registry for all persona classes.
"""

from __future__ import annotations

from typing import Dict, List, Type

from library.personas.base import CorpusThinker


# Philosophy personas
from library.personas.philosophy import (
    AristotleThinker,
    ConfuciusThinker,
    DescartesThinker,
    KantThinker,
    LockeThinker,
    NietzscheThinker,
    PhilosophersThinker,
    PlatoThinker,
    SocratesThinker,
)

# Science personas
from library.personas.science import (
    ChemistsThinker,
    DaVinciThinker,
    EinsteinThinker,
    MathematiciansThinker,
    NewtonThinker,
    PhysicistsThinker,
    PythagorasThinker,
    ScientistsThinker,
    TuringThinker,
)


# Central registry — maps domain → list of persona classes
PERSONAS: Dict[str, List[Type[CorpusThinker]]] = {
    "philosophy": [
        AristotleThinker,
        ConfuciusThinker,
        DescartesThinker,
        KantThinker,
        LockeThinker,
        NietzscheThinker,
        PhilosophersThinker,
        PlatoThinker,
        SocratesThinker,
    ],
    "physics": [
        EinsteinThinker,
        NewtonThinker,
        PhysicistsThinker,
    ],
    "chemistry": [
        ChemistsThinker,
    ],
    "mathematics": [
        PythagorasThinker,
        MathematiciansThinker,
    ],
    "computer_science": [
        TuringThinker,
    ],
    "polymath": [
        DaVinciThinker,
    ],
    "alchemy": [],  # placeholder for future alchemy personas
}


def get_persona(domain: str, persona_name: str = "") -> CorpusThinker | None:
    """Get a specific persona instance by domain and name.

    Args:
        domain: The domain to search (e.g., 'philosophy', 'physics')
        persona_name: Optional name filter (e.g., 'aristotle' → AristotleThinker)

    Returns:
        An instantiated CorpusThinker, or None if not found.
    """
    personas = PERSONAS.get(domain, [])
    if not personas:
        return None

    if persona_name:
        # Try to find matching persona by name (case-insensitive)
        for p in personas:
            if persona_name.lower() in p.__name__.lower():
                return p()
        return None

    # Return first available persona from domain
    for p in personas:
        instance = p()
        if instance.available:
            return instance

    return None


def list_personas(domain: str | None = None) -> Dict[str, List[str]]:
    """List all available personas by domain.

    Args:
        domain: Optional domain filter. If None, returns all domains.

    Returns:
        Dict mapping domain → list of persona names.
    """
    result = {}
    if domain:
        domains = [domain]
    else:
        domains = PERSONAS.keys()

    for dom in domains:
        personas = PERSONAS.get(dom, [])
        if personas:
            result[dom] = [p.__name__ for p in personas]

    return result


def get_all_personas() -> List[CorpusThinker]:
    """Get all available persona instances.

    Returns:
        List of instantiated CorpusThinkers that have data loaded.
    """
    all_personas = []
    for domain, personas in PERSONAS.items():
        for p in personas:
            instance = p()
            if instance.available:
                all_personas.append(instance)
    return all_personas
