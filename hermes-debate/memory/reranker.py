"""
Reranker for memory selection.
Selects most relevant memories based on query.
"""

import logging
from typing import Optional, List, Dict, Any
import asyncio

logger = logging.getLogger(__name__)


class MemoryReranker:
    """
    Reranker for selecting relevant memories.
    
    Receives:
    - query (current debate context)
    - candidates (list of memory entries)
    
    Returns:
    - top-k most relevant passages
    """
    
    def __init__(self, top_k: int = 5):
        self.top_k = top_k
    
    async def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        model_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank memory candidates based on relevance to query.
        
        In production, this would use a small embedding model or JEV.
        For now, uses simple heuristic scoring.
        """
        if not candidates:
            return []
        
        # In production, call reranker model (0.6B)
        # For simulation, use keyword-based scoring
        scored = []
        query_words = set(query.lower().split())
        
        for candidate in candidates:
            content = candidate.get('content', '').lower()
            # Simple keyword matching score
            content_words = set(content.split())
            overlap = len(query_words & content_words)
            score = overlap / max(len(query_words), 1)
            
            scored.append({
                'id': candidate.get('id', ''),
                'score': score,
                'content': candidate.get('content', ''),
                'type': candidate.get('type', ''),
                'source_agent': candidate.get('source_agent', '')
            })
        
        # Sort by score descending
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        # Return top-k
        return scored[:self.top_k]
    
    async def select_memories(
        self,
        debate_state: Dict[str, Any],
        memory_store: Any,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Select relevant memories from store for current debate state.
        
        Args:
            debate_state: Current state of the debate
            memory_store: MemoryStore instance
            top_k: Number of memories to select
        
        Returns:
            List of selected memory entries with scores
        """
        k = top_k or self.top_k
        
        # Build query from debate state
        query_parts = [
            debate_state.get('objective', ''),
            debate_state.get('current_agent', ''),
            str(debate_state.get('positions', {})),
            str(debate_state.get('arguments', []))
        ]
        query = " ".join(query_parts)
        
        # Get candidates from memory store
        recent = memory_store.get_recent(10)
        structured = memory_store.get_structured()
        
        candidates = []
        for entry in recent:
            candidates.append(entry.to_dict())
        for entry in structured:
            candidates.append(entry.to_dict())
        
        # Rerank
        return await self.rerank(query, candidates, top_k=k)
