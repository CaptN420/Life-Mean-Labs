"""Test the new argument tracking and debate state functionality."""

import sys
sys.path.insert(0, '.')

from philosophical_council.memory.argument_tracker import DebateState as ArgumentDebateState


def test_argument_tracking():
    """Test that argument tracking works correctly."""
    state = ArgumentDebateState(topic="What is the meaning of life?")

    # Add some turns
    state.add_turn(1, "Pragmatist", "Meaning comes from practical consequences and what works in practice.", "claim")
    state.add_turn(2, "Skeptic", "But how do we determine which consequences are 'practical' without circular reasoning?", "objection")
    state.add_turn(3, "Pragmatist", "We test them empirically through lived experience.", "claim")
    state.add_turn(4, "Stoic", "Your empirical test assumes a theory of value that you haven't justified.", "objection")

    # Check speaker distribution
    assert state.speaker_turn_count["Pragmatist"] == 2
    assert state.speaker_turn_count["Skeptic"] == 1
    assert state.speaker_turn_count["Stoic"] == 1

    # Deterministic contract of the CURRENT prevention logic (not brittle/order-
    # or PYTHONHASHSEED-dependent): Stoic spoke most recently and turn_count>3,
    # so the consecutive-speaker guard EXCLUDES it; Pragmatist (2 turns) and the
    # never-spoken speakers remain eligible.
    alternatives = state.get_alternatives()
    assert "Stoic" not in alternatives, \
        "Stoic spoke last with turn_count>3 — must be prevented as consecutive"
    assert "Pragmatist" in alternatives
    # Highest relevance goes to a never-spoken speaker (never-spoken bonus 3.0).
    spoken = {"Pragmatist", "Skeptic", "Stoic"}
    assert alternatives and alternatives[0] not in spoken
    assert set(alternatives) >= {"Pragmatist", "Skeptic"}


def test_repetition_prevention():
    """Test that repetition is detected and penalized."""
    state = ArgumentDebateState(topic="Test topic")

    # Same speaker multiple times
    for i in range(5):
        state.add_turn(i, "Pragmatist", f"Argument {i}: meaning is subjective.", "claim")

    # Check that Pragmatist has high penalty
    penalty = state.get_repetition_penalty("Pragmatist")
    print(f"Repetition penalty for Pragmatist: {penalty}")
    assert penalty > 0, "Should have positive penalty for repetition"

    # New speaker should have low penalty
    new_penalty = state.get_repetition_penalty("Stoic")
    print(f"Repetition penalty for Stoic: {new_penalty}")
    assert new_penalty == 0, "New speaker should have no penalty"

    print("✓ Repetition prevention test passed")


def test_alternative_selection():
    """Test that alternatives are selected correctly."""
    state = ArgumentDebateState(topic="Test topic")

    # Add turns from different speakers
    state.add_turn(1, "Pragmatist", "Meaning is subjective.", "claim")
    state.add_turn(2, "Pragmatist", "I agree with my previous point.", "agreement")
    state.add_turn(3, "Skeptic", "But that creates a problem.", "objection")

    # Get alternatives excluding Pragmatist (who just spoke)
    alternatives = state.get_alternatives(exclude="Pragmatist")
    print(f"Alternatives (excluding Pragmatist): {alternatives}")

    # Pragmatist should not be in the list
    assert "Pragmatist" not in alternatives

    # Should have other speakers
    assert len(alternatives) > 0

    print("✓ Alternative selection test passed")


def test_should_prevent_is_probe_order_independent():
    """Regression: should_prevent_speaker() must not mutate state.

    A defaultdict read via ``speaker_turn_count[speaker]`` CREATES a key for a
    never-spoken speaker, so probing (e.g. iterating VALID_SPEAKERS) inflated
    len(speaker_turn_count), drifted `avg = turn_count/len(...)`, and flipped
    the verdict purely by evaluation/hash order. Reading via .get() fixes the
    nondeterminism and leaves the state unchanged.
    """
    from philosophical_council.memory.argument_tracker import DebateState as S

    def build(probe_order):
        st = S(topic="t")
        st.add_turn(1, "Pragmatist", "a", "claim")
        st.add_turn(2, "Skeptic", "b", "objection")
        st.add_turn(3, "Pragmatist", "c", "claim")
        st.add_turn(4, "Stoic", "d", "objection")
        for sp in probe_order:
            st.should_prevent_speaker(sp)  # probe must not mutate
        return st.should_prevent_speaker("Pragmatist")

    r1 = build(["Nihilist", "Existentialist", "Spiritual"])
    r2 = build(["Stoic", "Skeptic"])
    assert r1 == r2 == False  # noqa: E712 verdict identical, no matter what was probed

    # state is not mutated by probing a never-spoken speaker
    st = S(topic="t")
    st.add_turn(1, "Pragmatist", "a", "claim")
    before = dict(st.speaker_turn_count)
    st.should_prevent_speaker("Nihilist")
    assert dict(st.speaker_turn_count) == before
    assert len(st.speaker_turn_count) == 1


if __name__ == "__main__":
    test_argument_tracking()
    test_repetition_prevention()
    test_alternative_selection()
    test_should_prevent_is_probe_order_independent()
    print("\n✅ All tests passed!")