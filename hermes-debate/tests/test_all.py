"""
Tests for Hermes Multi-Agent Debate Orchestrator.
"""

import pytest
import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Optional

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hermes_debate.models.state import DebateState, Action, ModelStatus, AgentResponse, AgentRole, HermesResult
from hermes_debate.models.registry import ModelRegistry, ModelEntry
from hermes_debate.models.manager import ModelManager
from hermes_debate.models.backends.base import FakeInferenceBackend
from hermes_debate.config import HermesConfig, ModelConfig
from hermes_debate.decision.clef import ClefDecisionEngine, FakeClefEngine
from hermes_debate.agents.base import ReasoningAgent, CriticAgent, JudgeAgent, BaseAgent
from hermes_debate.debate.loop_detector import LoopDetector
from hermes_debate.debate.consensus import ConsensusDetector
from hermes_debate.orchestrator.hermes import HermesOrchestrator


class TestDebateState:
    """Tests for DebateState."""
    
    def test_create_state(self):
        """Test creating a basic debate state."""
        state = DebateState(
            request="What is the meaning of life?",
            objective="Explore the meaning of life",
            max_turns=8
        )
        
        assert state.request == "What is the meaning of life?"
        assert state.turn_number == 0
        assert state.max_turns == 8
    
    def test_add_turn(self):
        """Test adding turns to the debate."""
        state = DebateState(request="Test")
        
        response = AgentResponse(
            agent_id="model_a",
            role=AgentRole.PHILOSOPHER,
            content="I think life has no inherent meaning.",
            turn_number=1
        )
        
        state.add_turn(response)
        
        assert state.turn_number == 1
        assert len(state.recent_turns) == 1
        assert state.recent_turns[0].agent_id == "model_a"
    
    def test_detect_loop(self):
        """Test loop detection."""
        state = DebateState(request="Test", max_turns=8)
        
        # Add alternating turns
        for i in range(6):
            agent_id = "model_a" if i % 2 == 0 else "model_b"
            response = AgentResponse(
                agent_id=agent_id,
                role=AgentRole.PHILOSOPHER,
                content=f"Argument {i}",
                turn_number=i + 1
            )
            state.add_turn(response)
        
        # Should detect loop after enough turns
        assert state.detect_loop() == True


class TestModelRegistry:
    """Tests for ModelRegistry."""
    
    def test_register_model(self):
        """Test registering a model."""
        registry = ModelRegistry()
        
        config = ModelConfig(
            model_id="test-model",
            role="philosopher",
            vram_class="reasoning"
        )
        
        registry.register("model_a", config)
        
        entry = registry.get("model_a")
        assert entry is not None
        assert entry.config.model_id == "test-model"
    
    def test_list_models(self):
        """Test listing all models."""
        registry = ModelRegistry()
        
        registry.register("clef", ModelConfig(
            model_id="clef",
            role="decision_model",
            vram_class="decision"
        ))
        
        registry.register("model_a", ModelConfig(
            model_id="model-a",
            role="philosopher",
            vram_class="reasoning"
        ))
        
        models = registry.list_models()
        assert len(models) == 2
        assert "clef" in models
        assert "model_a" in models
    
    def test_get_by_role(self):
        """Test getting models by role."""
        registry = ModelRegistry()
        
        registry.register("clef", ModelConfig(
            model_id="clef",
            role="decision_model",
            vram_class="decision"
        ))
        
        registry.register("model_a", ModelConfig(
            model_id="model-a",
            role="philosopher",
            vram_class="reasoning"
        ))
        
        decision_models = registry.get_by_role("decision_model")
        assert len(decision_models) == 1
        assert decision_models[0].config.model_id == "clef"


class TestModelManager:
    """Tests for ModelManager."""
    
    @pytest.mark.asyncio
    async def test_load_and_unload(self):
        """Test loading and unloading models."""
        config = HermesConfig(simulation=True)
        backend = FakeInferenceBackend()
        registry = ModelRegistry()
        
        registry.register("model_a", ModelConfig(
            model_id="model-a",
            role="philosopher",
            vram_class="reasoning"
        ))
        
        manager = ModelManager(registry, backend, config)
        
        # Load model
        success = await manager.load_model("model_a")
        assert success == True
        assert await manager.get_status("model_a") == "READY"

        # Unload model
        success = await manager.unload_model("model_a")
        assert success == True
        assert await manager.get_status("model_a") == "UNLOADED"
    
    @pytest.mark.asyncio
    async def test_switch_model(self):
        """Test switching between models."""
        config = HermesConfig(simulation=True)
        backend = FakeInferenceBackend()
        registry = ModelRegistry()
        
        registry.register("model_a", ModelConfig(
            model_id="model-a",
            role="philosopher",
            vram_class="reasoning"
        ))
        
        registry.register("model_b", ModelConfig(
            model_id="model-b",
            role="critic",
            vram_class="reasoning"
        ))
        
        manager = ModelManager(registry, backend, config)
        
        # Load model_a
        await manager.load_model("model_a")

        # Switch to model_b
        success = await manager.switch_model("model_a", "model_b")
        assert success == True
        assert await manager.get_status("model_a") == "UNLOADED"
        assert await manager.get_status("model_b") == "READY"


class TestClefDecisionEngine:
    """Tests for CLEF Decision Engine."""
    
    @pytest.mark.asyncio
    async def test_fake_clef_decision(self):
        """Test fake CLEF decision engine."""
        engine = FakeClefEngine()
        
        debate_state = {
            'turn_number': 2,
            'max_turns': 8
        }
        
        decision = await engine.make_decision(
            debate_state=debate_state,
            allowed_actions=['MODEL_A', 'MODEL_B', 'JUDGE']
        )
        
        assert 'next_action' in decision
        assert decision['confidence'] > 0
        assert isinstance(decision['consensus_reached'], bool)
    
    def test_decision_validation(self):
        """Test decision validation."""
        from hermes_debate.decision.clef import ClefDecisionEngine
        
        engine = ClefDecisionEngine(
            account_id="test",
            api_key="test"
        )
        
        # Valid decision
        decision = engine._validate_decision({
            'answers': {
                'next_action': {'selected': 'MODEL_A', 'probabilities': {'MODEL_A': 0.9}}
            }
        }, ['MODEL_A', 'MODEL_B'])
        
        assert decision['next_action'] == 'MODEL_A'
        assert decision['confidence'] == 0.9
        
        # Invalid decision (should default to END)
        decision = engine._validate_decision({
            'answers': {
                'next_action': {'selected': 'INVALID', 'probabilities': {}}
            }
        }, ['MODEL_A', 'MODEL_B'])
        
        assert decision['next_action'] == 'END'


class TestLoopDetector:
    """Tests for Loop Detector."""
    
    def test_no_loop_yet(self):
        """Test that loop is not detected with few turns."""
        detector = LoopDetector(threshold=3)
        state = DebateState(request="Test")
        
        # Add only 2 turns
        for i in range(2):
            response = AgentResponse(
                agent_id="model_a",
                role=AgentRole.PHILOSOPHER,
                content=f"Argument {i}",
                turn_number=i + 1
            )
            state.add_turn(response)
        
        assert detector.detect_loop(state) == False
    
    def test_detect_alternating_loop(self):
        """Test detecting alternating pattern."""
        detector = LoopDetector(threshold=3)
        state = DebateState(request="Test")
        
        # Add 6 alternating turns
        for i in range(6):
            agent_id = "model_a" if i % 2 == 0 else "model_b"
            response = AgentResponse(
                agent_id=agent_id,
                role=AgentRole.PHILOSOPHER,
                content=f"Argument {i}",
                turn_number=i + 1
            )
            state.add_turn(response)
        
        assert detector.detect_loop(state) == True


class TestConsensusDetector:
    """Tests for Consensus Detector."""
    
    def test_no_consensus_yet(self):
        """Test that consensus is not detected with few turns."""
        detector = ConsensusDetector()
        state = DebateState(request="Test")
        
        # Add only 1 turn
        response = AgentResponse(
            agent_id="model_a",
            role=AgentRole.PHILOSOPHER,
            content="I think life has meaning.",
            turn_number=1
        )
        state.add_turn(response)
        
        result = detector.detect_consensus(state)
        assert result['consensus_reached'] == False
    
    def test_detect_identical_positions(self):
        """Test detecting consensus from identical positions."""
        detector = ConsensusDetector()
        state = DebateState(request="Test")
        # Add some turns so the detector doesn't bail out early
        from hermes_debate.models.state import AgentResponse, AgentRole
        for i in range(2):
            state.add_turn(AgentResponse(
                agent_id=f"model_{i}",
                role=AgentRole.PHILOSOPHER,
                content="I think life has meaning.",
                turn_number=i + 1
            ))
        state.positions = {
            'model_a': 'Life has inherent meaning',
            'model_b': 'Life has inherent meaning'
        }

        result = detector.detect_consensus(state)
        assert result['consensus_reached'] == True
        assert result['confidence'] > 0.9


class TestOrchestrator:
    """Tests for Hermes Orchestrator."""
    
    @pytest.mark.asyncio
    async def test_run_debate_simulation(self):
        """Test running a debate in simulation mode."""
        config = HermesConfig(simulation=True)
        orchestrator = HermesOrchestrator(config)
        
        result = await orchestrator.run("What is the meaning of life?")
        
        assert isinstance(result, HermesResult)
        assert result.success == True
        assert len(result.turns) > 0
        assert 'answer' in result.__dict__
    
    @pytest.mark.asyncio
    async def test_orchestrator_metrics(self):
        """Test that metrics are tracked."""
        config = HermesConfig(simulation=True)
        orchestrator = HermesOrchestrator(config)

        await orchestrator.run("Test debate")

        assert orchestrator.metrics_data['total_requests'] >= 1
        assert 'clef_calls' in orchestrator.metrics_data


class TestActionEnum:
    """Tests for Action enum."""
    
    def test_action_values(self):
        """Test that all actions have valid values."""
        assert Action.MODEL_A.value == "MODEL_A"
        assert Action.MODEL_B.value == "MODEL_B"
        assert Action.JUDGE.value == "JUDGE"
        assert Action.SYNTHESIZE.value == "SYNTHESIZE"
        assert Action.END.value == "END"


class TestAgentBase:
    """Tests for Base Agent."""
    
    def test_create_reasoning_agent(self):
        """Test creating a reasoning agent."""
        agent = ReasoningAgent("model_a", AgentRole.PHILOSOPHER)
        
        assert agent.agent_id == "model_a"
        assert agent.role == AgentRole.PHILOSOPHER
    
    @pytest.mark.asyncio
    async def test_agent_response(self):
        """Test agent response generation."""
        agent = ReasoningAgent("model_a", AgentRole.PHILOSOPHER)
        
        response = await agent.generate_response(
            prompt="What is meaning?",
            debate_context={'turn_number': 1}
        )
        
        assert response.agent_id == "model_a"
        assert response.role == AgentRole.PHILOSOPHER
        assert len(response.content) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
