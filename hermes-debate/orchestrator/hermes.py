"""
Hermes Orchestrator - the central controller for multi-agent debate.
"""

import asyncio
import logging
import json
from typing import Optional, Any, Dict
from datetime import datetime

from ..models.state import DebateState, HermesResult, Action
from ..models.manager import ModelManager
from ..models.registry import ModelRegistry
from ..models.model_pool import ModelPool
from ..decision.clef import ClefDecisionEngine, FakeClefEngine
from ..agents.base import ReasoningAgent, CriticAgent, JudgeAgent, BaseAgent, AgentRole, AgentResponse
from ..debate.loop_detector import LoopDetector
from ..debate.consensus import ConsensusDetector
from ..debate.memory import MemoryPipeline
from ..debate.reranker import RerankerEngine, FakeRerankerEngine
from ..observability.logging import get_logger
from ..observability.metrics import get_metrics
from ..config import HermesConfig
from .request_queue import RequestQueue

logger = logging.getLogger(__name__)


class HermesOrchestrator:
    """
    Main orchestrator for multi-agent philosophical debate.

    Architecture:
    - Hermes: orchestration, policy, state management
    - CLEF: structured decisions (not content generation)
    - Reranker: context selection from memory
    - 27B Models: deep reasoning
    - ModelManager: VRAM lifecycle
    """

    def __init__(self, config: HermesConfig):
        self.config = config

        # Initialize components
        self.registry = ModelRegistry()
        self.request_queue = RequestQueue(max_concurrent=1)

        # Model pool for VRAM management — initialized after registry exists
        self.model_manager = ModelManager(
            registry=self.registry,
            backend=None,  # Will be set by backend-specific init
            config=config
        )
        self.model_pool = ModelPool(manager=self.model_manager)

        # Setup detectors
        self.loop_detector = LoopDetector(threshold=config.routing.loop_threshold)
        self.consensus_detector = ConsensusDetector(threshold=config.routing.consensus_threshold)

        # Initialize decision engine (fake or real)
        if config.simulation:
            logger.info("Running in SIMULATION mode")
            self.clef_engine = FakeClefEngine()
        else:
            from ..decision.clef import ClefDecisionEngine
            self.clef_engine = ClefDecisionEngine(
                account_id=config.clef_account_id or "",
                api_key=config.clef_api_key or "",
                endpoint=config.clef_endpoint
            )

        # Initialize reranker (fake for simulation)
        if config.simulation:
            self.reranker = FakeRerankerEngine()
        else:
            self.reranker = RerankerEngine(top_k=config.runtime.get('rerank_top_k', 3))

        # Memory pipeline
        self.memory = MemoryPipeline()

        # Observability
        self.logger = get_logger("hermes")
        self.metrics = get_metrics()

        # Initialize agents
        self.agents: dict[str, Any] = {}

        # Metrics tracking
        self.metrics_data = {
            'total_requests': 0,
            'clef_calls': 0,
            'model_swaps': 0,
            'loops_detected': 0,
            'consensus_reached': 0,
            'errors': 0,
        }

    async def run_debate(self, topic: str, max_turns: Optional[int] = None) -> Dict[str, Any]:
        """
        Run a debate on the given topic.

        Args:
            topic: The philosophical question or topic
            max_turns: Maximum number of turns (optional)

        Returns:
            Debate result dictionary
        """
        self.logger.info("Starting debate", extra={'topic': topic[:100]})

        # Initialize debate state
        state = DebateState(
            request=topic,
            objective=topic,
            max_turns=self.config.runtime.max_turns,
            available_agents=['model_a', 'model_b', 'judge'],
        )

        # Register default models if not already registered
        self._register_default_models()

        # Initialize agents
        self._initialize_agents()

        # Pre-load all models needed for this debate
        await self.model_pool.start_debate()
        model_ids_to_load = ['model_a', 'model_b']
        logger.info(f"Pre-loading models: {model_ids_to_load}")
        loaded_models = await self.model_pool.ensure_all_loaded(model_ids_to_load)
        logger.info(f"Models loaded: {loaded_models}")

        # Main debate loop
        while state.turn_number < state.max_turns and not state.final_answer_ready:
            logger.info(f"Turn {state.turn_number}/{state.max_turns}")

            # Check for loops
            if self.loop_detector.detect_loop(state):
                logger.warning("Loop detected")
                state.loop_detected = True
                self.metrics_data['loops_detected'] += 1
                self.metrics.increment('loop_count')

            # Check for consensus
            consensus_info = self.consensus_detector.detect_consensus(state)
            if consensus_info['consensus_reached']:
                logger.info(f"Consensus reached: {consensus_info['confidence']}")
                state.consensus = True
                state.consensus_confidence = consensus_info['confidence']
                self.metrics_data['consensus_reached'] += 1

            # Get allowed actions
            allowed_actions = self._get_allowed_actions(state)

            # Make decision using CLEF
            try:
                decision_data = await self.clef_engine.make_decision(
                    debate_state=state.to_dict(),
                    allowed_actions=allowed_actions,
                    previous_action=state.current_agent,
                )
                self.metrics_data['clef_calls'] += 1
                state.clef_decision = decision_data
                state.clef_confidence = decision_data.get('confidence', 0.0)

                # Validate and apply decision
                action = self._validate_action(
                    decision_data.get('next_action'),
                    allowed_actions,
                    state,
                )

            except Exception as e:
                logger.error(f"CLEF decision failed: {e}")
                action = self._fallback_action(state)

            # Execute the action
            if action == Action.END:
                state.final_answer_ready = True
                break

            elif action == Action.JUDGE:
                result = await self._run_judge(state)
                await self.model_pool.end_debate()
                await self.model_pool.cleanup()
                return HermesResult(
                    answer=result.content,
                    debate_state=state,
                    turns=list(state.recent_turns),
                    metrics=self.metrics_data,
                    status="completed",
                )

            elif action in [Action.MODEL_A.value, Action.MODEL_B.value]:
                await self._run_agent(state, action)
                self.metrics_data['total_requests'] = self.metrics_data.get('total_requests', 0) + 1

            elif action == 'bonsai':
                await self._run_agent(state, 'bonsai')
                self.metrics_data['total_requests'] = self.metrics_data.get('total_requests', 0) + 1

            elif action == 'savant':
                await self._run_agent(state, 'savant')
                self.metrics_data['total_requests'] = self.metrics_data.get('total_requests', 0) + 1

            elif action == Action.SYNTHESIZE:
                result = await self._synthesize(state)
                await self.model_pool.end_debate()
                await self.model_pool.cleanup()
                return HermesResult(
                    answer=result.content,
                    debate_state=state,
                    turns=list(state.recent_turns),
                    metrics=self.metrics_data,
                    status="completed",
                )

            else:
                logger.error(f"Unknown action: {action}")
                self.metrics_data['errors'] += 1

        # If we exhausted turns without conclusion, run judge
        if not state.final_answer_ready:
            result = await self._run_judge(state)
            await self.model_pool.end_debate()
            await self.model_pool.cleanup()
            return HermesResult(
                answer=result.content,
                debate_state=state,
                turns=list(state.recent_turns),
                metrics=self.metrics_data,
                status="completed",
            )

        # Return synthesized result
        await self.model_pool.end_debate()
        await self.model_pool.cleanup()
        return HermesResult(
            answer=self._synthesize_answer(state),
            debate_state=state,
            turns=list(state.recent_turns),
            metrics=self.metrics_data,
            status="completed",
        )

    def _register_default_models(self) -> None:
        """Register default models."""
        from ..config import ModelConfig

        # Register reasoning models
        self.registry.register('model_a', ModelConfig(
            model_id='model-a-27b',
            role='philosopher',
            vram_class='reasoning',
        ))

        self.registry.register('model_b', ModelConfig(
            model_id='model-b-27b',
            role='critic',
            vram_class='reasoning',
        ))

    def _initialize_agents(self) -> None:
        """Initialize debate agents."""
        from ..agents.rational import RationalAgent
        from ..agents.counter_position import CounterPositionAgent
        from ..agents.bonsai import BonsaiAgent
        from ..agents.savant import SavantAgent
        
        self.agents['model_a'] = RationalAgent('qwen35_4b')
        self.agents['model_b'] = CounterPositionAgent('gemma4_e4b')
        self.agents['bonsai'] = BonsaiAgent('bonsai_27b')
        self.agents['savant'] = SavantAgent('savant_commander')
        self.agents['judge'] = JudgeAgent('judge')

    def _get_allowed_actions(self, state: DebateState) -> list[str]:
        """Get allowed actions based on current state."""
        actions = [Action.MODEL_A.value, Action.MODEL_B.value]

        # Add escalation levels based on difficulty
        difficulty = state.metadata.get('difficulty_score', 0.0)
        if difficulty >= 0.7:
            actions.append('bonsai')
        if difficulty >= 0.9:
            actions.append('savant')

        # Add judge if enough turns or consensus
        if state.turn_number >= 2 or state.consensus or state.loop_detected:
            actions.append(Action.JUDGE.value)

        # Add synthesize at end
        if state.turn_number >= state.max_turns - 1:
            actions.append(Action.SYNTHESIZE.value)

        return actions

    async def _run_agent(self, state: DebateState, action: Action) -> None:
        """Run a reasoning agent with memory pipeline."""
        agent_id = action.value.lower()
        agent = self.agents.get(agent_id)

        if not agent:
            logger.error(f"Agent {agent_id} not found")
            return

        # Update state
        state.previous_agent = state.current_agent
        state.current_agent = agent_id

        # Generate prompt with memory context
        messages = await agent.format_prompt(state.objective, state.to_dict())

        # Run inference
        response = await agent.generate_response(
            prompt=state.request,
            debate_context={'turn_number': state.turn_number},
        )

        # Update state and memory
        state.add_turn(response)
        self.memory.add_turn(
            turn_number=response.turn_number,
            agent_id=response.agent_id,
            role=response.role.value,
            content=response.content,
        )

        logger.info(f"Agent {agent_id} responded: {response.content[:100]}...")

    async def _run_judge(self, state: DebateState) -> AgentResponse:
        """Run the judge to synthesize final answer."""
        judge = self.agents['judge']

        # Get structured memory for judge
        memory_context = self.memory.get_structured_memory()

        response = await judge.generate_response(
            prompt=f"Synthesize the debate on: {state.request}",
            debate_context={
                'turn_number': state.turn_number,
                'memory': memory_context,
            },
        )

        return response

    async def _synthesize(self, state: DebateState) -> Any:
        """Synthesize the debate into a final answer."""
        return await self._run_judge(state)

    def _validate_action(
        self,
        action_value: str,
        allowed_actions: list[str],
        state: Optional[DebateState] = None,
    ) -> Action:
        """Validate and convert action to enum."""
        try:
            action = Action(action_value)
            if action.value not in allowed_actions:
                logger.warning(f"Action {action_value} not allowed, using fallback")
                return self._fallback_action(state)
            return action
        except ValueError:
            logger.warning(f"Invalid action: {action_value}")
            return self._fallback_action(state)

    def _fallback_action(self, state: Optional[DebateState] = None) -> Action:
        """Determine fallback action when CLEF is unavailable."""
        if state and state.current_agent == 'model_a':
            return Action.MODEL_B
        elif state and state.current_agent == 'model_b':
            return Action.MODEL_A
        elif state and state.turn_number >= state.max_turns:
            return Action.JUDGE
        else:
            return Action.MODEL_A

    def _synthesize_answer(self, state: DebateState) -> str:
        """Synthesize a final answer from the debate."""
        return f"""Debate on: {state.request}

Summary:
- Turns: {state.turn_number}
- Consensus: {state.consensus}
- Loop detected: {state.loop_detected}

Final synthesis would be generated here based on the debate content."""

    async def run(self, user_input: str) -> Dict[str, Any]:
        """
        Run a debate (backward compatibility alias for run_debate).
        
        Args:
            user_input: The philosophical question or topic
            
        Returns:
            Debate result dictionary
        """
        return await self.run_debate(user_input)
