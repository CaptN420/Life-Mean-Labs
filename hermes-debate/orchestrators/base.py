"""
Orchestrator Base Interface.

All orchestrators must implement this interface.
The scientific model treats orchestrators as interchangeable
experimental variables — never hardcode dependencies on specific
frameworks (LangGraph, CrewAI, AutoGen).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class DebateState:
    """Current state of the debate."""
    
    turn_number: int = 0
    current_agent: Optional[str] = None
    previous_agent: Optional[str] = None
    transcript: list[dict] = field(default_factory=list)
    consensus: bool = False
    loop_detected: bool = False
    metadata: dict = field(default_factory=dict)
    
    def add_turn(self, agent: str, content: str, metadata: Optional[dict] = None) -> None:
        """Add a turn to the transcript."""
        self.transcript.append({
            'turn': self.turn_number,
            'agent': agent,
            'content': content,
            'timestamp': datetime.utcnow().isoformat(),
            'metadata': metadata or {},
        })
        self.previous_agent = self.current_agent
        self.current_agent = agent
        self.turn_number += 1


@dataclass
class OrchestratorResult:
    """Result from an orchestrator run."""
    
    success: bool
    final_answer: str
    consensus_reached: bool = False
    total_turns: int = 0
    metrics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    raw_state: Optional[DebateState] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class Orchestrator(ABC):
    """
    Abstract base class for debate orchestrators.
    
    Orchestrators manage the flow of multi-agent debates.
    They are considered experimental variables — the scientific
    model should not depend on any specific implementation.
    
    Supported implementations:
    - CustomOrchestrator: Native Python implementation
    - LangGraphOrchestrator: Adapter for LangGraph
    - CrewAIOrchestrator: Adapter for CrewAI
    - AutoGenOrchestrator: Adapter for AutoGen
    """
    
    @abstractmethod
    async def run(
        self,
        question: str,
        personas: list[str],
        protocol: str,
        models: dict[str, str],
        decision_model: Optional[Any] = None,
        max_turns: int = 8,
        **kwargs: Any
    ) -> OrchestratorResult:
        """
        Run a debate experiment.
        
        Args:
            question: The debate question
            personas: List of persona names
            protocol: Protocol to follow (e.g., "cross_examination")
            models: Mapping of persona to model_id
            decision_model: Optional decision model for routing
            max_turns: Maximum number of turns
            **kwargs: Additional parameters
            
        Returns:
            OrchestratorResult with final answer and metrics
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the orchestrator is available and healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        ...
    
    @abstractmethod
    async def get_orchestrator_info(self) -> dict[str, Any]:
        """
        Get metadata about the orchestrator.
        
        Returns:
            Dictionary with orchestrator information
        """
        ...


class MockOrchestrator(Orchestrator):
    """
    Mock orchestrator for testing without real agents.
    
    Simulates debate flow with deterministic responses.
    Useful for CI/CD and unit tests.
    """
    
    def __init__(self, delay_ms: int = 100):
        self.delay_ms = delay_ms
        self._run_count = 0
        
    async def run(
        self,
        question: str,
        personas: list[str],
        protocol: str,
        models: dict[str, str],
        decision_model: Optional[Any] = None,
        max_turns: int = 8,
        **kwargs: Any
    ) -> OrchestratorResult:
        """Simulate a debate run."""
        self._run_count += 1
        
        # Simulate turns
        transcript = []
        for turn in range(min(3, max_turns)):
            agent = personas[turn % len(personas)]
            transcript.append({
                'turn': turn,
                'agent': agent,
                'content': f"Simulated response from {agent} on: {question[:50]}...",
                'timestamp': datetime.utcnow().isoformat(),
            })
        
        return OrchestratorResult(
            success=True,
            final_answer=f"Simulated consensus on: {question}",
            consensus_reached=True,
            total_turns=len(transcript),
            metrics={
                'model_calls': len(transcript) * 2,
                'decision_calls': len(transcript),
                'avg_latency_ms': self.delay_ms,
            },
            raw_state=DebateState(
                turn_number=len(transcript),
                transcript=transcript,
                consensus=True,
            ),
        )
    
    async def health_check(self) -> bool:
        """Mock orchestrator is always healthy."""
        return True
    
    async def get_orchestrator_info(self) -> dict[str, Any]:
        """Return mock orchestrator info."""
        return {
            'id': 'mock-orchestrator',
            'type': 'orchestrator',
            'provider': 'mock',
            'version': '1.0.0',
            'run_count': self._run_count,
            'is_local': True,
        }
