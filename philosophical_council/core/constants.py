"""Shared constants for the debate system."""

from __future__ import annotations

# Valid speaker names that the moderator can select
VALID_SPEAKERS: set[str] = {
    "Existentialist",
    "Stoic",
    "Nihilist",
    "Spiritual",
    "Skeptic",
    "Pragmatist",
}

# Mapping from speaker names to agent roles
SPEAKER_TO_ROLE: dict[str, str] = {
    "Existentialist": "existentialist",
    "Stoic": "stoic",
    "Nihilist": "nihilist",
    "Spiritual": "spiritual",
    "Skeptic": "skeptic",
    "Pragmatist": "pragmatist",
}
