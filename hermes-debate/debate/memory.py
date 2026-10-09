"""
Memory pipeline for debate state management.
Handles structured memory, recent context, and historical compression.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MemorySegment:
    """A segment of debate memory."""
    turn_number: int
    agent_id: str
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    relevance_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            'turn_number': self.turn_number,
            'agent_id': self.agent_id,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'relevance_score': self.relevance_score,
        }


class MemoryPipeline:
    """
    Manages debate memory with structured segmentation.

    Maintains:
    - Recent verbatim context (last N turns)
    - Historical compressed summary
    - Structured arguments/objections/contradictions
    - Relevance scoring for reranking
    """

    def __init__(self, recent_window: int = 10, historical_threshold: int = 20):
        self.recent_window = recent_window
        self.historical_threshold = historical_threshold

        self.recent_turns: list[MemorySegment] = []
        self.historical_turns: list[MemorySegment] = []
        self.all_turns: list[MemorySegment] = []

        # Structured debate content
        self.positions: dict[str, str] = {}
        self.arguments: list[dict] = []
        self.counterarguments: list[dict] = []
        self.objections: list[dict] = []
        self.contradictions: list[dict] = []
        self.unresolved_points: list[str] = []

    def add_turn(self, turn_number: int, agent_id: str, role: str, content: str) -> None:
        """Add a new turn to memory."""
        segment = MemorySegment(
            turn_number=turn_number,
            agent_id=agent_id,
            role=role,
            content=content,
        )

        self.all_turns.append(segment)
        self.recent_turns.append(segment)

        # Maintain recent window
        if len(self.recent_turns) > self.recent_window:
            older = self.recent_turns[:-self.recent_window // 2]
            self.historical_turns.extend(older)
            self.recent_turns = self.recent_turns[-self.recent_window // 2:]

        # Update structured content based on role
        self._update_structured_content(segment, turn_number)

    def _update_structured_content(self, segment: MemorySegment, turn_number: int) -> None:
        """Update structured debate content from a turn."""
        if segment.role == 'philosopher':
            self.positions[segment.agent_id] = segment.content[:200]
            self.arguments.append({
                'turn_number': turn_number,
                'agent_id': segment.agent_id,
                'content': segment.content[:300],
            })
        elif segment.role == 'critic':
            self.counterarguments.append({
                'turn_number': turn_number,
                'agent_id': segment.agent_id,
                'content': segment.content[:300],
            })
            # Check for contradictions
            for pos_agent, pos_content in self.positions.items():
                if pos_agent != segment.agent_id:
                    contradiction = self._detect_contradiction(segment.content, pos_content)
                    if contradiction:
                        self.contradictions.append({
                            'turn_number': turn_number,
                            'agent_a': pos_agent,
                            'agent_b': segment.agent_id,
                            'contradiction': contradiction,
                        })

    def _detect_contradiction(self, text_a: str, text_b: str) -> Optional[str]:
        """Simple heuristic contradiction detection."""
        # Look for negation patterns
        negations = ['not', 'never', 'no', 'false', 'incorrect', 'wrong']
        text_a_lower = text_a.lower()
        text_b_lower = text_b.lower()

        for neg in negations:
            if neg in text_a_lower and neg not in text_b_lower:
                # Check if they discuss similar topics
                words_a = set(text_a_lower.split())
                words_b = set(text_b_lower.split())
                if len(words_a & words_b) > 3:
                    return f"Agent A claims '{neg}' while Agent B does not"

        return None

    def get_recent_context(self, max_tokens: int = 2048) -> list[dict]:
        """Get recent context for model input."""
        context = []
        for turn in self.recent_turns[-5:]:
            context.append({
                'role': turn.role,
                'agent_id': turn.agent_id,
                'content': turn.content[:max_tokens // 4],
            })
        return context

    def get_historical_summary(self) -> str:
        """Get compressed historical summary."""
        if not self.historical_turns:
            return "No historical context."

        summary_parts = []
        for turn in self.historical_turns[-10:]:
            summary_parts.append(
                f"[Turn {turn.turn_number}] {turn.role}: {turn.content[:150]}..."
            )

        return "\n".join(summary_parts)

    def get_structured_memory(self) -> dict:
        """Get full structured memory for state serialization."""
        return {
            'positions': self.positions,
            'arguments': self.arguments[-5:],
            'counterarguments': self.counterarguments[-5:],
            'objections': self.objections[-5:],
            'contradictions': self.contradictions[-3:],
            'unresolved_points': self.unresolved_points,
            'recent_turns': [t.to_dict() for t in self.recent_turns],
            'historical_summary': self.get_historical_summary(),
        }

    def clear(self) -> None:
        """Clear all memory."""
        self.recent_turns.clear()
        self.historical_turns.clear()
        self.all_turns.clear()
        self.positions.clear()
        self.arguments.clear()
        self.counterarguments.clear()
        self.objections.clear()
        self.contradictions.clear()
        self.unresolved_points.clear()
