"""Configurable debate agent — the generic RoleTemplate-driven participant.

This is the minimal generalization of :class:`~philosophical_council.agents.base_agent.BaseAgent`
that lets DebateEngine run ANY RoleTemplate team (Scientist + Skeptic, a
council, a molecular-discovery panel, ...) without depending on the six
hardcoded philosophical schools.

The existing philosophical subclasses (ExistentialistAgent, StoicAgent, ...)
are NOT touched and continue to work — this class is the DYNAMIC participant
for templates whose roles are not a known philosophical school. Its prompt is
generic:

    ROLE / PERSONA / OBJECTIVES / CONSTRAINTS / DEBATE CONTEXT /
    RECENT ARGUMENTS / MODERATOR CHALLENGE / EXPECTED OUTPUT

and it never forces "philosophical position" / "philosophical response"
language on a non-philosophical role (spec §6.H).
"""

from __future__ import annotations

from typing import List, Optional

from .base_agent import AgentConfig, BaseAgent


class ConfigurableDebateAgent(BaseAgent):
    """A BaseAgent configured from a RoleTemplate RoleSpec (generic wording)."""

    def __init__(
        self,
        role_id: str,
        name: str,
        system_prompt: str,
        model: str = "",
        color: str = "#888888",
        persona: str = "",
        objectives: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        expected_output: str = "",
    ) -> None:
        config = AgentConfig(
            role=role_id,
            name=name,
            system_prompt=system_prompt,
            model=model or None,
            color=color,
        )
        super().__init__(config)
        # Layered identity metadata (kept distinguishable in provenance — ROLE
        # != PERSONA: a persona is referenced, not merged into the role_id).
        self.persona = persona
        self.objectives = list(objectives or [])
        self.constraints = list(constraints or [])
        self.expected_output = expected_output

    def format_response(
        self,
        challenge: str,
        context: str,
        previous_speaker: Optional[str] = None,
        last_argument_summary: Optional[str] = None,
    ) -> str:
        """Generic per-turn prompt for a templated participant.

        Generic wording only — never "Express your philosophical position".
        The role/persona/objectives/constraints live in the SYSTEM prompt (set
        by the session factory); this user-turn prompt supplies the live debate
        state and the moderator challenge.
        """
        sections = []

        sections.append(f"DEBATE CONTEXT:\n{context}")

        history = self.get_history()
        if history:
            recent = history[-3:]
            lines = ["RECENT ARGUMENTS (yours, from previous turns):"]
            for i, r in enumerate(recent, 1):
                lines.append(f"{i}. {r[:300]}")
            sections.append("\n".join(lines))
        else:
            sections.append("RECENT ARGUMENTS: (none yet — this is your first turn)")

        sections.append(f"MODERATOR CHALLENGE:\n{challenge}")

        sections.append(
            "EXPECTED OUTPUT:\n"
            + (self.expected_output or "A focused, substantive contribution to the debate.")
        )

        sections.append(
            "RESPONSE INSTRUCTIONS:\n"
            "1. Address the moderator's challenge directly.\n"
            "2. Engage with the most relevant prior argument (if any) before advancing your own.\n"
            "3. Stay within your role's objectives and constraints.\n"
            "4. Be specific and concrete; avoid repeating arguments you already made."
        )
        if previous_speaker:
            sections.append(f"You are responding after {previous_speaker}; engage with their point.")

        return "\n\n---\n\n".join(sections)
