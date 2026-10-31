"""
Agent Manager for Life_mean Studio.

Manages agent lifecycle: create, update, delete, duplicate, test.
Connects to the real LLM backend (LM Studio / OpenAI-compatible) for testing.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LifeMean.Studio.AgentManager")


@dataclass
class AgentResult:
    """Result of an agent operation."""

    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class TestResult:
    """Result of testing an agent against a prompt."""

    success: bool
    response: str = ""
    model: Optional[str] = None
    provider: Optional[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class AgentManager:
    """Manages agent CRUD and LLM integration."""

    def __init__(self, storage):
        self.storage = storage

    # ---- CRUD ----

    def create(self, name: str, system_prompt: str, persona: str = "general",
               description: str = "", model: Optional[str] = None,
               provider: Optional[str] = None, config: Optional[Dict[str, Any]] = None,
               tools: Optional[List[str]] = None) -> AgentResult:
        """Create a new agent."""
        if not name or not system_prompt:
            return AgentResult(False, "Name and system prompt are required")

        try:
            agent_id = self.storage.create_agent(
                name=name,
                system_prompt=system_prompt,
                persona=persona,
                description=description,
                model=model,
                provider=provider,
                config=config,
                tools=tools,
            )
            return AgentResult(True, f"Agent '{name}' created", {"id": agent_id})
        except Exception as e:
            logger.error("Failed to create agent: %s", e)
            return AgentResult(False, f"Failed to create agent: {e}")

    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent by ID."""
        return self.storage.get_agent(agent_id)

    def list_all(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all agents."""
        return self.storage.list_agents(enabled_only=enabled_only)

    def update(self, agent_id: str, updates: Dict[str, Any]) -> AgentResult:
        """Update an agent."""
        if not self.storage.get_agent(agent_id):
            return AgentResult(False, "Agent not found")

        try:
            self.storage.update_agent(agent_id, updates)
            return AgentResult(True, "Agent updated")
        except Exception as e:
            logger.error("Failed to update agent: %s", e)
            return AgentResult(False, f"Failed to update agent: {e}")

    def delete(self, agent_id: str) -> AgentResult:
        """Delete an agent."""
        if not self.storage.get_agent(agent_id):
            return AgentResult(False, "Agent not found")

        try:
            self.storage.delete_agent(agent_id)
            return AgentResult(True, "Agent deleted")
        except Exception as e:
            logger.error("Failed to delete agent: %s", e)
            return AgentResult(False, f"Failed to delete agent: {e}")

    def duplicate(self, agent_id: str, new_name: Optional[str] = None) -> AgentResult:
        """Duplicate an agent."""
        original = self.storage.get_agent(agent_id)
        if not original:
            return AgentResult(False, "Agent not found")

        try:
            new_id = self.storage.duplicate_agent(agent_id, new_name)
            return AgentResult(True, "Agent duplicated", {"id": new_id})
        except Exception as e:
            logger.error("Failed to duplicate agent: %s", e)
            return AgentResult(False, f"Failed to duplicate agent: {e}")

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search agents."""
        return self.storage.search_agents(query)

    # ---- Persona loading ----

    def load_persona(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """Load a predefined persona as an agent config."""
        from life_mean_studio.engine.personas import persona_to_agent_config
        return persona_to_agent_config(persona_id)

    def load_pattern_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Load a geometrical pattern prompt as an agent config."""
        from life_mean_studio.engine.patterns import pattern_to_agent_config
        return pattern_to_agent_config(prompt_id)

    def load_thinker(self, thinker_id: str) -> Optional[Dict[str, Any]]:
        """Load a historical thinker as an agent config."""
        from life_mean_studio.engine.historical_thinkers import thinker_to_agent_config
        return thinker_to_agent_config(thinker_id)

    def list_available_personas(self) -> List[Dict[str, str]]:
        """List all available personas from all sources."""
        from life_mean_studio.engine.personas import list_personas
        from life_mean_studio.engine.patterns import list_pattern_prompts
        from life_mean_studio.engine.historical_thinkers import list_thinkers

        all_personas = []
        all_personas.extend(list_personas())
        all_personas.extend(list_pattern_prompts())
        all_personas.extend(list_thinkers())
        return all_personas

    # ---- LLM Integration ----

    def _get_llm_config(self) -> tuple[str, str]:
        """Get LLM base URL and API key from environment/config."""
        import os
        base_url = os.environ.get("LIFE_MEAN_LLM_BASE_URL", "http://localhost:1234/v1")
        api_key = os.environ.get("LIFE_MEAN_LLM_API_KEY", "")

        # Try to load from .env file
        root = Path(__file__).resolve().parents[2]
        for path in [root / "overrides" / "llm.env", root / ".env"]:
            if path.exists():
                try:
                    for line in path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k == "LIFE_MEAN_LLM_BASE_URL" and not os.environ.get("LIFE_MEAN_LLM_BASE_URL"):
                            base_url = v
                        elif k == "LIFE_MEAN_LLM_API_KEY" and not os.environ.get("LIFE_MEAN_LLM_API_KEY"):
                            api_key = v
                except OSError:
                    pass

        return base_url, api_key

    def test_agent(self, agent_id: str, prompt: str) -> TestResult:
        """Test an agent by sending a prompt to its configured LLM."""
        agent = self.get(agent_id)
        if not agent:
            return TestResult(False, error="Agent not found")

        base_url, api_key = self._get_llm_config()
        model = agent.get("model") or "qwen3.5-2b"
        provider = agent.get("provider") or "lm-studio"

        # Build the message with system prompt
        messages = [
            {"role": "system", "content": agent["system_prompt"]},
            {"role": "user", "content": prompt},
        ]

        # Add any extra config (temperature, max_tokens, etc.)
        extra_config = agent.get("config", {})

        start_time = time.perf_counter()
        try:
            url = f"{base_url.rstrip('/')}/chat/completions"
            payload = {
                "model": model,
                "messages": messages,
                **extra_config,
            }
            headers = {
                "Content-Type": "application/json",
            }
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                response_text = body.get("choices", [{}])[0].get("message", {}).get("content", "")
                latency = round((time.perf_counter() - start_time) * 1000, 1)

                return TestResult(
                    success=True,
                    response=response_text,
                    model=model,
                    provider=provider,
                    latency_ms=latency,
                )

        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                err_msg = f"HTTP {e.code}: {err_body[:200]}"
            except Exception:
                err_msg = f"HTTP {e.code}"
            return TestResult(False, error=err_msg)

        except urllib.error.URLError as e:
            return TestResult(False, error=f"Connection failed: {e.reason}")

        except Exception as e:
            return TestResult(False, error=str(e))

    def get_available_models(self) -> List[str]:
        """Get list of available models from LLM backend."""
        base_url, api_key = self._get_llm_config()

        try:
            url = f"{base_url.rstrip('/')}/models"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return [m.get("id") for m in body.get("data", []) if m.get("id")]
        except Exception as e:
            logger.debug("Could not load models: %s", e)
            return []
