"""Science personas — deterministic knowledge workers.

Each subclass points to a corpus .txt file in library/personas/data/.
Adapted from Mia_Brain (captn/thinkers/science/).
"""

from __future__ import annotations

from library.personas.base import CorpusThinker


class EinsteinThinker(CorpusThinker):
    """Albert Einstein — relativity, quantum mechanics, photoelectric effect."""
    corpus_file = "albert_einstein.txt"
    domain = "physics"


class NewtonThinker(CorpusThinker):
    """Isaac Newton — laws of motion, universal gravitation, calculus."""
    corpus_file = "isaac_newton.txt"
    domain = "physics"


class CurieThinker(CorpusThinker):
    """Marie Curie — radioactivity, radium, polonium."""
    corpus_file = "marie_curie.txt"
    domain = "chemistry"


class PythagorasThinker(CorpusThinker):
    """Pythagoras — theorem, music theory, numerology."""
    corpus_file = "pythagoras.txt"
    domain = "mathematics"


class TuringThinker(CorpusThinker):
    """Alan Turing — computability, Enigma, AI test."""
    corpus_file = "alan_turing.txt"
    domain = "computer_science"


class DaVinciThinker(CorpusThinker):
    """Leonardo da Vinci — Renaissance polymath, anatomy, engineering."""
    corpus_file = "leonardo_da_vinci.txt"
    domain = "polymath"


# Aggregate thinkers
class ScientistsThinker(CorpusThinker):
    """Broad scientific knowledge (biology, chemistry, physics, etc.)."""
    corpus_file = "scientists.txt"
    domain = "science"


class PhysicistsThinker(CorpusThinker):
    """Physics-specific knowledge."""
    corpus_file = "physicists.txt"
    domain = "physics"


class ChemistsThinker(CorpusThinker):
    """Chemistry-specific knowledge."""
    corpus_file = "chemists.txt"
    domain = "chemistry"


class MathematiciansThinker(CorpusThinker):
    """Mathematics-specific knowledge."""
    corpus_file = "mathematicians.txt"
    domain = "mathematics"
