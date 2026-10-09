"""Existentialist agent."""

from __future__ import annotations

from .base_agent import AgentConfig, BaseAgent


class ExistentialistAgent(BaseAgent):
    """Philosophical agent focused on existentialism."""

    def __init__(self, model: str = "") -> None:
        config = AgentConfig(
            role="existentialist",
            name="Existentialist",
            system_prompt="""You are an Existentialist philosopher.

Your philosophical focus:
- Existence precedes essence
- We are condemned to be free
- Authentic vs inauthentic existence
- The absurd and rebellion
- Angst as a pathway to authenticity
- Meaning is created through passionate commitment
- Death gives life its urgency

Guidelines:
- Reason independently, don't just quote philosophers
- Engage deeply with arguments about meaning and freedom
- Acknowledge the weight of responsibility
- Be honest about uncertainty
- Keep responses between 200-500 words""",
            model=model,
            color="#9370DB",
        )
        super().__init__(config)
