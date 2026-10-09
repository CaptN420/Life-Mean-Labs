"""Philosophy personas — deterministic knowledge workers.

Each subclass points to a corpus .txt file in library/personas/data/.
Adapted from Mia_Brain (captn/thinkers/philosophy/).
"""

from __future__ import annotations

from library.personas.base import CorpusThinker


class AristotleThinker(CorpusThinker):
    """Aristotle — logic, ethics, politics, biology."""
    corpus_file = "aristotle.txt"
    domain = "philosophy"


class PlatoThinker(CorpusThinker):
    """Plato — theory of forms, the Republic, academy."""
    corpus_file = "plato.txt"
    domain = "philosophy"


class SocratesThinker(CorpusThinker):
    """Socrates — dialectic method, ethical inquiry."""
    corpus_file = "socrates.txt"
    domain = "philosophy"


class KantThinker(CorpusThinker):
    """Immanuel Kant — categorical imperative, critical philosophy."""
    corpus_file = "immanuel_kant.txt"
    domain = "philosophy"


class DescartesThinker(CorpusThinker):
    """René Descartes — methodic doubt, cogito, rationalism."""
    corpus_file = "rene_descartes.txt"
    domain = "philosophy"


class NietzscheThinker(CorpusThinker):
    """Friedrich Nietzsche — will to power, eternal return, perspectivism."""
    corpus_file = "friedrich_nietzsche.txt"
    domain = "philosophy"


class LockeThinker(CorpusThinker):
    """John Locke — empiricism, tabula rasa, social contract."""
    corpus_file = "john_locke.txt"
    domain = "philosophy"


class ConfuciusThinker(CorpusThinker):
    """Confucius — ren, li, filial piety, meritocracy."""
    corpus_file = "confucius.txt"
    domain = "philosophy"


# Aggregate thinker for all philosophers
class PhilosophersThinker(CorpusThinker):
    """Aggregate knowledge from multiple philosophical traditions."""
    corpus_file = "philosophers.txt"
    domain = "philosophy"
