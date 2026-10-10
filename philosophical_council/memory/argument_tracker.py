"""Argument tracking for detecting repetition and building debate state."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Argument:
    """A structured argument extracted from a turn."""

    turn_id: int
    speaker: str
    content: str
    argument_type: str  # "claim", "objection", "question", "agreement", "revision"
    key_concepts: list[str] = field(default_factory=list)
    responds_to: Optional[str] = None  # speaker name being responded to


@dataclass
class DebateState:
    """Structured state of the debate for intelligent moderation."""

    topic: str = ""
    current_speaker: Optional[str] = None
    previous_speaker: Optional[str] = None

    # Argument tracking
    arguments: list[Argument] = field(default_factory=list)
    objections: list[Argument] = field(default_factory=list)
    agreements: list[Argument] = field(default_factory=list)
    revisions: list[Argument] = field(default_factory=list)  # position changes

    # Unresolved issues
    unresolved_questions: list[str] = field(default_factory=list)
    established_arguments: set[str] = field(default_factory=set)

    # Speaker stats
    speaker_turn_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    consecutive_speakers: list[str] = field(default_factory=list)

    # Turn tracking
    turn_count: int = 0

    def add_turn(self, turn_id: int, speaker: str, response: str,
                 argument_type: str = "claim", responds_to: Optional[str] = None) -> None:
        """Record a turn and extract argument information."""
        self.turn_count += 1
        self.previous_speaker = self.current_speaker
        self.current_speaker = speaker

        # Update speaker stats
        self.speaker_turn_count[speaker] += 1

        # Track consecutive speakers
        if self.consecutive_speakers and self.consecutive_speakers[-1] == speaker:
            pass  # Already consecutive
        else:
            self.consecutive_speakers.append(speaker)

        # Extract key concepts from response
        concepts = self._extract_concepts(response)

        # Create argument entry
        arg = Argument(
            turn_id=turn_id,
            speaker=speaker,
            content=response[:500],  # Truncate for storage
            argument_type=argument_type,
            key_concepts=concepts,
            responds_to=responds_to,
        )

        self.arguments.append(arg)

        # Categorize
        if argument_type == "objection":
            self.objections.append(arg)
        elif argument_type == "agreement":
            self.agreements.append(arg)
        elif argument_type == "revision":
            self.revisions.append(arg)

        # Mark as established after 2+ turns
        if len([a for a in self.arguments if a.key_concepts == concepts and a.speaker == speaker]) >= 2:
            self.established_arguments.add(tuple(concepts))

    def _extract_concepts(self, text: str) -> list[str]:
        """Extract key concepts from argument text."""
        # Simple extraction: look for repeated significant words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'can', 'shall',
                      'to', 'of', 'for', 'in', 'on', 'at', 'by', 'with', 'from',
                      'and', 'or', 'but', 'not', 'no', 'if', 'then', 'than', 'that',
                      'this', 'it', 'its', 'i', 'me', 'my', 'we', 'our', 'you',
                      'your', 'he', 'him', 'his', 'she', 'her', 'they', 'them',
                      'their', 'which', 'what', 'who', 'whom'}

        # Remove punctuation and split
        words = re.findall(r'\b[a-zA-Zà-ÿ]+\b', text.lower())
        concepts = [w for w in words if len(w) > 3 and w not in stop_words]

        # Return most frequent as key concepts
        from collections import Counter
        freq = Counter(concepts)
        return [word for word, _ in freq.most_common(10)]

    def get_repetition_penalty(self, speaker: str) -> float:
        """Calculate penalty for selecting a speaker again."""
        count = self.speaker_turn_count.get(speaker, 0)

        # Base penalty for multiple turns
        penalty = count * 0.5

        # Extra penalty for consecutive turns
        if self.consecutive_speakers and self.consecutive_speakers[-1] == speaker:
            penalty += 2.0

        # Penalty for established arguments being repeated
        established_count = sum(1 for arg in self.arguments
                               if arg.speaker == speaker and
                               tuple(arg.key_concepts) in self.established_arguments)
        penalty += established_count * 1.5

        return penalty

    def get_relevance_score(self, speaker: str, last_argument: Optional[Argument] = None) -> float:
        """Score how relevant a speaker is to the current debate state."""
        if not last_argument:
            return 0.5

        score = 0.0

        # Higher relevance if this speaker was previously responded to
        if last_argument.responds_to and last_argument.responds_to == speaker:
            score += 2.0

        # Higher relevance if this speaker has objections pending
        pending_objections = [obj for obj in self.objections
                              if obj.speaker != speaker and
                              not any(a.responds_to == obj.speaker and a.speaker == speaker
                                     for a in self.arguments)]
        score += len(pending_objections) * 1.0

        # Higher relevance if this speaker hasn't spoken recently
        last_turn = self.speaker_turn_count.get(speaker, 0)
        if last_turn == 0:
            score += 3.0  # Bonus for never having spoken
        elif last_turn < self.turn_count / len(self.speaker_turn_count) if self.speaker_turn_count else 1:
            score += 1.0  # Slight bonus for underrepresented speakers

        return score

    def should_prevent_speaker(self, speaker: str) -> bool:
        """Check if a speaker should be prevented from speaking again."""
        # Prevent if they've spoken more than 2x the average
        if self.speaker_turn_count:
            avg = self.turn_count / len(self.speaker_turn_count)
            if self.speaker_turn_count.get(speaker, 0) > avg * 2.5:
                return True

        # Prevent consecutive turns unless very few total turns
        if (self.consecutive_speakers and
            self.consecutive_speakers[-1] == speaker and
            self.turn_count > 3):
            return True

        return False

    def get_alternatives(self, exclude: Optional[str] = None) -> list[str]:
        """Get list of valid speakers, sorted by relevance."""
        from philosophical_council.core.constants import VALID_SPEAKERS

        alternatives = []
        for speaker in VALID_SPEAKERS:
            if exclude and speaker == exclude:
                continue
            if self.should_prevent_speaker(speaker):
                continue

            score = self.get_relevance_score(speaker)
            penalty = self.get_repetition_penalty(speaker)
            final_score = score - penalty

            alternatives.append((speaker, final_score))

        # Sort by score descending
        alternatives.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in alternatives]