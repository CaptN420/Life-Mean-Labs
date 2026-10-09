"""
Memory store for Hermes Multi-Agent Debate Orchestrator.
Multi-level memory: recent, structured, and long-term.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str
    content: str
    type: str  # "argument", "objection", "position", "contradiction", "decision"
    source_agent: str
    turn_number: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'content': self.content,
            'type': self.type,
            'source_agent': self.source_agent,
            'turn_number': self.turn_number,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


class MemoryStore:
    """
    Multi-level memory store.
    
    Level 1: Recent - verbatim turns (last 10)
    Level 2: Structured - arguments, objections, positions, contradictions
    Level 3: Long-term - historical passages for reranking
    """
    
    def __init__(self, max_recent: int = 10, max_historical: int = 100):
        self._recent: List[MemoryEntry] = []
        self._structured: Dict[str, List[MemoryEntry]] = {
            'arguments': [],
            'objections': [],
            'positions': [],
            'contradictions': [],
            'decisions': []
        }
        self._historical: List[MemoryEntry] = []
        self._max_recent = max_recent
        self._max_historical = max_historical
        self._counter = 0
    
    def add_turn(self, turn_number: int, agent_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        """Add a debate turn to memory."""
        entry = MemoryEntry(
            id=f"turn_{turn_number}",
            content=content,
            type="turn",
            source_agent=agent_id,
            turn_number=turn_number,
            metadata=metadata or {}
        )
        
        self._recent.append(entry)
        if len(self._recent) > self._max_recent:
            # Move older turns to historical
            removed = self._recent.pop(0)
            self._historical.append(removed)
        
        return entry.id
    
    def add_argument(self, turn_number: int, agent_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        """Add an argument to structured memory."""
        entry = MemoryEntry(
            id=f"arg_{self._counter}",
            content=content,
            type="argument",
            source_agent=agent_id,
            turn_number=turn_number,
            metadata=metadata or {}
        )
        self._counter += 1
        self._structured['arguments'].append(entry)
        return entry.id
    
    def add_objection(self, turn_number: int, agent_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        """Add an objection to structured memory."""
        entry = MemoryEntry(
            id=f"obj_{self._counter}",
            content=content,
            type="objection",
            source_agent=agent_id,
            turn_number=turn_number,
            metadata=metadata or {}
        )
        self._counter += 1
        self._structured['objections'].append(entry)
        return entry.id
    
    def add_position(self, agent_id: str, position: str, metadata: Optional[Dict] = None) -> str:
        """Add a position to structured memory."""
        entry = MemoryEntry(
            id=f"pos_{self._counter}",
            content=position,
            type="position",
            source_agent=agent_id,
            turn_number=0,
            metadata=metadata or {}
        )
        self._counter += 1
        self._structured['positions'].append(entry)
        return entry.id
    
    def add_contradiction(self, arg1: str, arg2: str, explanation: str, metadata: Optional[Dict] = None) -> str:
        """Add a contradiction to structured memory."""
        entry = MemoryEntry(
            id=f"contr_{self._counter}",
            content=f"Contradiction: {arg1} vs {arg2}. Explanation: {explanation}",
            type="contradiction",
            source_agent="system",
            turn_number=0,
            metadata=metadata or {}
        )
        self._counter += 1
        self._structured['contradictions'].append(entry)
        return entry.id
    
    def get_recent(self, n: int = 5) -> List[MemoryEntry]:
        """Get recent turns."""
        return self._recent[-n:]
    
    def get_structured(self, type_: Optional[str] = None) -> List[MemoryEntry]:
        """Get structured memories, optionally filtered by type."""
        if type_ and type_ in self._structured:
            return self._structured[type_]
        # Return all structured
        result = []
        for entries in self._structured.values():
            result.extend(entries)
        return result
    
    def get_historical(self, n: int = 50) -> List[MemoryEntry]:
        """Get historical memories."""
        return self._historical[-n:]
    
    def get_all(self) -> Dict[str, Any]:
        """Get complete memory state."""
        return {
            'recent': [e.to_dict() for e in self.get_recent()],
            'structured': {
                k: [e.to_dict() for e in v]
                for k, v in self._structured.items()
            },
            'historical_count': len(self._historical),
            'total_entries': self._counter
        }
    
    def clear(self) -> None:
        """Clear all memories."""
        self._recent.clear()
        for key in self._structured:
            self._structured[key].clear()
        self._historical.clear()
        self._counter = 0
