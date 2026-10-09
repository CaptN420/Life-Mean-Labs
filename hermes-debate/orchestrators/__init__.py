"""
Orchestrators package.

Provides interchangeable orchestrator implementations:
- CustomOrchestrator: Native implementation
- LangGraphOrchestrator: Adapter for LangGraph
- CrewAIOrchestrator: Adapter for CrewAI
- AutoGenOrchestrator: Adapter for AutoGen

All orchestrators implement the same interface and are considered
experimental variables — the scientific model does not depend on
the internal implementation.
"""

from .base import Orchestrator, OrchestratorResult, DebateState, MockOrchestrator
from .custom import CustomOrchestrator
from .langgraph import LangGraphOrchestrator
from .crewai import CrewAIOrchestrator
from .autogen import AutoGenOrchestrator


__all__ = [
    'Orchestrator',
    'OrchestratorResult',
    'DebateState',
    'MockOrchestrator',
    'CustomOrchestrator',
    'LangGraphOrchestrator',
    'CrewAIOrchestrator',
    'AutoGenOrchestrator',
]
