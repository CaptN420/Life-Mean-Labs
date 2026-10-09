"""
Tests for Decision Model infrastructure.

Tests cover:
- DecisionModel interface
- MockDecisionModel
- LMStudioDecisionModel (mocked)
- StrandsDecider2B
- Configuration
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from models.decision_models.base import DecisionModel, DecisionResult, MockDecisionModel
from models.decision_models.lmstudio import LMStudioDecisionModel
from models.decision_models.strands_decider import StrandsDecider2B
from config import DecisionModelConfig


class TestDecisionResult:
    """Tests for DecisionResult dataclass."""
    
    def test_valid_decision(self):
        result = DecisionResult(
            selected_option="agent_01",
            confidence=0.85,
            reasoning="Best option",
            raw_response='{"decision": "agent_01"}',
        )
        assert result.is_valid
        assert result.selected_option == "agent_01"
        assert result.confidence == 0.85
    
    def test_invalid_option_empty(self):
        result = DecisionResult(
            selected_option="",
            confidence=0.5,
            reasoning="Test",
            raw_response="{}",
        )
        assert not result.is_valid
    
    def test_invalid_confidence_too_high(self):
        result = DecisionResult(
            selected_option="agent_01",
            confidence=1.5,  # Invalid
            reasoning="Test",
            raw_response="{}",
        )
        assert not result.is_valid
    
    def test_timestamp_auto_generated(self):
        before = datetime.utcnow()
        result = DecisionResult(
            selected_option="agent_01",
            confidence=0.5,
            reasoning="Test",
            raw_response="{}",
        )
        after = datetime.utcnow()
        assert before <= result.timestamp <= after


class TestMockDecisionModel:
    """Tests for MockDecisionModel."""
    
    @pytest.mark.asyncio
    async def test_decide_returns_valid_result(self):
        model = MockDecisionModel(seed=42)
        result = await model.decide(
            options=["agent_01", "agent_02", "agent_03"],
            context={"debate_state": {"turn_number": 1}}
        )
        assert result.is_valid
        assert result.selected_option in ["agent_01", "agent_02", "agent_03"]
        assert 0.0 <= result.confidence <= 1.0
    
    @pytest.mark.asyncio
    async def test_decide_empty_options_raises(self):
        model = MockDecisionModel()
        with pytest.raises(ValueError, match="Options list cannot be empty"):
            await model.decide(options=[], context={})
    
    @pytest.mark.asyncio
    async def test_health_check_always_true(self):
        model = MockDecisionModel()
        assert await model.health_check() is True
    
    @pytest.mark.asyncio
    async def test_get_model_info(self):
        model = MockDecisionModel()
        info = await model.get_model_info()
        assert info['id'] == "mock-decision-model"
        assert info['type'] == "decision_model"
        assert info['provider'] == "mock"
    
    @pytest.mark.asyncio
    async def test_deterministic_selection(self):
        """Same seed + same options should produce same result."""
        model1 = MockDecisionModel(seed=42)
        model2 = MockDecisionModel(seed=42)
        
        result1 = await model1.decide(
            options=["a", "b", "c"],
            context={}
        )
        result2 = await model2.decide(
            options=["a", "b", "c"],
            context={}
        )
        
        assert result1.selected_option == result2.selected_option


class TestLMStudioDecisionModel:
    """Tests for LMStudioDecisionModel."""
    
    @pytest.mark.asyncio
    async def test_init_with_defaults(self):
        model = LMStudioDecisionModel()
        assert model.base_url == "http://localhost:1234/v1"
        assert model.temperature == 0.0
        assert model.max_tokens == 1024
    
    @pytest.mark.asyncio
    async def test_init_with_custom_values(self):
        model = LMStudioDecisionModel(
            base_url="http://example.com:8080/v1",
            model_id="my-model",
            temperature=0.1,
            max_tokens=512,
        )
        assert model.base_url == "http://example.com:8080/v1"
        assert model.model_id == "my-model"
        assert model.temperature == 0.1
    
    @pytest.mark.asyncio
    async def test_health_check_fails_when_unreachable(self):
        model = LMStudioDecisionModel(base_url="http://invalid:9999/v1")
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.get.side_effect = Exception("Connection failed")
            assert await model.health_check() is False
    
    @pytest.mark.asyncio
    async def test_health_check_fails_when_model_not_found(self):
        model = LMStudioDecisionModel(model_id="nonexistent-model")
        
        # Mock response with different model
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            'data': [{'id': 'other-model'}]
        })
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            assert await model.health_check() is False
    
    @pytest.mark.asyncio
    async def test_health_check_succeeds(self):
        model = LMStudioDecisionModel(model_id="test-model")

        # Mock the aiohttp.ClientSession directly
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            'data': [{'id': 'test-model'}]
        })

        # Create a proper async context manager
        class MockResponseCM:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, exc_type, exc, tb):
                pass

        mock_session_instance = MagicMock()
        mock_session_instance.get = MagicMock(return_value=MockResponseCM())

        with patch('aiohttp.ClientSession') as MockSession:
            MockSession.return_value = mock_session_instance
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await model.health_check() is True


class TestStrandsDecider2B:
    """Tests for StrandsDecider2B."""
    
    @pytest.mark.asyncio
    async def test_init(self):
        model = StrandsDecider2B(
            base_url="http://localhost:1234/v1",
            model_id="strands-decider-2b"
        )
        assert model.model_id == "strands-decider-2b"
        assert model.temperature == 0.0
    
    @pytest.mark.asyncio
    async def test_get_model_info(self):
        model = StrandsDecider2B()
        
        with patch.object(LMStudioDecisionModel, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            info = await model.get_model_info()
            assert info['type'] == "decision_model"
            assert info['provider'] == "lm_studio"
            assert "routing" in info['capabilities']


class TestDecisionModelConfig:
    """Tests for DecisionModelConfig."""
    
    def test_create_config(self):
        config = DecisionModelConfig(
            model_id="strands-decider-2b",
            name="Strands Decider 2B",
            provider="lm_studio",
            base_url="http://localhost:1234/v1",
        )
        assert config.type == "decision_model"
        assert config.temperature == 0.0
        assert len(config.capabilities) == 4
    
    def test_config_to_dict(self):
        config = DecisionModelConfig(
            model_id="test-model",
            name="Test Model",
        )
        assert config.model_id == "test-model"
        assert config.name == "Test Model"


class TestIntegration:
    """Integration tests for decision models."""
    
    @pytest.mark.asyncio
    async def test_mock_model_integration(self):
        """Test full flow with MockDecisionModel."""
        model = MockDecisionModel(seed=123)
        
        # Health check
        assert await model.health_check() is True
        
        # Make decision
        result = await model.decide(
            options=["agent_a", "agent_b", "agent_c"],
            context={"turn_number": 5}
        )
        
        assert result.is_valid
        assert result.selected_option in ["agent_a", "agent_b", "agent_c"]
        assert len(result.reasoning) > 0
    
    @pytest.mark.asyncio
    async def test_config_loads_correctly(self):
        """Test that DecisionModelConfig can be created from dict."""
        config_dict = {
            'model_id': 'strands-decider-2b',
            'name': 'Strands Decider 2B',
            'type': 'decision_model',
            'provider': 'lm_studio',
            'base_url': 'http://localhost:1234/v1',
            'temperature': 0.0,
            'max_tokens': 1024,
        }
        
        config = DecisionModelConfig(**config_dict)
        assert config.model_id == 'strands-decider-2b'
        assert config.temperature == 0.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
