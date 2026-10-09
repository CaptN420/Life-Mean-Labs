"""Base agent class for philosophical agents."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a philosophical agent."""

    role: str
    name: str
    system_prompt: str
    model: Optional[str] = None
    color: str = "#888888"


class BaseAgent:
    """Base class for all philosophical agents with argument tracking."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._response_history: list[str] = []
        self._arguments_expressed: list[dict[str, str]] = []
        """Tracks arguments expressed by this agent for repetition detection."""

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def role(self) -> str:
        return self.config.role

    @property
    def color(self) -> str:
        return self.config.color

    @property
    def system_prompt(self) -> str:
        return self.config.system_prompt

    def add_to_history(self, response: str) -> None:
        """Record a response for this agent."""
        self._response_history.append(response)
        
        # Extract and store key arguments for repetition detection
        self._extract_and_store_arguments(response)

    def _extract_and_store_arguments(self, response: str) -> None:
        """Extract key arguments from response and store them."""
        # Look for claim indicators
        claim_patterns = [
            r'I believe.*?(?:\.|$)',
            r'My position is.*?(?:\.|$)',
            r'The truth is.*?(?:\.|$)',
            r'Essentially,.*?(?:\.|$)',
            r'What I mean is.*?(?:\.|$)',
        ]
        
        for pattern in claim_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            for match in matches:
                cleaned = ' '.join(match.split())[:200]
                if cleaned and len(cleaned) > 20:
                    self._arguments_expressed.append({
                        'argument': cleaned,
                        'turn_id': len(self._response_history),
                        'timestamp': str(len(self._response_history))
                    })

    def has_repeated_argument(self, new_response: str) -> bool:
        """Check if the new response repeats previously expressed arguments."""
        # Extract key phrases from new response
        new_phrases = self._extract_key_phrases(new_response)
        
        for existing in self._arguments_expressed:
            existing_phrases = self._extract_key_phrases(existing['argument'])
            
            # Check for significant overlap
            overlap = len(set(new_phrases) & set(existing_phrases))
            if overlap >= 3:  # At least 3 matching key phrases
                return True
        
        return False

    def _extract_key_phrases(self, text: str) -> list[str]:
        """Extract key phrases from text for comparison."""
        # Simple extraction: sentences or significant clauses
        sentences = re.split(r'[.!?]+', text)
        phrases = []
        for sent in sentences:
            sent = ' '.join(sent.split())
            if len(sent) > 30 and len(sent) < 200:
                phrases.append(sent.lower().strip())
        return phrases

    def get_history(self) -> list[str]:
        return list(self._response_history)

    def format_response(self, challenge: str, context: str, 
                        previous_speaker: Optional[str] = None,
                        last_argument_summary: Optional[str] = None) -> str:
        """Format the prompt for this agent's response with improved context."""
        
        # Build speaker-specific context
        speaker_context = f"""RECENT DEBATE CONTEXT:

{context}

---

SPEAKER HISTORY:
You have previously expressed these positions:
"""
        
        if self._arguments_expressed:
            for i, expr in enumerate(self._arguments_expressed[-5:], 1):
                speaker_context += f"{i}. {expr['argument']}\n"
        else:
            speaker_context += "(No previous arguments expressed yet)\n"
        
        speaker_context += f"""

---

MODERATOR CHALLENGE:
{challenge}

---

RESPONSE INSTRUCTIONS:
1. FIRST: Identify which agent's argument you are responding to (if any)
2. SECOND: Acknowledge what was said before attempting to counter or build upon it
3. THIRD: Express your philosophical position clearly
4. FOURTH: If you agree with a previous point, state WHY you agree
5. FIFTH: If you disagree, explain SPECIFICALLY where the reasoning fails
6. SIXTH: Propose what comes next in the discussion

IMPORTANT: Do NOT simply restate arguments you've already made. 
If you have already expressed a position, either:
- Refine it based on new objections
- Defend it against specific counterarguments  
- Acknowledge its limitations
- Build upon it with new insights

Respond as {self.name}. Write your philosophical response now:"""
        
        return speaker_context

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"
