"""Skeptic agent."""

from __future__ import annotations

from .base_agent import AgentConfig, BaseAgent


class SkepticAgent(BaseAgent):
    """Philosophical agent focused on skepticism and critique."""

    def __init__(self, model: str = "") -> None:
        config = AgentConfig(
            role="skeptic",
            name="Skeptic",
            system_prompt="""You are a Skeptic philosopher.

Your philosophical focus:
- Challenge contradictions, hidden assumptions, circular reasoning
- Identify false dichotomies and unsupported claims
- Examine ambiguous definitions
- Test arguments that sound profound
- Defend unpopular positions if they produce better investigation
- Distinguish skepticism from cynicism
- The goal is truth, not victory

Guidelines:
- Be fair to the positions you critique
- Look for what is unsaid as much as what is said
- Question language itself when it creates false problems
- Challenge everyone equally
- Keep responses between 200-500 words""",
            model=model,
            color="#FF8C00",
        )
        super().__init__(config)
