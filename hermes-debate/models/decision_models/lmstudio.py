"""
LM Studio Decision Model Adapter.

Implements DecisionModel interface for Strands Decider 2B and other
decision models served via LM Studio's OpenAI-compatible API.
"""

import json
import logging
import re
from typing import Any, Optional

from .base import DecisionModel, DecisionResult

logger = logging.getLogger(__name__)


class LMStudioDecisionModel(DecisionModel):
    """
    Decision model adapter for LM Studio.
    
    Communicates with LM Studio via its OpenAI-compatible API endpoint.
    Supports any decision model served through LM Studio, including:
    - Strands Decider 2B
    - Other specialized decision models
    - Fine-tuned routing models
    
    Configuration is external — no hardcoded endpoints or model names.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout_seconds: int = 60,
    ):
        """
        Initialize LM Studio decision model.
        
        Args:
            base_url: LM Studio API endpoint (e.g., http://localhost:1234/v1)
            model_id: Model identifier as exposed by LM Studio
            api_key: API key if required
            temperature: Generation temperature (default 0.0 for decisions)
            max_tokens: Maximum tokens for response
            timeout_seconds: Request timeout
        """
        self.base_url = base_url.rstrip('/')
        self.model_id = model_id
        self.api_key = api_key or ""
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        
        self._session = None
        self._model_info: Optional[dict] = None
        
    async def decide(
        self,
        options: list[str],
        context: dict[str, Any],
        **kwargs: Any
    ) -> DecisionResult:
        """
        Make a structured decision using LM Studio.
        
        Args:
            options: List of valid options to choose from
            context: Additional context for the decision
            **kwargs: Override temperature, max_tokens, etc.
            
        Returns:
            DecisionResult with selected option and metadata
            
        Raises:
            ValueError: If options is empty or invalid
            TimeoutError: If decision takes too long
            RuntimeError: If model is unavailable
        """
        if not options:
            raise ValueError("Options list cannot be empty")
        
        # Build structured prompt for decision
        prompt = self._build_decision_prompt(options, context)
        
        try:
            response = await self._call_lm_studio(prompt, kwargs)
            return self._parse_response(response, options)
            
        except Exception as e:
            logger.error(f"Decision failed: {e}")
            raise
    
    async def health_check(self) -> bool:
        """
        Check if LM Studio is available and model is loaded.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                # Check API endpoint
                async with session.get(
                    f"{self.base_url}/models",
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as response:
                    if response.status != 200:
                        logger.error(f"LM Studio not reachable at {self.base_url}")
                        return False
                    
                    # Check if model is available
                    data = await response.json()
                    models = data.get('data', [])
                    
                    # Validate model_id is in the list
                    if self.model_id:
                        model_ids = [m.get('id') for m in models]
                        if self.model_id not in model_ids:
                            logger.error(
                                f"Model '{self.model_id}' not found in LM Studio. "
                                f"Available: {model_ids}"
                            )
                            return False
                    
                    self._model_info = {
                        'endpoint': self.base_url,
                        'model_id': self.model_id,
                        'available_models': model_ids,
                        'healthy': True,
                    }
                    return True
                    
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def get_model_info(self) -> dict[str, Any]:
        """
        Get metadata about the decision model.
        
        Returns:
            Dictionary with model information
        """
        if self._model_info is None:
            await self.health_check()
        return self._model_info or {}
    
    def _build_decision_prompt(self, options: list[str], context: dict) -> str:
        """Build structured prompt for decision model."""
        options_list = "\n".join(f"- {i+1}. {opt}" for i, opt in enumerate(options))
        
        # Extract relevant context
        context_summary = ""
        if 'debate_state' in context:
            state = context['debate_state']
            context_summary = f"""
Debate State:
- Turn: {state.get('turn_number', 0)}
- Current Agent: {state.get('current_agent', 'unknown')}
- Previous Agent: {state.get('previous_agent', 'unknown')}
- Consensus: {state.get('consensus', False)}
- Loop Detected: {state.get('loop_detected', False)}
"""
        
        return f"""You are a decision model tasked with selecting the best option from the given choices.

OPTIONS:
{options_list}

CONTEXT:
{context_summary}

Select the BEST option and return a JSON response with this exact structure:
{{
  "decision": "<selected_option>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}}

Rules:
1. Choose ONLY from the provided options
2. Confidence must be between 0.0 and 1.0
3. Reasoning should be concise (max 50 words)
4. Return ONLY valid JSON, no other text"""
    
    async def _call_lm_studio(self, prompt: str, kwargs: dict) -> dict:
        """Call LM Studio API."""
        import aiohttp
        
        temperature = kwargs.get('temperature', self.temperature)
        max_tokens = kwargs.get('max_tokens', self.max_tokens)
        
        payload = {
            'model': self.model_id,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': temperature,
            'max_tokens': max_tokens,
            'response_format': {'type': 'json_object'},
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.base_url}/chat/completions',
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"LM Studio API error: {response.status} - {error_text}")
                
                data = await response.json()
                return data
    
    def _parse_response(self, response: dict, valid_options: list[str]) -> DecisionResult:
        """Parse and validate LM Studio response."""
        try:
            content = response['choices'][0]['message']['content']
            raw_response = content
            
            # Try to parse JSON
            try:
                decision_data = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from text
                json_match = re.search(r'\{[^}]+\}', content)
                if json_match:
                    decision_data = json.loads(json_match.group())
                else:
                    raise ValueError(f"Could not parse decision JSON from response: {content}")
            
            # Extract fields
            selected_option = decision_data.get('decision', '')
            confidence = float(decision_data.get('confidence', 0.5))
            reasoning = decision_data.get('reasoning', '')
            
            # Validate option is in valid options
            if selected_option not in valid_options:
                logger.warning(
                    f"Invalid option '{selected_option}' from model. "
                    f"Valid options: {valid_options}"
                )
                # Try to find closest match
                selected_option = self._find_closest_option(selected_option, valid_options)
                if selected_option is None:
                    selected_option = valid_options[0]  # Fallback to first option
            
            # Clamp confidence
            confidence = max(0.0, min(1.0, confidence))
            
            return DecisionResult(
                selected_option=selected_option,
                confidence=confidence,
                reasoning=reasoning,
                raw_response=raw_response,
            )
            
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            raise
    
    def _find_closest_option(self, selected: str, valid_options: list[str]) -> Optional[str]:
        """Find closest matching option (simple string matching)."""
        selected_lower = selected.lower()
        for opt in valid_options:
            if selected_lower in opt.lower() or opt.lower() in selected_lower:
                return opt
        return None
