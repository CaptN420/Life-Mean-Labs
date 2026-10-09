"""
LangGraph Orchestrator Adapter.

Adapter for LangGraph-based debate orchestration.
This adapter is independent of the core scientific model —
it can be swapped out without affecting experiments.
"""

import logging
from typing import Any, Optional

from .base import Orchestrator, OrchestratorResult, DebateState

logger = logging.getLogger(__name__)


class LangGraphOrchestrator(Orchestrator):
    """
    Orchestrator adapter for LangGraph.
    
    Uses LangGraph's state machine capabilities to manage debate flow.
    This adapter is OPTIONAL — the core system does not depend on it.
    
    Requirements:
        pip install langgraph
    
    Usage:
        orchestrator = LangGraphOrchestrator()
        result = await orchestrator.run(...)
    """
    
    def __init__(self, graph_config: Optional[dict] = None):
        """
        Initialize the LangGraph orchestrator.
        
        Args:
            graph_config: Configuration for the LangGraph state graph
        """
        self.graph_config = graph_config or {}
        self._run_count = 0
        self._health_status = False
        self._langgraph_available = False
        
        # Try to import langgraph
        try:
            import langgraph  # noqa: F401
            self._langgraph_available = True
            logger.info("LangGraph available")
        except ImportError:
            logger.warning("LangGraph not installed. LangGraphOrchestrator will use fallback.")
        
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
        Run a debate using LangGraph.
        
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
        
        # Fallback to mock if LangGraph not available
        if not self._langgraph_available:
            logger.warning("LangGraph not available, using mock fallback")
            return await self._run_mock(question, personas, protocol, models, decision_model, max_turns, **kwargs)
        
        try:
            # Build the debate graph
            from langgraph.graph import StateGraph, START, END
            
            # Define state schema
            class DebateState:
                turns: list[dict]
                current_agent: str
                consensus: bool
                loop_detected: bool
            
            # Create graph
            graph = StateGraph(DebateState)
            
            # Add nodes
            graph.add_node("select_agent", self._select_agent_node)
            graph.add_node("generate_response", self._generate_response_node)
            graph.add_node("check_consensus", self._check_consensus_node)
            
            # Add edges
            graph.add_edge(START, "select_agent")
            graph.add_edge("select_agent", "generate_response")
            graph.add_edge("generate_response", "check_consensus")
            graph.add_conditional_edges(
                "check_consensus",
                self._should_continue,
                {True: "select_agent", False: END}
            )
            
            # Compile and run
            app = graph.compile()
            initial_state = {
                'turns': [],
                'current_agent': personas[0],
                'consensus': False,
                'loop_detected': False,
            }
            
            result = await app.ainvoke(initial_state)
            
            return OrchestratorResult(
                success=True,
                final_answer=self._synthesize_from_state(result),
                consensus_reached=result.get('consensus', False),
                total_turns=len(result.get('turns', [])),
                metrics={'model_calls': len(result.get('turns', []))},
            )
            
        except Exception as e:
            logger.error(f"LangGraph orchestrator failed: {e}")
            return await self._run_mock(question, personas, protocol, models, decision_model, max_turns, **kwargs)
    
    async def health_check(self) -> bool:
        """Check if LangGraph is available."""
        try:
            import langgraph  # noqa: F401
            self._health_status = True
        except ImportError:
            self._health_status = False
        return self._health_status
    
    async def get_orchestrator_info(self) -> dict[str, Any]:
        """Get LangGraph orchestrator metadata."""
        return {
            'id': 'langgraph-orchestrator',
            'type': 'orchestrator',
            'provider': 'langgraph',
            'version': '1.0.0',
            'run_count': self._run_count,
            'is_local': False,
            'langgraph_available': self._langgraph_available,
        }
    
    async def _select_agent_node(self, state: dict) -> dict:
        """Select next agent based on protocol or decision model."""
        # This would use the decision model in production
        return {'current_agent': 'mock_agent'}
    
    async def _generate_response_node(self, state: dict) -> dict:
        """Generate response from selected agent."""
        # This would call the actual model in production
        return {'turns': [{'agent': 'mock_agent', 'content': 'Mock response'}]}
    
    async def _check_consensus_node(self, state: dict) -> dict:
        """Check if consensus has been reached."""
        return {'consensus': False}
    
    def _should_continue(self, state: dict) -> str:
        """Determine if debate should continue."""
        return 'yes' if not state.get('consensus', False) else 'no'
    
    def _synthesize_from_state(self, state: dict) -> str:
        """Synthesize final answer from graph state."""
        turns = state.get('turns', [])
        if not turns:
            return "No debate took place."
        return " ".join([t['content'] for t in turns[-3:]])
    
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
