"""
Agents package for Hermes Multi-Agent Debate Orchestrator.
"""

from .base import BaseAgent, ReasoningAgent, CriticAgent, JudgeAgent
from .rational import RationalAgent
from .counter_position import CounterPositionAgent
from .judge import JudgeAgent
from .bonsai import BonsaiAgent
from .savant import SavantAgent
from .jev import JevAgent

__all__ = [
    'BaseAgent',
    'ReasoningAgent',
    'CriticAgent',
    'JudgeAgent',
    'RationalAgent',
    'CounterPositionAgent',
    'BonsaiAgent',
    'SavantAgent',
    'JevAgent',
]
