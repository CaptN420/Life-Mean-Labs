"""Tests for personas — deterministic knowledge workers.

Phase 3: Personas & Roles
Tests corpus loading, keyword matching, and synthesis.
"""

import pytest


def test_aristotle_loads():
    """Test that Aristotle thinker loads its corpus."""
    from library.personas.philosophy import AristotleThinker
    thinker = AristotleThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0
    assert thinker.corpus_file == "aristotle.txt"


def test_plato_loads():
    """Test that Plato thinker loads its corpus."""
    from library.personas.philosophy import PlatoThinker
    thinker = PlatoThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_socrates_loads():
    """Test that Socrates thinker loads its corpus."""
    from library.personas.philosophy import SocratesThinker
    thinker = SocratesThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_kant_loads():
    """Test that Kant thinker loads its corpus."""
    from library.personas.philosophy import KantThinker
    thinker = KantThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_einstein_loads():
    """Test that Einstein thinker loads its corpus."""
    from library.personas.science import EinsteinThinker
    thinker = EinsteinThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_newton_loads():
    """Test that Newton thinker loads its corpus."""
    from library.personas.science import NewtonThinker
    thinker = NewtonThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_aristotle_findings_topic():
    """Test Aristotle findings with topic filter."""
    from library.personas.philosophy import AristotleThinker
    thinker = AristotleThinker()
    results = thinker.findings("logic")
    assert len(results) > 0
    # Should match logic-related entries
    assert any("logic" in r["detail"].lower() or "logic" in r["source"].lower() for r in results)


def test_aristotle_findings_no_topic():
    """Test Aristotle findings without topic filter."""
    from library.personas.philosophy import AristotleThinker
    thinker = AristotleThinker()
    results = thinker.findings()
    assert len(results) > 0


def test_einstein_findings_topic():
    """Test Einstein findings with topic filter."""
    from library.personas.science import EinsteinThinker
    thinker = EinsteinThinker()
    results = thinker.findings("relativity")
    assert len(results) > 0


def test_synthesize_aristotle():
    """Test Aristotle synthesis output."""
    from library.personas.philosophy import AristotleThinker
    thinker = AristotleThinker()
    synth = thinker.synthesize("ethics")
    assert "Aristotle" in synth or "philosophy" in synth.lower()


def test_synthesize_einstein():
    """Test Einstein synthesis output."""
    from library.personas.science import EinsteinThinker
    thinker = EinsteinThinker()
    synth = thinker.synthesize("physics")
    assert "Einstein" in synth or "physics" in synth.lower()


def test_persona_registry():
    """Test the persona registry."""
    from library.personas import get_persona, list_personas, get_all_personas

    # Test listing personas
    all_domains = list_personas()
    assert "philosophy" in all_domains
    assert "physics" in all_domains

    # Test getting specific persona
    aristotle = get_persona("philosophy", "aristotle")
    assert aristotle is not None
    assert type(aristotle).__name__ == "AristotleThinker"

    # Test getting all personas
    all_personas = get_all_personas()
    assert len(all_personas) > 0


def test_persona_status():
    """Test persona status method."""
    from library.personas.philosophy import AristotleThinker
    thinker = AristotleThinker()
    status = thinker.status()
    assert status["thinker"] == "AristotleThinker"
    assert status["domain"] == "philosophy"
    assert status["available"] is True
    assert status["entries"] > 0


def test_confucius_loads():
    """Test that Confucius thinker loads its corpus."""
    from library.personas.philosophy import ConfuciusThinker
    thinker = ConfuciusThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_descartes_loads():
    """Test that Descartes thinker loads its corpus."""
    from library.personas.philosophy import DescartesThinker
    thinker = DescartesThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_nietzsche_loads():
    """Test that Nietzsche thinker loads its corpus."""
    from library.personas.philosophy import NietzscheThinker
    thinker = NietzscheThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_locke_loads():
    """Test that Locke thinker loads its corpus."""
    from library.personas.philosophy import LockeThinker
    thinker = LockeThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_turing_loads():
    """Test that Turing thinker loads its corpus."""
    from library.personas.science import TuringThinker
    thinker = TuringThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0


def test_pythagoras_loads():
    """Test that Pythagoras thinker loads its corpus."""
    from library.personas.science import PythagorasThinker
    thinker = PythagorasThinker()
    assert thinker.available is True
    assert len(thinker.entries) > 0
