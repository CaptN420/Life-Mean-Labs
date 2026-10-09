"""Agent panel for the GUI."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)


class AgentPanel(tb.Frame):
    """Panel displaying agent status and history."""

    def __init__(self, parent: tb.Frame, agents: dict[str, any], **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.agents = agents
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the agent panel UI."""
        for role, agent in self.agents.items():
            agent_frame = tb.LabelFrame(self, text=agent.name, padding=5)
            agent_frame.pack(fill=X, pady=(0, 5))

            # Agent info
            info_frame = tb.Frame(agent_frame)
            info_frame.pack(fill=X)

            tb.Label(info_frame, text=f"Color: {agent.color}",
                    foreground=agent.color, font=("Consolas", 10)).pack(side=LEFT)

            model_label = f"Model: {agent.config.model or 'default'}"
            tb.Label(info_frame, text=model_label).pack(side=RIGHT)

            # History
            history_frame = tb.Frame(agent_frame)
            history_frame.pack(fill=X, pady=(5, 0))

            tb.Label(history_frame, text="Recent responses:").pack(anchor=W)
            history_text = tb.Text(history_frame, height=4, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
            history_text.pack(fill=X, expand=True)

            # Store reference for updates
            setattr(self, f"{role}_history", history_text)

    def update_agent(self, role: str, response: str) -> None:
        """Update an agent's history with a new response."""
        history = getattr(self, f"{role}_history", None)
        if history is None:
            return

        history.config(state=NORMAL)
        history.delete(1.0, tk.END)
        # Show last 3 responses
        recent = agent.get_history()[-3:]
        for r in recent:
            history.insert(tk.END, r[:200] + "...\n")
        history.config(state=tk.DISABLED)
