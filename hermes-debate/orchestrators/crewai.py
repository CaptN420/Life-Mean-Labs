"""
CrewAI Orchestrator Adapter.

Adapter for CrewAI-based debate orchestration.
This adapter is OPTIONAL — the core system does not depend on it.
"""

import logging
from typing import Any, Optional

from .base import Orchestrator, OrchestratorResult, DebateState

logger = logging.getLogger(__name__)


class CrewAIOrchestrator(Orchestrator):
    """
    Orchestrator adapter for CrewAI.
    
    Uses CrewAI's agent framework to manage debate participants.
    This adapter is OPTIONAL — the core system does not depend on it.
    
    Requirements:
        pip install crewai
    
    Usage:
        orchestrator = CrewAIOrchestrator()
        result = await orchestrator.run(...)
    """
    
    def __init__(self, crew_config: Optional[dict] = None):
        """
        Initialize the CrewAI orchestrator.
        
        Args:
            crew_config: Configuration for the CrewAI crew
        """
        self.crew_config = crew_config or {}
        self._run_count = 0
        self._health_status = False
        self._crewai_available = False
        
        # Try to import crewai
        try:
            import crewai  # noqa: F401
            self._crewai_available = True
            logger.info("CrewAI available")
        except ImportError:
            logger.warning("CrewAI not installed. CrewAIOrchestrator will use fallback.")
        
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
        Run a debate using CrewAI.
        
        Args:
            question: The debate question
            personas: List of persona names
            protocol: Protocol to follow
            models: Mapping of persona to model_id
            decision_model: Optional decision model for routing
            max_turns: Maximum number of turns
            **kwargs: Additional parameters
            
        Returns:
            OrchestratorResult with final answer and metrics
        """
        self._run_count += 1
        
        # Fallback to mock if CrewAI not available
        if not self._crewai_available:
            logger.warning("CrewAI not available, using mock fallback")
            return await self._run_mock(question, personas, protocol, models, decision_model, max_turns, **kwargs)
        
        try:
            # Build the crew with agents
            from crewai import Crew, Agent, Task
            
            # Create agents for each persona
            agents = {}
            for persona in personas:
                model_id = models.get(persona, 'default_model')
                agents[persona] = Agent(
                    role=persona,
                    goal=f"Represent {persona} perspective",
                    backstory=f"You are an expert {persona}.",
                    model=model_id,
                )
            
            # Create tasks
            tasks = [
                Task(
                    description=f"Respond to the question: {question}",
                    agent=agents[personas[0]],
                    expected_output=f"Response from {personas[0]}",
                )
            ]
            
            # Create and run crew
            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                process="sequential",
            )
            
            result = await crew.kickoff()
            
            return OrchestratorResult(
                success=True,
                final_answer=str(result),
                consensus_reached=True,
                total_turns=1,
                metrics={'model_calls': len(personas)},
            )
            
        except Exception as e:
            logger.error(f"CrewAI orchestrator failed: {e}")
            return await self._run_mock(question, personas, protocol, models, decision_model, max_turns, **kwargs)
    
    async def health_check(self) -> bool:
        """Check if CrewAI is available."""
        try:
            import crewai  # noqa: F401
            self._health_status = True
        except ImportError:
            self._health_status = False
        return self._health_status
    
    async def get_orchestrator_info(self) -> dict[str, Any]:
        """Get CrewAI orchestrator metadata."""
        return {
            'id': 'crewai-orchestrator',
            'type': 'orchestrator',
            'provider': 'crewai',
            'version': '1.0.0',
            'run_count': self._run_count,
            'is_local': False,
            'crewai_available': self._crewai_available,
        }
    
    async def _run_mock(
        self,
        question: str,
        personas: list[str],
        protocol: str,
        models: dict[str, str],
        decision_model: Optional[Any] = None,
        max_turns: int = 8,
        **kwargs
    ) -> OrchestratorResult:
        """Fallback mock implementation."""
        from .base import MockOrchestrator
        
        mock = MockOrchestrator()
        return await mock.run(question, personas, protocol, models, decision_model, max_turns, **kwargs)
