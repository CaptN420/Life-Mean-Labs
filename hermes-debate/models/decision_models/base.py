"""
Decision Model Interface — Generic abstraction for decision-making models.

This module defines the core interface that all decision models must implement.
It is intentionally independent of LangGraph, CrewAI, AutoGen, or any specific framework.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class DecisionResult:
    """Structured result from a decision model."""
    
    selected_option: str
    confidence: float
    reasoning: str
    raw_response: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)
    
    @property
    def is_valid(self) -> bool:
        """Check if the decision result is valid."""
        return (
            self.selected_option is not None
            and self.confidence >= 0.0
            and self.confidence <= 1.0
            and len(self.selected_option.strip()) > 0
        )


class DecisionModel(ABC):
    """
    Abstract base class for decision models.
    
    Decision models are specialized models that make structured decisions:
    - Select next agent in debate
    - Choose routing strategy
    - Select tools
    - Evaluate options
    - Determine phase transitions
    
    This interface is framework-agnostic and can be implemented for:
    - Local models (via LM Studio, Ollama, etc.)
    - Remote models (APIs)
    - Rule-based systems
    - ML classifiers
    """
    
    @abstractmethod
    async def decide(
        self,
        options: list[str],
        context: dict[str, Any],
        **kwargs: Any
    ) -> DecisionResult:
        """
        Make a structured decision.
        
        Args:
            options: List of valid options to choose from
            context: Additional context for the decision
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
            
        Returns:
            DecisionResult with selected option and metadata
            
        Raises:
            ValueError: If options is empty or invalid
            TimeoutError: If decision takes too long
            RuntimeError: If model is unavailable
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the decision model is available and healthy.
        
        Returns:
            True if model is ready, False otherwise
        """
        ...
    
    @abstractmethod
    async def get_model_info(self) -> dict[str, Any]:
        """
        Get metadata about the decision model.
        
        Returns:
            Dictionary with model information
        """
        ...


class MockDecisionModel(DecisionModel):
    """
    Mock decision model for testing without real models.
    
    Returns deterministic decisions based on options index.
    Useful for CI/CD and unit tests.
    """
    
    def __init__(self, seed: int = 42):
        self._seed = seed
        self._call_count = 0
        
    async def decide(
        self,
        options: list[str],
        context: dict[str, Any],
        **kwargs: Any
    ) -> DecisionResult:
        """Return deterministic mock decision."""
        if not options:
            raise ValueError("Options list cannot be empty")
        
        # Deterministic selection based on seed and call count
        import hashlib
        seed_str = f"{self._seed}_{self._call_count}"
        hash_val = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
        selected_idx = hash_val % len(options)
        selected_option = options[selected_idx]
        
        self._call_count += 1
        
        return DecisionResult(
            selected_option=selected_option,
            confidence=0.85 + (hash_val % 100) / 1000.0,
            reasoning=f"Mock decision: selected {selected_option} from {len(options)} options",
            raw_response=f"{{\"decision\": \"{selected_option}\", \"confidence\": 0.87}}",
        )
    
    async def health_check(self) -> bool:
        """Mock model is always healthy."""
        return True
    
    async def get_model_info(self) -> dict[str, Any]:
        """Return mock model info."""
        return {
            "id": "mock-decision-model",
            "type": "decision_model",
            "provider": "mock",
            "version": "1.0.0",
            "capabilities": ["routing", "classification", "tool_selection"],
            "is_local": True,
        }
