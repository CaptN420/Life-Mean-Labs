"""
Tests for Orchestrator infrastructure.

Tests cover:
- Orchestrator interface
- MockOrchestrator
- CustomOrchestrator
- Configuration
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrators.base import Orchestrator, OrchestratorResult, DebateState, MockOrchestrator
from orchestrators.custom import CustomOrchestrator
from orchestrators.langgraph import LangGraphOrchestrator
from orchestrators.crewai import CrewAIOrchestrator
from orchestrators.autogen import AutoGenOrchestrator


class TestDebateState:
    """Tests for DebateState."""
    
    def test_create_state(self):
        state = DebateState()
        assert state.turn_number == 0
        assert state.current_agent is None
        assert len(state.transcript) == 0
    
    def test_add_turn(self):
        state = DebateState()
        state.add_turn("philosopher", "I think...")
        assert state.turn_number == 1
        assert state.current_agent == "philosopher"
        assert len(state.transcript) == 1
    
    def test_add_multiple_turns(self):
        state = DebateState()
        state.add_turn("agent_a", "First argument")
        state.add_turn("agent_b", "Counter argument")
        state.add_turn("agent_a", "Rebuttal")
        
        assert state.turn_number == 3
        assert state.transcript[0]['agent'] == "agent_a"
        assert state.transcript[1]['agent'] == "agent_b"
        assert state.transcript[2]['agent'] == "agent_a"


class TestMockOrchestrator:
    """Tests for MockOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_run_returns_valid_result(self):
        orchestrator = MockOrchestrator()
        result = await orchestrator.run(
            question="What is life?",
            personas=["philosopher", "skeptic"],
            protocol="free_debate",
            models={"philosopher": "model_a", "skeptic": "model_b"},
        )
        
        assert result.success
        assert result.consensus_reached
        assert result.total_turns > 0
    
    @pytest.mark.asyncio
    async def test_health_check_always_true(self):
        orchestrator = MockOrchestrator()
        assert await orchestrator.health_check() is True
    
    @pytest.mark.asyncio
    async def test_get_orchestrator_info(self):
        orchestrator = MockOrchestrator()
        info = await orchestrator.get_orchestrator_info()
        
        assert info['id'] == "mock-orchestrator"
        assert info['type'] == "orchestrator"
        assert info['provider'] == "mock"


class TestCustomOrchestrator:
    """Tests for CustomOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_run_basic_debate(self):
        orchestrator = CustomOrchestrator()
        result = await orchestrator.run(
            question="What is the meaning of life?",
            personas=["philosopher", "skeptic"],
            protocol="cross_examination",
            models={"philosopher": "model_a", "skeptic": "model_b"},
            max_turns=4,
        )
        
        assert result.success
        assert len(result.final_answer) > 0
    
    @pytest.mark.asyncio
    async def test_run_with_decision_model(self):
        """Test with a mock decision model."""
        orchestrator = CustomOrchestrator()
        
        # Create a mock decision model
        mock_dm = MagicMock()
        mock_dm.decide = AsyncMock(return_value=MagicMock(selected_option="philosopher"))
        
        result = await orchestrator.run(
            question="What is truth?",
            personas=["philosopher", "skeptic"],
            protocol="structured",
            models={"philosopher": "model_a", "skeptic": "model_b"},
            decision_model=mock_dm,
            max_turns=3,
        )
        
        assert result.success
        # Verify decision model was called for each turn
        mock_dm.decide.assert_called()
        assert mock_dm.decide.call_count == 3
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        orchestrator = CustomOrchestrator()
        assert await orchestrator.health_check() is True
    
    @pytest.mark.asyncio
    async def test_get_orchestrator_info(self):
        orchestrator = CustomOrchestrator()
        info = await orchestrator.get_orchestrator_info()
        
        assert info['id'] == "custom-orchestrator"
        assert info['type'] == "orchestrator"
        assert info['provider'] == "custom"


class TestLangGraphOrchestrator:
    """Tests for LangGraphOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_init(self):
        orchestrator = LangGraphOrchestrator()
        assert orchestrator._langgraph_available is False  # Not installed in test env
    
    @pytest.mark.asyncio
    async def test_run_falls_back_to_mock(self):
        """Test that it falls back to mock when LangGraph not available."""
        orchestrator = LangGraphOrchestrator()
        result = await orchestrator.run(
            question="Test question",
            personas=["agent_a"],
            protocol="free_debate",
            models={"agent_a": "model_a"},
        )
        
        # Should fall back to mock and succeed
        assert result.success


class TestCrewAIOrchestrator:
    """Tests for CrewAIOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_init(self):
        orchestrator = CrewAIOrchestrator()
        assert orchestrator._crewai_available is False  # Not installed in test env
    
    @pytest.mark.asyncio
    async def test_run_falls_back_to_mock(self):
        """Test that it falls back to mock when CrewAI not available."""
        orchestrator = CrewAIOrchestrator()
        result = await orchestrator.run(
            question="Test question",
            personas=["agent_a"],
            protocol="free_debate",
            models={"agent_a": "model_a"},
        )
        
        # Should fall back to mock and succeed
        assert result.success


class TestAutoGenOrchestrator:
    """Tests for AutoGenOrchestrator."""
    
    @pytest.mark.asyncio
    async def test_init(self):
        orchestrator = AutoGenOrchestrator()
        assert orchestrator._autogen_available is False  # Not installed in test env
    
    @pytest.mark.asyncio
    async def test_run_falls_back_to_mock(self):
        """Test that it falls back to mock when AutoGen not available."""
        orchestrator = AutoGenOrchestrator()
        result = await orchestrator.run(
            question="Test question",
            personas=["agent_a"],
            protocol="free_debate",
            models={"agent_a": "model_a"},
        )
        
        # Should fall back to mock and succeed
        assert result.success


class TestOrchestratorInterchangeability:
    """Test that all orchestrators implement the same interface."""
    
    @pytest.mark.asyncio
    async def test_all_orchestrators_have_same_interface(self):
        """Verify all orchestrators have run, health_check, get_orchestrator_info."""
        orchestrators = [
            MockOrchestrator(),
            CustomOrchestrator(),
            LangGraphOrchestrator(),
            CrewAIOrchestrator(),
            AutoGenOrchestrator(),
        ]
        
        for orch in orchestrators:
            # Check interface methods exist
            assert hasattr(orch, 'run')
            assert hasattr(orch, 'health_check')
            assert hasattr(orch, 'get_orchestrator_info')
            
            # Check health check works
            health = await orch.health_check()
            assert isinstance(health, bool)
            
            # Check info returns dict
            info = await orch.get_orchestrator_info()
            assert isinstance(info, dict)


class TestExperimentScenarios:
    """Test realistic experiment scenarios."""
    
    @pytest.mark.asyncio
    async def test_persona_diversity_experiment(self):
        """Simulate Experiment 1: Persona Diversity."""
        orchestrator = CustomOrchestrator()
        
        # Run with 3 personas
        result_3 = await orchestrator.run(
            question="Should AI have rights?",
            personas=["philosopher", "scientist", "ethicist"],
            protocol="structured_debate",
            models={"philosopher": "model_a", "scientist": "model_b", "ethicist": "model_c"},
            max_turns=6,
        )
        
        # Run with 5 personas
        result_5 = await orchestrator.run(
            question="Should AI have rights?",
            personas=["philosopher", "scientist", "ethicist", "lawyer", "technologist"],
            protocol="structured_debate",
            models={p: f"model_{i}" for i, p in enumerate(["philosopher", "scientist", "ethicist", "lawyer", "technologist"])},
            max_turns=6,
        )
        
        # Compare metrics
        assert result_3.success
        assert result_5.success
        # More personas should lead to more turns (in mock)
        assert result_5.total_turns >= result_3.total_turns
    
    @pytest.mark.asyncio
    async def test_skeptic_ablation_experiment(self):
        """Simulate Experiment 2: Skeptic Ablation."""
        orchestrator = CustomOrchestrator()
        
        # Without Skeptic
        result_without = await orchestrator.run(
            question="Is free will an illusion?",
            personas=["philosopher", "scientist"],
            protocol="cross_examination",
            models={"philosopher": "model_a", "scientist": "model_b"},
            max_turns=6,
        )
        
        # With Skeptic
        result_with = await orchestrator.run(
            question="Is free will an illusion?",
            personas=["philosopher", "scientist", "skeptic"],
            protocol="cross_examination",
            models={"philosopher": "model_a", "scientist": "model_b", "skeptic": "model_c"},
            max_turns=6,
        )
        
        assert result_without.success
        assert result_with.success


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
