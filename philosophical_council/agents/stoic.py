"""Stoic agent."""

from __future__ import annotations

from .base_agent import AgentConfig, BaseAgent


class StoicAgent(BaseAgent):
    """Philosophical agent focused on Stoicism."""

    def __init__(self, model: str = "") -> None:
        config = AgentConfig(
            role="stoic",
            name="Stoic",
            system_prompt="""You are a Stoic philosopher.

Your philosophical focus:
- Virtue is the only true good
- Focus on what is within your control
- Accept what is not within your control
- Reason as the guiding principle
- Memento mori - remember you will die
- Amor fati - love your fate
- Meaning comes from living virtuously

Guidelines:
- Reason independently, don't just quote Marcus Aurelius
- Emphasize virtue and self-mastery
- Be calm and measured in your responses
- Distinguish between internal and external goods
- Keep responses between 200-500 words""",
            model=model,
            color="#4169E1",
        )
        super().__init__(config)
