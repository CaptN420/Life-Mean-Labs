"""
JEV 0.8B - Auxiliary Analysis Agent
Lightweight model for extraction, classification, preprocessing.
"""

import logging
from typing import Optional

from .base import BaseAgent, AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class JevAgent(BaseAgent):
    """
    JEV 0.8B - Analyse auxiliaire
    
    Utilisations:
    - Extraction d'information
    - Analyse légère
    - Classification auxiliaire
    - Prétraitement
    - Détection de signaux
    - Préparation du contexte
    - Résumé court
    - Analyse rapide d'une intervention
    """
    
    def __init__(self, agent_id: str = "jev_08b", **kwargs):
        super().__init__(agent_id, AgentRole.PHILOSOPHER, kwargs)
    
    def _get_system_prompt(self) -> str:
        return """You are JEV, a lightweight auxiliary analysis model.
Your role is to extract signals, classify information, and prepare context.

You must NOT:
- Make debate decisions
- Choose next agents
- Generate full arguments

You MUST:
- Extract key points from text
- Classify argument types
- Detect patterns and signals
- Prepare concise summaries
- Identify relevant memories

Keep responses brief and focused on extraction/classification.
"""
    
    async def generate_response(self, prompt: str, debate_context: dict, **kwargs) -> AgentResponse:
        """Generate auxiliary analysis."""
        turn_number = debate_context.get('turn_number', 0) + 1
        
        return AgentResponse(
            agent_id=self.agent_id,
            role=self.role,
            content=f"[JEV Analysis] Extracting: {prompt[:150]}...",
            turn_number=turn_number,
            metadata={
                'agent_type': 'jev',
                'model': 'jev_08b'
            }
        )
