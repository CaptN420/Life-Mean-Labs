"""Pydantic models for structured LLM output validation."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ModeratorDecision(BaseModel):
    """The moderator's structured decision for the next turn."""

    selected_speaker: str = Field(
        ...,
        description="Name of the agent selected to speak next (e.g. 'Skeptic').",
    )
    challenge: str = Field(
        ...,
        description="The specific philosophical challenge or question to pose.",
    )
    reason: str = Field(
        ...,
        description="Why this speaker was chosen and why now.",
    )
    question: Optional[str] = Field(
        None,
        description="An optional deeper philosophical question to explore.",
    )
    detected_issues: Optional[str] = Field(
        None,
        description="Any contradictions, repetitions, or fallacies detected.",
    )

    @classmethod
    def safe_parse(cls, raw: str) -> ModeratorDecision:
        """Best-effort parse with fallback."""
        import json
        import logging

        logger = logging.getLogger(__name__)
        raw = raw.strip()

        # Try direct JSON parse first
        try:
            data = json.loads(raw)
            return cls(**data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to extract JSON from markdown code fences
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return cls(**data)
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: construct a minimal valid decision
        logger.warning("Failed to parse moderator JSON: %r", raw[:200])
        return cls(
            selected_speaker="Skeptic",
            challenge=raw[:500] if raw else "Continue the discussion.",
            reason="Could not parse structured output; using raw text as challenge.",
            question=None,
            detected_issues="Malformed moderator response — recovered gracefully.",
        )


class MemoryConsolidationResult(BaseModel):
    """Result of consolidating a section of debate into mid-term memory."""

    period: str = Field(..., description="Turn range this summary covers.")
    main_arguments: list[str] = Field(default_factory=list)
    counter_arguments: list[str] = Field(default_factory=list)
    agreements: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    important_questions: list[str] = Field(default_factory=list)
    position_changes: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)

    @classmethod
    def safe_parse(cls, raw: str) -> MemoryConsolidationResult:
        """Best-effort parse with fallback."""
        import json
        import logging

        logger = logging.getLogger(__name__)
        raw = raw.strip()

        try:
            data = json.loads(raw)
            return cls(**data)
        except (json.JSONDecodeError, ValueError):
            pass

        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return cls(**data)
            except (json.JSONDecodeError, ValueError):
                pass

        logger.warning("Failed to parse memory consolidation JSON: %r", raw[:200])
        return cls(period=raw[:100] if raw else "unknown")


class LongTermMemoryEntry(BaseModel):
    """A single entry in long-term memory."""

    key: str = Field(..., description="Unique identifier for this memory.")
    category: Optional[str] = Field(None, description="Category: argument, contradiction, question, etc.")
    content: str = Field(..., description="The memory content.")
