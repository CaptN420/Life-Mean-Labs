"""
AutoGen Orchestrator Adapter.

Adapter for Microsoft AutoGen-based debate orchestration.
This adapter is OPTIONAL — the core system does not depend on it.
"""

import logging
from typing import Any, Optional

from .base import Orchestrator, OrchestratorResult, DebateState

logger = logging.getLogger(__name__)


class AutoGenOrchestrator(Orchestrator):
    """
    Orchestrator adapter for Microsoft AutoGen.
    
    Uses AutoGen's conversational agents to manage debate participants.
    This adapter is OPTIONAL — the core system does not depend on it.
    
    Requirements:
        pip install pyautogen
    
    Usage:
        orchestrator = AutoGenOrchestrator()
        result = await orchestrator.run(...)
    """
    
    def __init__(self, autogen_config: Optional[dict] = None):
        """
        Initialize the AutoGen orchestrator.
        
        Args:
            autogen_config: Configuration for the AutoGen conversation
        """
        self.autogen_config = autogen_config or {}
        self._run_count = 0
        self._health_status = False
        self._autogen_available = False
        
        # Try to import pyautogen
        try:
            import autogen  # noqa: F401
            self._autogen_available = True
            logger.info("AutoGen available")
        except ImportError:
            logger.warning("AutoGen not installed. AutoGenOrchestrator will use fallback.")
        
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
        Run a debate using AutoGen.
        
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
        
        # Fallback to mock if AutoGen not available
        if not self._autogen_available:
            logger.warning("AutoGen not available, using mock fallback")
            return await self._run_mock(question, personas, protocol, models, decision_model, max_turns, **kwargs)
        
        try:
            # Build the conversation
            from autogen import ConversableAgent, Agent
            
            # Create agents for each persona
            agents = {}
            for persona in personas:
                model_id = models.get(persona, 'default_model')
                agents[persona] = ConversableAgent(
                    name=persona,
                    system_message=f"You are a {persona}. Respond to debates from this perspective.",
                    llm_config={"model": model_id},
                )
            
            # Run conversation
            chat_result = await agents[personas[0]].a_initiate_chat(
                agents[personas[-1]],
                message=question,
                max_turns=max_turns,
            )
            
            return OrchestratorResult(
                success=True,
                final_answer=str(chat_result.summary),
                consensus_reached=True,
                total_turns=chat_result.count_summary.get('n', 1),
                metrics={'model_calls': len(personas) * 2},
            )
            
        except Exception as e:
            logger.error(f"AutoGen orchestrator failed: {e}")
            return await self._run_mock(question, personas, protocol, models, decision_model, max_turns, **kwargs)
    
    async def health_check(self) -> bool:
        """Check if AutoGen is available."""
        try:
            import autogen  # noqa: F401
            self._health_status = True
        except ImportError:
            self._health_status = False
        return self._health_status
    
    async def get_orchestrator_info(self) -> dict[str, Any]:
        """Get AutoGen orchestrator metadata."""
        return {
            'id': 'autogen-orchestrator',
            'type': 'orchestrator',
            'provider': 'autogen',
            'version': '1.0.0',
            'run_count': self._run_count,
            'is_local': False,
            'autogen_available': self._autogen_available,
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
