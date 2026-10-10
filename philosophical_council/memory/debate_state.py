"""Enhanced debate state tracking for progressive argumentation."""

from __future__ import annotations

import logging
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# Argument semantic clusters - maps related arguments to the same conceptual ID
ARGUMENT_CLUSTERS: dict[str, list[str]] = {
    "value_laden_consequences": [
        "flourishing requires a prior value",
        "consequences are value-laden",
        "experience cannot tell us what matters",
        "empirical observation presupposes a criterion",
        "the testing framework assumes flourishing",
        "practical consequences require normative standards",
    ],
    "ungrounded_normativity": [
        "no neutral vantage point",
        "all standards require prior commitments",
        "no transcendent grounding",
        "every framework is circular",
        "all commitments are ungrounded",
        "normative foundations are impossible",
    ],
    "circularity_problem": [
        "justification requires justification",
        "infinite regress of reasons",
        "foundationalism fails",
        "coherentism is circular",
        "skepticism is self-defeating",
    ],
    "pragmatic_resolution": [
        "we must live with uncertainty",
        "practical wisdom suffices",
        "meaning is constructed not discovered",
        "commitment creates value",
        "action precedes justification",
    ],
}


@dataclass
class Claim:
    """A specific claim made by an agent."""
    turn_id: int
    speaker: str
    content: str
    key_concepts: list[str] = field(default_factory=list)
    responded_to: Optional[str] = None
    argument_cluster: Optional[str] = None


@dataclass
class Objection:
    """An objection raised against a claim."""
    turn_id: int
    speaker: str
    target_speaker: str
    content: str
    key_concepts: list[str] = field(default_factory=list)
    responded: bool = False
    argument_cluster: Optional[str] = None


@dataclass
class PositionChange:
    """Records when an agent changes their position."""
    turn_id: int
    speaker: str
    old_position: str
    new_position: str
    reason: str
    magnitude: float = 0.5


@dataclass
class EstablishedArgument:
    """An argument that has been sufficiently demonstrated."""
    arg_id: str
    claim: str
    status: str = "provisionally_established"
    supporting_agents: list[str] = field(default_factory=list)
    counterarguments: list[str] = field(default_factory=list)
    strength: float = 0.0
    saturation: float = 0.0
    times_used: int = 0
    last_used_turn: Optional[int] = None


@dataclass
class ArgumentThread:
    """A thread of argumentation around a specific question."""
    thread_id: str
    central_question: str
    claims: list[Claim] = field(default_factory=list)
    objections: list[Objection] = field(default_factory=list)
    current_speaker: Optional[str] = None
    last_speaker: Optional[str] = None
    status: str = "active"  # active, resolved, abandoned

    # Metadata for thread management
    participants: set[str] = field(default_factory=set)
    core_objection: Optional[str] = None
    last_progress: Optional[str] = None

    # Saturation tracking
    saturation_level: int = 0
    max_saturation: int = 5  # Default threshold
    established_conclusions: list[str] = field(default_factory=list)
    unresolved_points: list[str] = field(default_factory=list)

    # Next move type
    next_move_type: str = "attack"  # attack, defense, clarification, concession, distinction, construction, stress_test, revision, comparison, synthesis, pivot


@dataclass
class DebateArchiveEntry:
    """Entry for the debate test archive."""
    turn_id: int
    speaker: str
    responding_to: Optional[str]
    thread_id: str
    target_claim: Optional[str]
    main_argument: Optional[str]
    response: str
    new_claim: Optional[str]
    objection: Optional[str]
    concession: Optional[str]
    position_changed: bool
    state_changed: bool
    quality_score: float
    timestamp: str


class DebateState:
    """Complete structured state of the debate for intelligent moderation."""

    # Debate phases
    PHASE_EXPLORATION = "exploration"
    PHASE_DESTRUCTION = "destruction"
    PHASE_SATURATION = "saturation"
    PHASE_CONSTRUCTION = "construction"
    PHASE_STRESS_TEST = "stress_test"
    PHASE_REVISION = "revision"
    PHASE_SYNTHESIS = "synthesis"

    def __init__(self, topic: str = "") -> None:
        self.topic = topic

        # Thread management
        self.threads: dict[str, ArgumentThread] = {}
        self.active_thread_id: str = "main"

        # Global tracking
        self.turn_count: int = 0
        self.all_claims: list[Claim] = []
        self.all_objections: list[Objection] = []

        # Speaker statistics
        self.speaker_turn_count: dict[str, int] = defaultdict(int)
        self.speaker_claims: dict[str, list[str]] = defaultdict(list)
        self.speaker_positions: dict[str, str] = {}
        self.position_changes: list[PositionChange] = []

        # Recent history
        self.recent_speakers: list[str] = []
        self.recent_claims: list[Claim] = []
        self.recent_objections: list[Objection] = []

        # Unresolved issues
        self.unresolved_questions: list[str] = []
        self.established_arguments: dict[str, EstablishedArgument] = {}

        # Quality tracking
        self.turn_quality_scores: list[float] = []

        # Archive entries
        self.archive_entries: list[DebateArchiveEntry] = []

        # Semantic fingerprint tracking for repetition detection
        self._argument_fingerprints: dict[str, list[str]] = defaultdict(list)
        self._semantic_clusters: dict[str, set[str]] = {}

        # Phase management
        self.current_phase: str = self.PHASE_EXPLORATION
        self.phase_transitions: list[dict] = []

        # Consecutive turn tracking
        self.consecutive_speaker: Optional[str] = None
        self.consecutive_count: int = 0

        # Legacy fields for compatibility
        self.status: str = "idle"
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.error_count: int = 0
        self.agent_positions: dict[str, list[str]] = defaultdict(list)
        self.argument_history: list[dict[str, str]] = []

        # Fallback tracking
        self.fallback_count: int = 0
        self.fallback_reasons: list[str] = []
        self.fallback_quality_scores: list[float] = []

    def start(self) -> None:
        """Start the debate."""
        self.status = "running"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.turn_count = 0
        logger.info("Debate started: %s", self.topic)

    def stop(self) -> None:
        """Stop the debate."""
        self.status = "stopped"
        self.finished_at = datetime.now(timezone.utc).isoformat()
        logger.info("Debate stopped after %d turns", self.turn_count)

    def add_turn(
        self,
        turn_id: int,
        speaker: str,
        response: str,
        responding_to: Optional[str] = None,
        argument_type: str = "claim",
        thread_id: Optional[str] = None,
        target_claim: Optional[str] = None,
    ) -> None:
        """Record a turn and update all state."""
        self.turn_count += 1

        # Update recent speakers
        self.recent_speakers.append(speaker)
        if len(self.recent_speakers) > 20:
            self.recent_speakers = self.recent_speakers[-20:]

        # Update speaker stats
        self.speaker_turn_count[speaker] += 1

        # Extract claims and objections
        claims = self._extract_claims(response, turn_id, speaker)
        objections = self._extract_objections(response, turn_id, speaker, responding_to)

        # Store claims
        for claim in claims:
            self.all_claims.append(claim)
            self.speaker_claims[speaker].append(claim.content[:100])
            self.recent_claims.append(claim)

            # Track positions (legacy)
            if speaker not in self.agent_positions:
                self.agent_positions[speaker] = []
            self.agent_positions[speaker].append(claim.content[:200])

            # Track argument history (legacy)
            self.argument_history.append({
                "speaker": speaker,
                "argument": claim.content[:300],
                "type": argument_type,
                "turn_id": turn_id,
            })

            # Track position changes - detect if response introduces new concepts
            if speaker in self.speaker_positions:
                old_pos = self.speaker_positions[speaker]
                # Check for significant semantic shift (not just repetition)
                if self._has_significant_shift(old_pos, response):
                    self.position_changes.append(PositionChange(
                        turn_id=turn_id,
                        speaker=speaker,
                        old_position=old_pos[:200],
                        new_position=response[:200],
                        reason=f"Response to {responding_to}" if responding_to else "New argument",
                    ))
            else:
                self.speaker_positions[speaker] = response[:300]

        # Store objections and mark as unresolved
        for objection in objections:
            self.all_objections.append(objection)
            self.recent_objections.append(objection)

            # Add to unresolved questions if it's a genuine question
            if "?" in objection.content and len(objection.content) > 20:
                self.unresolved_questions.append(objection.content.strip())

        # Update active thread
        if not thread_id:
            thread_id = self.active_thread_id

        if thread_id not in self.threads:
            self.threads[thread_id] = ArgumentThread(
                thread_id=thread_id,
                central_question=self.topic,
            )

        thread = self.threads[thread_id]
        thread.last_speaker = thread.current_speaker
        thread.current_speaker = speaker
        thread.participants.add(speaker)

        # Add claims and objections to thread
        for claim in claims:
            thread.claims.append(claim)
        for objection in objections:
            thread.objections.append(objection)

        # Clean up old items
        if len(self.recent_claims) > 30:
            self.recent_claims = self.recent_claims[-30:]
        if len(self.recent_objections) > 20:
            self.recent_objections = self.recent_objections[-20:]

    def _extract_claims(self, text: str, turn_id: int, speaker: str) -> list[Claim]:
        """Extract claims from a response."""
        claims = []

        patterns = [
            r"(?:I believe|my position|the truth is|essentially|what I mean is)\s*([^.]{20,150})",
            r"(?:claim|argue|assert)\s+(?:that\s+)?([^.]{20,150})",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                cleaned = ' '.join(match.split())
                if len(cleaned) > 20:
                    concepts = self._extract_concepts(cleaned)
                    claim = Claim(
                        turn_id=turn_id,
                        speaker=speaker,
                        content=cleaned,
                        key_concepts=concepts,
                    )
                    # Try to match to an argument cluster
                    claim.argument_cluster = self._match_argument_cluster(cleaned)
                    claims.append(claim)

        # If no specific claims found, use first substantial sentence
        if not claims:
            sentences = re.split(r'[.!?]+', text)
            for sent in sentences:
                sent = ' '.join(sent.split())
                if len(sent) > 50 and len(sent) < 300:
                    concepts = self._extract_concepts(sent)
                    claim = Claim(
                        turn_id=turn_id,
                        speaker=speaker,
                        content=sent,
                        key_concepts=concepts,
                    )
                    claim.argument_cluster = self._match_argument_cluster(sent)
                    claims.append(claim)
                    break

        return claims

    def _extract_objections(self, text: str, turn_id: int, speaker: str,
                           responds_to: Optional[str]) -> list[Objection]:
        """Extract objections from a response."""
        objections = []

        patterns = [
            r"(?:but|however|yet)\s+([^.]{20,150})",
            r"(?:challenge|objection|problem|issue|contradiction)\s+(?:is|that\s+)?([^.]{20,150})",
            r"(?:why|how)\s+[^.]+\??",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                cleaned = ' '.join(match.split())
                if len(cleaned) > 20:
                    concepts = self._extract_concepts(cleaned)
                    objection = Objection(
                        turn_id=turn_id,
                        speaker=speaker,
                        target_speaker=responds_to or "unknown",
                        content=cleaned,
                        key_concepts=concepts,
                    )
                    # Try to match to an argument cluster
                    objection.argument_cluster = self._match_argument_cluster(cleaned)
                    objections.append(objection)

        return objections

    def _extract_concepts(self, text: str) -> list[str]:
        """Extract key concepts from text."""
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'for', 'in',
            'on', 'at', 'by', 'with', 'from', 'and', 'or', 'but', 'not', 'no',
            'if', 'then', 'than', 'that', 'this', 'it', 'its', 'i', 'me', 'my',
            'we', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her', 'they',
            'them', 'their', 'which', 'what', 'who', 'whom',
        }

        words = re.findall(r'\b[a-zA-Zà-ÿ]+\b', text.lower())
        concepts = [w for w in words if len(w) > 3 and w not in stop_words]

        freq = Counter(concepts)
        return [word for word, _ in freq.most_common(8)]

    def _match_argument_cluster(self, text: str) -> Optional[str]:
        """Match text to an argument cluster."""
        text_lower = text.lower()

        for cluster_id, examples in ARGUMENT_CLUSTERS.items():
            for example in examples:
                if example.lower() in text_lower or text_lower in example.lower():
                    return cluster_id

        # Also check for key concept overlap
        concepts = set(self._extract_concepts(text))
        for cluster_id, examples in ARGUMENT_CLUSTERS.items():
            for example in examples:
                example_concepts = set(self._extract_concepts(example))
                if concepts & example_concepts:
                    return cluster_id

        return None

    def _has_significant_shift(self, old_position: str, new_response: str) -> bool:
        """Check if the response represents a significant shift from old position."""
        # Extract key concepts from both
        old_concepts = set(re.findall(r'\b[a-zA-Zà-ÿ]{4,}\b', old_position.lower()))
        new_concepts = set(re.findall(r'\b[a-zA-Zà-ÿ]{4,}\b', new_response.lower()))

        # Calculate overlap
        if not old_concepts or not new_concepts:
            return False

        overlap = len(old_concepts & new_concepts)
        total = len(old_concepts | new_concepts)

        # If less than 50% overlap, consider it a shift
        if total == 0:
            return False

        return (overlap / total) < 0.5

    def get_strongest_unresolved_objection(self) -> Optional[Objection]:
        """Find the strongest unresolved objection."""
        for obj in reversed(self.all_objections):
            # Check if anyone responded to this objection
            responded = any(
                c.responded_to == obj.speaker and c.speaker != obj.target_speaker
                for c in self.all_claims[-10:]
            )
            if not responded:
                return obj

        return None

    def get_best_respondent(self, target_speaker: str) -> Optional[str]:
        """Find who is best positioned to respond to a speaker."""
        candidates = []

        for speaker in self.speaker_turn_count.keys():
            if speaker == target_speaker:
                continue

            # Score based on having objections to this speaker
            score = sum(
                1 for obj in self.all_objections
                if obj.target_speaker == target_speaker and obj.speaker == speaker
            )

            # Bonus for not having spoken recently
            turns = self.speaker_turn_count.get(speaker, 0)
            if turns == 0:
                score += 5
            elif turns < self.turn_count / max(len(self.speaker_turn_count), 1):
                score += 2

            candidates.append((speaker, score))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0] if candidates[0][1] > 0 else None

    def get_alternatives(self, exclude: Optional[str] = None) -> list[str]:
        """Get valid speakers sorted by relevance."""
        from philosophical_council.core.debate_engine import VALID_SPEAKERS

        alternatives = []
        for speaker in VALID_SPEAKERS:
            if exclude and speaker == exclude:
                continue

            if self.should_prevent_speaker(speaker):
                continue

            score = self._calculate_speaker_score(speaker)
            alternatives.append((speaker, score))

        alternatives.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in alternatives]

    def _calculate_speaker_score(self, speaker: str) -> float:
        """Calculate relevance score for a speaker."""
        score = 0.0

        # Penalty for too many turns (progression priority over equity)
        count = self.speaker_turn_count.get(speaker, 0)
        avg = self.turn_count / max(len(self.speaker_turn_count), 1)
        if count > avg * 2:
            score -= 3.0
        elif count > avg:
            score -= 1.0

        # Bonus for not having spoken recently
        if speaker not in self.recent_speakers[-5:]:
            score += 2.0

        # Small bonus for never having spoken (not dominant)
        if count == 0:
            score += 1.0

        # Bonus for having unresolved objections
        pending = sum(
            1 for obj in self.all_objections
            if obj.speaker == speaker and not any(
                c.responded_to == obj.speaker and c.speaker != obj.target_speaker
                for c in self.all_claims[-5:]
            )
        )
        score += pending * 1.5

        return score

    def should_prevent_speaker(self, speaker: str) -> bool:
        """Check if a speaker should be prevented from speaking."""
        count = self.speaker_turn_count.get(speaker, 0)
        avg = self.turn_count / max(len(self.speaker_turn_count), 1)

        # Prevent if they've spoken more than 2.5x the average
        if count > avg * 2.5 and self.turn_count > 5:
            return True

        # Prevent consecutive turns (max 1 consecutive by default)
        if speaker == self.consecutive_speaker and self.consecutive_count >= 1:
            return True

        return False

    def check_saturation(self, thread_id: Optional[str] = None) -> bool:
        """Check if a thread has reached saturation."""
        if thread_id:
            thread = self.threads.get(thread_id)
            if thread and thread.saturation_level >= thread.max_saturation:
                return True
        else:
            # Check all active threads
            for tid, thread in self.threads.items():
                if thread.status == "active" and thread.saturation_level >= thread.max_saturation:
                    return True
        return False

    def detect_repetition(self, new_response: str, speaker: str) -> bool:
        """Detect if a response repeats an existing argument semantically."""
        # Extract semantic fingerprint
        fingerprint = self._compute_fingerprint(new_response)

        # Check against existing fingerprints for this speaker
        if speaker in self._argument_fingerprints:
            existing_fps = self._argument_fingerprints[speaker]
            for existing_fp in existing_fps:
                if self._fingerprints_similar(fingerprint, existing_fp):
                    return True

        # Store fingerprint
        if speaker not in self._argument_fingerprints:
            self._argument_fingerprints[speaker] = []
        self._argument_fingerprints[speaker].append(fingerprint)

        return False

    def _compute_fingerprint(self, text: str) -> str:
        """Compute a semantic fingerprint for a response."""
        # Extract key concepts and arguments
        concepts = self._extract_concepts(text)

        # Create a simplified representation
        fingerprint_parts = []
        for concept in concepts[:5]:  # Top 5 concepts
            fingerprint_parts.append(concept.lower())

        return "|".join(sorted(fingerprint_parts))

    def _fingerprints_similar(self, fp1: str, fp2: str) -> bool:
        """Check if two fingerprints represent similar arguments."""
        concepts1 = set(fp1.split("|"))
        concepts2 = set(fp2.split("|"))

        # Calculate overlap
        if not concepts1 or not concepts2:
            return False

        overlap = len(concepts1 & concepts2)
        total = len(concepts1 | concepts2)

        # High overlap indicates repetition
        return overlap / total > 0.7 if total > 0 else False

    def advance_phase(self, new_phase: str) -> None:
        """Advance the debate to a new phase."""
        if self.current_phase != new_phase:
            self.phase_transitions.append({
                "from": self.current_phase,
                "to": new_phase,
                "turn": self.turn_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.info("Phase transition: %s -> %s at turn %d",
                       self.current_phase, new_phase, self.turn_count)
        self.current_phase = new_phase

    def record_position_revision(self, speaker: str, old_pos: str, new_pos: str,
                                reason: str, magnitude: float = 0.5) -> None:
        """Record a position revision with magnitude."""
        self.position_changes.append(PositionChange(
            turn_id=self.turn_count,
            speaker=speaker,
            old_position=old_pos[:200],
            new_position=new_pos[:200],
            reason=reason[:200],
            magnitude=magnitude,
        ))

        # Update speaker position
        self.speaker_positions[speaker] = new_pos[:300]

    def establish_argument(self, arg_id: str, claim: str, agent: str, strength: float = 0.8) -> None:
        """Mark an argument as provisionally established."""
        if arg_id not in self.established_arguments:
            self.established_arguments[arg_id] = EstablishedArgument(
                arg_id=arg_id,
                claim=claim,
                supporting_agents=[agent],
                strength=strength,
            )
        elif agent not in self.established_arguments[arg_id].supporting_agents:
            self.established_arguments[arg_id].supporting_agents.append(agent)
            self.established_arguments[arg_id].strength = min(1.0,
                self.established_arguments[arg_id].strength + 0.1)

    def get_established_arguments(self) -> list[EstablishedArgument]:
        """Get all established arguments."""
        return list(self.established_arguments.values())

    def build_moderator_context(self) -> str:
        """Build context for the moderator prompt."""
        lines = [f"DEBATE TOPIC: {self.topic}"]
        lines.append(f"Total turns: {self.turn_count}")
        lines.append(f"Current phase: {self.current_phase}")

        # Speaker stats
        lines.append("\nSPEAKER DISTRIBUTION:")
        for speaker, count in sorted(
            self.speaker_turn_count.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            lines.append(f"  - {speaker}: {count} turns")

        # Recent claims
        if self.recent_claims:
            lines.append("\nRECENT CLAIMS:")
            for claim in self.recent_claims[-5:]:
                cluster_info = f" [CLUSTER: {claim.argument_cluster}]" if claim.argument_cluster else ""
                lines.append(f"  Turn {claim.turn_id} ({claim.speaker}): {claim.content[:80]}...{cluster_info}")

        # Recent objections
        if self.recent_objections:
            lines.append("\nRECENT OBJECTIONS:")
            for obj in self.recent_objections[-5:]:
                cluster_info = f" [CLUSTER: {obj.argument_cluster}]" if obj.argument_cluster else ""
                lines.append(f"  Turn {obj.turn_id} ({obj.speaker} vs {obj.target_speaker}): {obj.content[:80]}...{cluster_info}")

        # Unresolved questions
        if self.unresolved_questions:
            lines.append("\nUNRESOLVED QUESTIONS:")
            for q in self.unresolved_questions[-3:]:
                lines.append(f"  - {q}")

        # Established arguments
        established = self.get_established_arguments()
        if established:
            lines.append("\nESTABLISHED ARGUMENTS (do not repeat):")
            for arg in established:
                lines.append(f"  - {arg.arg_id}: {arg.claim[:80]}... (strength: {arg.strength:.2f})")

        # Position changes
        if self.position_changes:
            lines.append("\nPOSITION CHANGES:")
            for change in self.position_changes[-2:]:
                lines.append(f"  {change.speaker}: revised position at turn {change.turn_id}")

        return "\n".join(lines)

    def build_agent_prompt_context(self, speaker: str, responding_to: Optional[str]) -> str:
        """Build context for an agent's response."""
        lines = [f"CURRENT DEBATE TOPIC: {self.topic}"]
        lines.append(f"Current phase: {self.current_phase}")

        # Show this agent's previous positions
        if speaker in self.speaker_positions:
            lines.append(f"\nYOUR PREVIOUS POSITION:")
            lines.append(self.speaker_positions[speaker][:300])

        # Show your previous claims
        my_claims = [c for c in self.all_claims if c.speaker == speaker]
        if my_claims:
            lines.append(f"\nYOUR PREVIOUS CLAIMS (do not repeat these):")
            for claim in my_claims[-3:]:
                cluster_info = f" [CLUSTER: {claim.argument_cluster}]" if claim.argument_cluster else ""
                lines.append(f"  - {claim.content[:100]}{cluster_info}")

        # Show what others have said
        if responding_to:
            lines.append(f"\nRESPONDING TO {responding_to}:")
            their_claims = [c for c in self.all_claims
                          if c.speaker == responding_to and c.turn_id > (self.turn_count - 10)]
            for claim in their_claims[-2:]:
                lines.append(f"  Claim: {claim.content[:150]}")

            # Show objections to them
            their_objections = [o for o in self.all_objections
                               if o.target_speaker == responding_to]
            if their_objections:
                lines.append(f"\nOBJECTIONS RAISED AGAINST {responding_to}:")
                for obj in their_objections[-2:]:
                    lines.append(f"  - {obj.content[:100]}")

        # Show unresolved questions
        if self.unresolved_questions:
            lines.append(f"\nUNRESOLVED QUESTIONS TO ADDRESS:")
            for q in self.unresolved_questions[-2:]:
                lines.append(f"  - {q}")

        # Show established arguments to avoid repeating
        established = self.get_established_arguments()
        if established:
            lines.append(f"\nESTABLISHED ARGUMENTS (do not repeat, build upon or challenge):")
            for arg in established[:3]:
                lines.append(f"  - {arg.arg_id}: {arg.claim[:100]}")

        return "\n".join(lines)

    def check_turn_quality(self, speaker: str, response: str, responding_to: Optional[str]) -> dict:
        """Check if a turn advances the debate."""
        quality = {
            "responds_to_previous": False,
            "new_contribution": False,
            "state_changed": False,
            "score": 0.0,
            "repetition_detected": False,
            "thread_progressed": False,
            "semantic_novelty": 0.0,
        }

        # Check if responding to previous argument
        if responding_to:
            quality["responds_to_previous"] = True
            quality["score"] += 0.3

        # Check for new claims
        my_claims = [c for c in self.all_claims if c.speaker == speaker]
        if my_claims:
            latest_claim = my_claims[-1].content
            # Check if this is different from previous claims
            if len(my_claims) > 1:
                prev_claims = [c.content for c in my_claims[:-1]]
                if latest_claim not in prev_claims:
                    quality["new_contribution"] = True
                    quality["score"] += 0.3

        # Check for position change
        if self.position_changes and self.position_changes[-1].speaker == speaker:
            quality["state_changed"] = True
            quality["score"] += 0.4

        # Check for objections raised
        recent_objections = [o for o in self.recent_objections
                           if o.speaker == speaker and o.turn_id >= self.turn_count - 2]
        if recent_objections:
            quality["score"] += 0.2

        # Check for repetition
        if self.detect_repetition(response, speaker):
            quality["repetition_detected"] = True
            quality["score"] -= 0.3

        # Calculate semantic novelty (simple heuristic)
        quality["semantic_novelty"] = self._calculate_semantic_novelty(response, speaker)

        return quality

    def _calculate_semantic_novelty(self, response: str, speaker: str) -> float:
        """Calculate how novel a response is compared to previous arguments.

        Honest metric (spec §17): an EMPTY or trivially tiny response carries NO
        measurable content, so it must never be reported as maximally novel
        (1.0). Only a response with actual substance can be judged; empty/tiny
        output is 0.0 (no contribution) rather than fake precision.
        """
        text = (response or "").strip()
        if len(text) < 20:
            return 0.0  # too tiny to measure — not a novel contribution
        my_claims = [c for c in self.all_claims if c.speaker == speaker]
        if not my_claims:
            return 1.0  # First substantive argument is always novel

        # Extract concepts from new response
        new_concepts = set(self._extract_concepts(response))

        # Check overlap with previous claims
        total_overlap = 0
        for claim in my_claims[-3:]:
            claim_concepts = set(claim.key_concepts)
            if claim_concepts:
                overlap = len(new_concepts & claim_concepts)
                total = len(new_concepts | claim_concepts)
                if total > 0:
                    total_overlap += overlap / total

        # Novelty is inverse of average overlap
        avg_overlap = total_overlap / min(3, len(my_claims))
        novelty = max(0.0, 1.0 - avg_overlap)

        return round(novelty, 2)

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict."""
        return {
            "topic": self.topic,
            "status": self.status,
            "turn_count": self.turn_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_count": self.error_count,
            "agent_positions": dict(self.agent_positions),
            "argument_history": self.argument_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DebateState:
        """Deserialize from dict."""
        state = cls(
            topic=str(data.get("topic", "")),
        )
        state.status = str(data.get("status", "idle"))
        state.turn_count = int(data.get("turn_count", 0))
        state.started_at = data.get("started_at")
        state.finished_at = data.get("finished_at")
        state.error_count = int(data.get("error_count", 0))

        positions = data.get("agent_positions", {})
        if isinstance(positions, dict):
            state.agent_positions = positions

        history = data.get("argument_history", [])
        if isinstance(history, list):
            state.argument_history = history

        return state

    def rollback_reserved_turn(self, speaker: str) -> None:
        """Undo the optimistic reservation of a turn.

        The engine reserves a turn (placeholder ``add_turn``) BEFORE launching
        the model call; if the model returns an empty/whitespace response the
        reservation is rolled back so no phantom/conceptual turn ever counts.
        Reverses exactly what the reservation mutated: turn_count, speaker
        turns, and the trailing recent-speaker marker.
        """
        self.turn_count = max(0, self.turn_count - 1)
        if speaker in self.speaker_turn_count:
            self.speaker_turn_count[speaker] -= 1
            if self.speaker_turn_count[speaker] <= 0:
                del self.speaker_turn_count[speaker]
        # Remove the trailing reservation occurrence of this speaker (if any).
        for i in range(len(self.recent_speakers) - 1, -1, -1):
            if self.recent_speakers[i] == speaker:
                del self.recent_speakers[i]
                break