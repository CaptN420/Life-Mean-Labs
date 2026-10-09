"""
Cloudflare Clef Decision Engine.
Handles structured decisions from the CLEF model.
"""

import json
import logging
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)


class ClefDecisionEngine:
    """
    Decision engine that uses Cloudflare CLEF for structured decisions.
    Returns validated, safe decisions based on debate state.
    """
    
    def __init__(self, account_id: str, api_key: str, endpoint: str = "https://api.cloudflare.com/client/v4"):
        self.account_id = account_id
        self.api_key = api_key
        self.endpoint = endpoint.rstrip('/')
        self._base_url = f"{endpoint.rstrip('/')}/accounts/{account_id}/ai/run"
        self.model_name = "cloudflare_clef-flash"
    
    async def make_decision(
        self,
        debate_state: dict,
        allowed_actions: list[str],
        previous_action: Optional[str] = None
    ) -> dict:
        """
        Make a structured decision using CLEF.
        
        Args:
            debate_state: Current state of the debate
            allowed_actions: List of allowed actions
            previous_action: Last action taken
            
        Returns:
            Validated decision dictionary
        """
        try:
            questions = self._build_questions(allowed_actions)
            
            payload = {
                'model': self.model_name,
                'state': json.dumps(debate_state, indent=2),
                'questions': questions
            }
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # Use aiohttp or requests for actual HTTP call
            # For now, simulate the response structure
            decision = await self._call_clef_api(payload, headers)
            
            # Validate and sanitize the decision
            validated = self._validate_decision(decision, allowed_actions)
            
            logger.info(f"CLEF decision: {validated.get('next_action')} (confidence: {validated.get('confidence', 0):.2f})")
            return validated
            
        except Exception as e:
            logger.error(f"CLEF decision failed: {e}")
            raise
    
    def _build_questions(self, allowed_actions: list[str]) -> dict:
        """Build the CLEF questions schema."""
        return {
            'next_action': {
                'type': 'choice',
                'instructions': 'Which action should be taken next in the debate?',
                'criteria': {action: f"Take {action} action" for action in allowed_actions}
            },
            'consensus_reached': {
                'type': 'noul',
                'instructions': 'Has consensus been reached among the philosophers?'
            },
            'loop_detected': {
                'type': 'noul',
                'instructions': 'Is the debate looping without progress?'
            },
            'needs_fact_check': {
                'type': 'noul',
                'instructions': 'Does this require factual verification?'
            },
            'debate_progress': {
                'type': 'score',
                'instructions': 'How much progress has been made? (0-1)',
                'criteria': ['No progress', 'Some progress', 'Significant progress', 'Near completion']
            }
        }
    
    async def _call_clef_api(self, payload: dict, headers: dict) -> dict:
        """Call the CLEF API."""
        # In production, use aiohttp or requests
        # For simulation, return a mock response
        import os
        
        if os.getenv('SIMULATION'):
            return {
                'answers': {
                    'next_action': {'selected': 'MODEL_A', 'probabilities': {'MODEL_A': 0.91, 'MODEL_B': 0.05, 'JUDGE': 0.04}},
                    'consensus_reached': {'text': 'false'},
                    'loop_detected': {'text': 'false'},
                    'needs_fact_check': {'text': 'false'},
                    'debate_progress': {'score': 0.65}
                }
            }
        
        # Real API call would go here
        raise NotImplementedError("Real CLEF API not configured")
    
    def _validate_decision(self, decision: dict, allowed_actions: list[str]) -> dict:
        """Validate and sanitize the CLEF decision."""
        next_action = decision.get('answers', {}).get('next_action', {})
        selected = next_action.get('selected', 'END')
        
        # Ensure action is in allowed list
        if selected not in allowed_actions:
            logger.warning(f"Invalid action '{selected}' from CLEF, defaulting to END")
            selected = 'END'
        
        return {
            'next_action': selected,
            'confidence': next_action.get('probabilities', {}).get(selected, 0.5),
            'consensus_reached': decision.get('answers', {}).get('consensus_reached', {}).get('text', 'false').lower() == 'true',
            'loop_detected': decision.get('answers', {}).get('loop_detected', {}).get('text', 'false').lower() == 'true',
            'needs_fact_check': decision.get('answers', {}).get('needs_fact_check', {}).get('text', 'false').lower() == 'true',
            'debate_progress': decision.get('answers', {}).get('debate_progress', {}).get('score', 0.5),
            'reason': f"CLEF selected {selected} with confidence {next_action.get('probabilities', {}).get(selected, 0):.2f}"
        }


class FakeClefEngine:
    """Fake CLEF engine for simulation mode."""
    
    async def make_decision(self, debate_state: dict, allowed_actions: list[str], previous_action: Optional[str] = None) -> dict:
        """Return a simulated decision."""
        import random
        
        # Determine next action based on state
        if not allowed_actions or 'END' in allowed_actions and len(allowed_actions) == 1:
            return {
                'next_action': 'END',
                'confidence': 0.9,
                'consensus_reached': True,
                'loop_detected': False,
                'needs_fact_check': False,
                'debate_progress': 1.0,
                'reason': 'Simulation: debate complete'
            }
        
        # Pick next action (prefer different from previous)
        available = [a for a in allowed_actions if a != previous_action]
        if not available:
            available = allowed_actions
        
        next_action = random.choice(available)
        
        return {
            'next_action': next_action,
            'confidence': 0.85 + random.random() * 0.1,
            'consensus_reached': False,
            'loop_detected': False,
            'needs_fact_check': False,
            'debate_progress': min(1.0, (debate_state.get('turn_number', 0) + 1) / debate_state.get('max_turns', 8)),
            'reason': f"Simulation: selecting {next_action}"
        }
