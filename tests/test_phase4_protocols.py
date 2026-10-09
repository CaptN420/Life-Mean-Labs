"""Tests for protocols — deterministic debate and reflection mechanisms.

Phase 4: Protocols (Debate)
Tests mirror transformations, stagnation detection, and integration.
"""

import pytest


def test_reflection_protocol_initialization():
    """Test that ReflectionProtocol initializes correctly."""
    from library.protocols.reflection import ReflectionProtocol
    protocol = ReflectionProtocol()
    assert protocol.initialize() is True
    assert protocol.name == "reflection_protocol"


def test_reflect_hypothesis():
    """Test basic hypothesis mirroring."""
    from library.protocols.reflection import reflect
    result = reflect("The meaning of life is 42", task_id="test")

    assert result["status"] == "success"
    assert result["original_hypothesis"] == "The meaning of life is 42"
    assert "mirrored_reasoning" in result
    assert "mirror_score" in result


def test_reflect_reversed_assumption():
    """Test that mirrored reasoning includes reversed assumption."""
    from library.protocols.reflection import reflect
    result = reflect("All humans are mortal")

    mirrored = result["mirrored_reasoning"]
    assert "reversed_assumption" in mirrored
    assert "Reversed:" in mirrored["reversed_assumption"]


def test_reflect_validation():
    """Test that mirror operation is validated."""
    from library.protocols.reflection import reflect
    result = reflect("Test hypothesis")

    validation = result["validation_result"]
    assert validation["is_valid"] is True
    assert validation["status"] == "experimental"


def test_reflect_score_components():
    """Test that mirror score has all components."""
    from library.protocols.reflection import reflect
    result = reflect("Test hypothesis")

    score = result["mirror_score"]
    assert "mirror_score" in score
    assert "novelty" in score
    assert "consistency" in score
    assert "contradiction_detected" in score
    assert "evidence_support" in score


def test_reflect_convenience_function():
    """Test the convenience reflect() function."""
    from library.protocols import reflect
    result = reflect("Convenience function test")
    assert result["status"] == "success"


def test_stagnation_detector_initialization():
    """Test that StagnationDetector initializes correctly."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()
    assert detector is not None


def test_stagnation_detector_add_turn():
    """Test adding turns to stagnation detection."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()

    result = detector.add_turn("Existentialist", "Life has no meaning", turn_id=1)
    assert "stagnation_detected" in result
    assert "indicators" in result


def test_stagnation_detector_consecutive_repetition():
    """Test detection of consecutive repetition."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()

    # Add three turns from same speaker to trigger repetition
    detector.add_turn("Stoic", "We must accept fate", turn_id=1)
    detector.add_turn("Stoic", "Again, we must accept fate", turn_id=2)
    result = detector.add_turn("Stoic", "And again, fate is all", turn_id=3)

    # Should detect stagnation
    assert result["stagnation_detected"] is True
    assert any(i["type"] == "consecutive_repetition" for i in result["indicators"])


def test_stagnation_detector_short_response():
    """Test detection of short responses."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()

    result = detector.add_turn("Skeptic", "Idk", turn_id=1)
    assert any(i["type"] == "short_response" for i in result["indicators"])


def test_stagnation_detector_vague_language():
    """Test detection of vague language."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()

    result = detector.add_turn("Nihilist", "Maybe life is perhaps meaningless", turn_id=1)
    assert any(i["type"] == "vague_language" for i in result["indicators"])


def test_stagnation_detector_status():
    """Test stagnation detection status."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()

    status = detector.status()
    assert "total_turns" in status
    assert "consecutive_duplicates" in status
    assert "stagnation_risk" in status


def test_stagnation_detector_alternatives():
    """Test getting alternative speakers."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()

    alternatives = detector.get_alternatives(exclude="Stoic")
    assert "Stoic" not in alternatives
    assert len(alternatives) > 0


def test_reflection_and_stagnation_integration():
    """Test integration between reflection and stagnation detection."""
    from library.protocols.reflection import ReflectionProtocol
    from library.protocols.stagnation import StagnationDetector

    protocol = ReflectionProtocol()
    detector = StagnationDetector()

    # Run reflection on a hypothesis
    result = protocol.process_hypothesis("The universe is deterministic")

    # Check that the mirrored reasoning can be analyzed
    assert result["status"] == "success"
    assert len(result["mirrored_reasoning"]) > 0


def test_reflect_long_hypothesis():
    """Test reflecting on a longer hypothesis."""
    from library.protocols.reflection import reflect
    long_hypothesis = "The nature of consciousness remains one of the most puzzling questions in philosophy and neuroscience. While some argue that consciousness is an emergent property of complex computational systems, others maintain that it requires something fundamentally different — a 'hard problem' that cannot be solved by reductionist approaches alone."
    result = reflect(long_hypothesis)
    assert result["status"] == "success"
    assert result["original_hypothesis"] == long_hypothesis


def test_stagnation_multiple_speakers():
    """Test stagnation detection with multiple speakers."""
    from library.protocols.stagnation import StagnationDetector
    detector = StagnationDetector()

    # Simulate a debate with alternating speakers
    speakers = ["Existentialist", "Stoic", "Nihilist", "Stoic", "Stoic"]
    for i, speaker in enumerate(speakers):
        detector.add_turn(speaker, f"Response {i} from {speaker}", turn_id=i)

    status = detector.status()
    assert status["total_turns"] == 5
    assert status["consecutive_duplicates"] >= 1  # Two consecutive Stoic turns
