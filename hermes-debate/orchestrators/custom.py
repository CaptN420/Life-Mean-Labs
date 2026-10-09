"""
Custom Orchestrator — Native Python implementation.

This is the default orchestrator that does not depend on any
external framework (LangGraph, CrewAI, AutoGen). It provides
full control over the debate flow and is suitable for:
- Research experiments
- Controlled studies
- Reproducibility requirements
"""

import logging
from typing import Any, Optional

from .base import Orchestrator, OrchestratorResult, DebateState

logger = logging.getLogger(__name__)


class CustomOrchestrator(Orchestrator):
    """
    Native Python orchestrator for multi-agent debates.
    
    This orchestrator implements the debate protocol directly in Python
    without depending on external frameworks. It provides:
    - Full control over debate flow
    - Deterministic behavior for reproducibility
    - No external dependencies (except decision models)
    - Complete observability and logging
    
    Usage:
        orchestrator = CustomOrchestrator()
        result = await orchestrator.run(
            question="What is the meaning of life?",
            personas=["philosopher", "skeptic", "scientist"],
            protocol="cross_examination",
            models={"philosopher": "model_a", "skeptic": "model_b"},
            decision_model=decision_model,
        )
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the custom orchestrator.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._run_count = 0
        self._health_status = True
        
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
        Run a debate experiment using the custom orchestrator.
        
        Args:
            question: The debate question
            personas: List of persona names
            protocol: Protocol to follow
            models: Mapping of persona to model_id
            decision_model: Optional decision model for routing
            max_turns: Maximum number of turns
            **kwargs: Additional parameters (temperature, etc.)
            
        Returns:
            OrchestratorResult with final answer and metrics
        """
        self._run_count += 1
        
        # Initialize debate state
        state = DebateState()
        state.metadata['question'] = question
        state.metadata['protocol'] = protocol
        state.metadata['personas'] = personas
        
        # Track metrics
        metrics = {
            'model_calls': 0,
            'decision_calls': 0,
            'errors': [],
            'latencies': [],
        }
        
        try:
            # Run debate loop
            for turn in range(max_turns):
                # Get decision from decision model if available
                selected_agent = None
                if decision_model:
                    try:
                        options = personas.copy()
                        decision = await decision_model.decide(
                            options=options,
                            context={'debate_state': state.__dict__}
                        )
                        selected_agent = decision.selected_option
                        metrics['decision_calls'] += 1
                        logger.info(f"Decision model selected: {selected_agent}")
                    except Exception as e:
                        logger.error(f"Decision model failed: {e}")
                        metrics['errors'].append(f"Decision error: {str(e)}")
                        selected_agent = personas[turn % len(personas)]
                else:
                    # Round-robin if no decision model
                    selected_agent = personas[turn % len(personas)]
                
                # Generate response from selected agent's model
                model_id = models.get(selected_agent, 'default_model')
                try:
                    # This would call the actual model in production
                    # For now, simulate with mock
                    response = await self._generate_response(
                        agent=selected_agent,
                        model_id=model_id,
                        question=question,
                        context=state.transcript,
                        **kwargs
                    )
                    metrics['model_calls'] += 1
                    
                    # Add to transcript
                    state.add_turn(selected_agent, response)
                    
                except Exception as e:
                    logger.error(f"Model generation failed for {selected_agent}: {e}")
                    metrics['errors'].append(f"Model error: {str(e)}")
                    continue
            
            # Detect consensus or loop
            state.consensus = self._detect_consensus(state)
            state.loop_detected = self._detect_loop(state)
            
            return OrchestratorResult(
                success=True,
                final_answer=self._synthesize_answer(state),
                consensus_reached=state.consensus,
                total_turns=state.turn_number,
                metrics=metrics,
                raw_state=state,
            )
            
        except Exception as e:
            logger.error(f"Orchestrator run failed: {e}")
            return OrchestratorResult(
                success=False,
                final_answer="",
                errors=[str(e)],
                metrics=metrics,
            )
    
    async def health_check(self) -> bool:
        """Check if the orchestrator is healthy."""
        return self._health_status
    
    async def get_orchestrator_info(self) -> dict[str, Any]:
        """Get orchestrator metadata."""
        return {
            'id': 'custom-orchestrator',
            'type': 'orchestrator',
            'provider': 'custom',
            'version': '1.0.0',
            'run_count': self._run_count,
            'is_local': True,
            'capabilities': [
                'routing',
                'protocol_execution',
                'consensus_detection',
                'loop_detection',
            ],
        }
    
    async def _generate_response(
        self,
        agent: str,
        model_id: str,
        question: str,
        context: list[dict],
        **kwargs
    ) -> str:
        """
        Generate a response from the selected agent.
        
        In production, this would call the actual model.
        For now, returns a simulated response.
        """
        # Simulated response for testing
        return f"[{agent}] Response to '{question[:50]}...' based on context."
    
    def _detect_consensus(self, state: DebateState) -> bool:
        """Detect if consensus has been reached."""
        if len(state.transcript) < 2:
            return False
        
        # Simple heuristic: check if last 3 turns have similar agents
        recent_agents = [t['agent'] for t in state.transcript[-3:]]
        return len(set(recent_agents)) == 1
    
    def _detect_loop(self, state: DebateState) -> bool:
        """Detect if the debate is looping."""
        if len(state.transcript) < 4:
            return False
        
        # Check for repeating pattern
        recent = [t['agent'] for t in state.transcript[-4:]]
        return recent[0] == recent[2] and recent[1] == recent[3]
    
    def _synthesize_answer(self, state: DebateState) -> str:
        """Synthesize a final answer from the debate."""
        if not state.transcript:
            return "No debate took place."
        
        # Simple synthesis: concatenate last few turns
        last_turns = state.transcript[-3:]
        answers = [t['content'] for t in last_turns]
        return " ".join(answers)
