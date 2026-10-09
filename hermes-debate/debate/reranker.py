"""
Reranker engine for selecting relevant context from debate memory.
Uses local models (Qwen3-Reranker-0.6B, Jev-0.8B) or simulation.
"""

import logging
from typing import Optional
from dataclasses import dataclass, field
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Result from reranking operation."""
    selected_segments: list[dict] = field(default_factory=list)
    top_k: int = 3
    query: str = ""
    total_documents: int = 0
    latency_ms: float = 0.0

    @property
    def context_text(self) -> str:
        """Get formatted context text from selected segments."""
        if not self.selected_segments:
            return "No relevant context found."

        lines = []
        for seg in self.selected_segments:
            lines.append(f"[{seg['agent_id']}] {seg['content'][:200]}...")
        return "\n".join(lines)


class RerankerEngine:
    """
    Reranker for selecting relevant debate context.

    Supports:
    - Qwen3-Reranker-0.6B
    - Jev-0.8B (future)
    - Simulation mode for testing
    """

    def __init__(self, model_name: str = "qwen3-reranker-0.6b", top_k: int = 3):
        self.model_name = model_name
        self.top_k = top_k
        self._loaded = False
        self._simulation_mode = True

    async def load(self) -> bool:
        """Load the reranker model."""
        # In simulation mode, just mark as loaded
        if self._simulation_mode:
            self._loaded = True
            return True

        # Real implementation would load model here
        logger.info(f"Loading reranker model: {self.model_name}")
        self._loaded = True
        return True

    async def unload(self) -> bool:
        """Unload the reranker model."""
        self._loaded = False
        return True

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
    ) -> RerankResult:
        """
        Rerank documents based on relevance to query.

        Args:
            query: The search query (agent role + last intervention + objective)
            documents: List of debate memory segments
            top_k: Number of top results to return

        Returns:
            RerankResult with selected segments
        """
        import time
        start_time = time.perf_counter()

        if not documents:
            return RerankResult(
                selected_segments=[],
                top_k=top_k or self.top_k,
                query=query,
                total_documents=0,
            )

        # In simulation mode, use heuristic scoring
        if self._simulation_mode:
            selected = self._simulate_rerank(query, documents, top_k)
        else:
            selected = await self._real_rerank(query, documents, top_k)

        latency_ms = (time.perf_counter() - start_time) * 1000

        return RerankResult(
            selected_segments=selected,
            top_k=top_k or self.top_k,
            query=query,
            total_documents=len(documents),
            latency_ms=latency_ms,
        )

    def _simulate_rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """Simulate reranking with heuristic scoring."""
        # Simple keyword-based relevance scoring
        query_terms = set(query.lower().split())

        scored = []
        for doc in documents:
            content = doc.get('content', '').lower()
            score = sum(1 for term in query_terms if term in content)
            scored.append({**doc, '_score': score})

        # Sort by score and return top_k
        scored.sort(key=lambda x: x['_score'], reverse=True)
        return scored[:top_k or self.top_k]

    async def _real_rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """Real reranking using the model."""
        # This would use the actual reranker model
        raise NotImplementedError("Real reranker not implemented yet")

    @property
    def is_loaded(self) -> bool:
        """Check if reranker is loaded."""
        return self._loaded


class FakeRerankerEngine(RerankerEngine):
    """Fake reranker for simulation mode."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._simulation_mode = True

    async def rerank(self, query: str, documents: list[dict], top_k: Optional[int] = None) -> RerankResult:
        """Return simulated reranking results."""
        import random
        k = top_k or self.top_k
        selected = random.sample(documents, min(k, len(documents))) if documents else []
        return RerankResult(
            selected_segments=selected,
            top_k=k,
            query=query,
            total_documents=len(documents),
            latency_ms=10.0,
        )
