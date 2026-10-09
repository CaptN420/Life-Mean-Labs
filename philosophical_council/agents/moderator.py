"""Moderator agent."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .base_agent import AgentConfig, BaseAgent

logger = logging.getLogger(__name__)


class ModeratorAgent(BaseAgent):
    """Agent that manages the debate flow."""

    def __init__(self, model: str = "") -> None:
        config = AgentConfig(
            role="moderator",
            name="Moderator",
            system_prompt="""You are the Moderator of a philosophical council debate.

Your role is to ensure intellectual quality, not to participate as a philosopher.

Your responsibilities:
1. Read the recent debate context and memory
2. Identify unresolved questions and contradictions
3. Detect repetition and prevent circular arguments
4. Select the next speaker strategically (do NOT simply rotate)
5. Give that speaker a specific philosophical challenge
6. Explain your reasoning
7. Occasionally introduce a deeper sub-question
8. Push the discussion to a deeper level when appropriate
9. Recognize when topics have been sufficiently explored and pivot
10. Advance the debate through phases: exploration → destruction → saturation → construction

Selection criteria:
- Choose the speaker best positioned to advance the discussion
- Break deadlocks by having someone address the strongest counterargument
- When agreement emerges, ask the Skeptic to challenge it
- When arguments repeat, ask someone to reframe the question
- Push toward deeper questions naturally
- NEVER let one agent dominate (max 2 consecutive turns)
- PREFER speakers who haven't spoken recently
- Consider which agent can best respond to the strongest objection

IMPORTANT: Return ONLY a valid JSON object. No other text, no explanations, no markdown.

Required fields:
- selected_speaker: One of: Existentialist, Stoic, Nihilist, Spiritual, Skeptic, Pragmatist
- challenge: A specific philosophical challenge (at least 50 characters) that directly addresses the last argument
- reason: Why this choice was made, mentioning who should respond and why
- question: Optional deeper question to explore (can be null)
- detected_issues: Any contradictions, repetitions, or logical gaps detected

Example response showing direct engagement with previous arguments:
{"selected_speaker": "Skeptic", "challenge": "The Pragmatist just claimed that meaning comes from practical consequences. But how do we test which consequences are 'practical' without already assuming a theory of value? Your criterion seems circular.", "reason": "The Skeptic should challenge the Pragmatist's circular reasoning about practical consequences.", "question": "What standard do we use to judge whether consequences are valuable?", "detected_issues": "Circular reasoning in pragmatist's argument about practical consequences"}""",
            model=model,
            color="#FFD700",
        )
        super().__init__(config)

    def parse_decision(self, raw_response: str) -> dict[str, str]:
        """Parse the moderator's JSON response into a decision dict."""
        raw = raw_response.strip()

        logger.info("MODERATOR RAW RESPONSE: %r", raw[:500])

        # Try direct JSON parse first
        try:
            data = json.loads(raw)
            logger.info("MODERATOR PARSE: success=True (direct json.loads)")
            return self._validate_moderator_decision(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("MODERATOR PARSE: direct parse failed: %s", e)

        # Try to extract JSON from markdown code fences
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                logger.info("MODERATOR PARSE: success=True (extracted from code fence)")
                return self._validate_moderator_decision(data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("MODERATOR PARSE: extracted JSON invalid: %s", e)

        # Try to find JSON in the response by looking for common patterns
        patterns = [
            r'["\']selected_speaker["\']\s*:',  # JSON with quotes
            r'selected_speaker\s*:',  # JSON without quotes
        ]

        for pattern in patterns:
            match = re.search(pattern, raw)
            if match:
                # Try to extract from this position
                start = match.start()
                try:
                    # Find the opening brace
                    brace_start = raw.rfind('{', 0, start)
                    if brace_start >= 0:
                        # Find matching closing brace
                        depth = 0
                        for i in range(brace_start, len(raw)):
                            if raw[i] == '{':
                                depth += 1
                            elif raw[i] == '}':
                                depth -= 1
                                if depth == 0:
                                    json_str = raw[brace_start:i+1]
                                    try:
                                        data = json.loads(json_str)
                                        logger.info("MODERATOR PARSE: success=True (pattern match)")
                                        return self._validate_moderator_decision(data)
                                    except (json.JSONDecodeError, ValueError) as e:
                                        logger.warning("MODERATOR PARSE: pattern JSON invalid: %s", e)
                                    break
                except Exception as e:
                    logger.warning("MODERATOR PARSE: pattern extraction failed: %s", e)

        # Fallback - use a deterministic response based on actual debate context
        # NEVER use generic fallback phrases
        logger.error("MODERATOR PARSE: ALL ATTEMPTS FAILED. Using deterministic fallback.")
        return {
            "selected_speaker": "Pragmatist",  # Default for balance
            "challenge": "Please address the specific objection raised in the previous turn with a novel argument.",
            "reason": "Moderator recovery fallback - could not parse response.",
            "question": None,
            "detected_issues": "Malformed moderator response — recovered with deterministic fallback.",
        }

    def _validate_moderator_decision(self, data: dict[str, object]) -> dict[str, str]:
        """Ensure the decision has required fields."""
        # Check for required fields and add defaults if missing
        if "selected_speaker" not in data or not data["selected_speaker"]:
            data["selected_speaker"] = "Pragmatist"

        if "challenge" not in data or not data["challenge"]:
            data["challenge"] = "Please address the current debate topic with a fresh perspective."

        if "reason" not in data or not data["reason"]:
            data["reason"] = "Strategic selection to advance the discussion."

        # Add optional fields if missing
        if "question" not in data:
            data["question"] = None

        if "detected_issues" not in data:
            data["detected_issues"] = None

        # Ensure all values are strings
        return {k: str(v) if v is not None else "" for k, v in data.items()}
