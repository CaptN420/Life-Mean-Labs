"""Moderator agent."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .base_agent import AgentConfig, BaseAgent

logger = logging.getLogger(__name__)


class ModeratorAgent(BaseAgent):
    """Agent that manages the debate flow.

    The set of selectable speakers is CONFIGURABLE per session
    (``allowed_speakers``) so the same ModeratorAgent serves both the
    historical philosophical template (six schools) and generic RoleTemplate
    debates (Moderator + Scientist + Skeptic, ...). The prompt never hardcodes
    a six-philosopher list; the session's actual participants are enumerated.
    """

    def __init__(self, model: str = "", allowed_speakers=None,
                 shared_context: str = "") -> None:
        allowed = list(allowed_speakers) if allowed_speakers else [
            "Existentialist", "Stoic", "Nihilist", "Spiritual", "Skeptic", "Pragmatist"]
        speakers_text = ", ".join(allowed)
        system_prompt = f"""You are the Moderator of a council debate.

Your role is to ensure intellectual quality, not to participate as a debater.

Your responsibilities:
1. Read the recent debate context and memory
2. Identify unresolved questions and contradictions
3. Detect repetition and prevent circular arguments
4. Select the next speaker strategically (do NOT simply rotate)
5. Give that speaker a specific challenge that advances the discussion
6. Explain your reasoning
7. Occasionally introduce a deeper sub-question
8. Push the discussion to a deeper level when appropriate
9. Recognize when topics have been sufficiently explored and pivot
10. Keep the debate moving through meaningful stages

Selection criteria:
- Choose the speaker best positioned to advance the discussion
- Break deadlocks by having someone address the strongest counterargument
- When agreement emerges, ask another participant to challenge it
- When arguments repeat, ask someone to reframe the question
- Push toward deeper questions naturally
- NEVER let one participant dominate (max 2 consecutive turns)
- PREFER participants who haven't spoken recently
- Consider which participant can best respond to the strongest objection

Registered participants for THIS session:
- {speakers_text}

IMPORTANT: Return ONLY a valid JSON object. No other text, no explanations, no markdown.

Required fields:
- selected_speaker: One of: {speakers_text}
- challenge: A specific challenge (at least 50 characters) that directly addresses the last argument
- reason: Why this choice was made, mentioning who should respond and why
- question: Optional deeper question to explore (can be null)
- detected_issues: Any contradictions, repetitions, or logical gaps detected

Example response showing direct engagement with previous arguments:
{{"selected_speaker": "{allowed[0]}", "challenge": "The previous speaker claimed a strong position, but an unexamined assumption remains that undercuts it. Address that assumption directly and show why it does or does not hold.", "reason": "The selected participant is best positioned to advance the discussion by addressing the unresolved objection.", "question": "What standard do we use to judge whether this claim holds?", "detected_issues": "Unaddressed assumption in the previous argument"}}"""
        if shared_context and shared_context.strip():
            system_prompt += "\n\n=== TEMPLATE SHARED CONTEXT ===\n" + shared_context.strip()

        config = AgentConfig(
            role="moderator",
            name="Moderator",
            system_prompt=system_prompt,
            model=model,
            color="#FFD700",
        )
        super().__init__(config)
        # Spec §6.G / §11: the session's admissible speakers (runtime authority
        # checks them; the engine validates against them too).
        self.allowed_speakers: list[str] = allowed
        # Spec §16: how the LAST decision was parsed. DEFAULTS to DIRECT_JSON;
        # set on every successful/failed branch so consumers can label the parse.
        self.last_parse_mode: str = "DIRECT_JSON"

    def parse_decision(self, raw_response: str) -> dict[str, str]:
        """Parse the moderator's JSON response into a decision dict.

        Records ``self.last_parse_mode`` so the engine can label each decision
        as DIRECT_JSON / EXTRACTED_JSON / PATTERN_FALLBACK (spec §16) — a
        recovered-by-pattern response is `PATTERN_FALLBACK``, not silently
        equal to perfect structured output.
        """
        raw = raw_response.strip()

        logger.info("MODERATOR RAW RESPONSE: %r", raw[:500])

        # Try direct JSON parse first
        try:
            data = json.loads(raw)
            self.last_parse_mode = "DIRECT_JSON"
            logger.info("MODERATOR PARSE: success=True (direct json.loads) | mode=DIRECT_JSON")
            return self._validate_moderator_decision(data)
        except (json.JSONDecodeError, ValueError) as e:
            self.last_parse_mode = "DIRECT_JSON_FAILED"
            logger.warning("MODERATOR PARSE: direct parse failed: %s", e)

        # Try to extract JSON from markdown code fences
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                self.last_parse_mode = "EXTRACTED_JSON"
                logger.info("MODERATOR PARSE: success=True (extracted from code fence) | mode=EXTRACTED_JSON")
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
                                        self.last_parse_mode = "PATTERN_FALLBACK"
                                        logger.info("MODERATOR PARSE: success=True (pattern match) | mode=PATTERN_FALLBACK")
                                        return self._validate_moderator_decision(data)
                                    except (json.JSONDecodeError, ValueError) as e:
                                        logger.warning("MODERATOR PARSE: pattern JSON invalid: %s", e)
                                    break
                except Exception as e:
                    logger.warning("MODERATOR PARSE: pattern extraction failed: %s", e)

        # Fallback - use a deterministic response based on actual debate context
        # NEVER use generic fallback phrases, and NEVER inject a specific
        # philosopher (e.g. "Pragmatist") just because parsing failed: an empty
        # selected_speaker is an INVALID/unknown speaker that the DebateEngine
        # rejects, forcing its explicit deterministic fallback over the
        # session's ACTUAL registered participants (spec §6.G).
        logger.error("MODERATOR PARSE: ALL ATTEMPTS FAILED. Using deterministic fallback.")
        self.last_parse_mode = "DETERMINISTIC_FALLBACK"
        return {
            "selected_speaker": "",  # invalid — engine applies session fallback
            "challenge": "Please address the specific objection raised in the previous turn with a novel argument.",
            "reason": "Moderator recovery fallback - could not parse response.",
            "question": None,
            "detected_issues": "Malformed moderator response — recovered with deterministic fallback.",
        }

    def _validate_moderator_decision(self, data: dict[str, object]) -> dict[str, str]:
        """Ensure the decision has required fields."""
        # Check for required fields and add defaults if missing. A missing
        # selected_speaker is left EMPTY (invalid) so the ENGINE decides who is
        # admissible from the session's actual participants — never a hardcoded
        # philosopher injected by the parser.
        if "selected_speaker" not in data or not data["selected_speaker"]:
            data["selected_speaker"] = ""

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
