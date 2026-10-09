"""Debate view for the GUI."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)


class DebateView(tb.Frame):
    """View for displaying the debate transcript."""

    def __init__(self, parent: tb.Frame, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        self._build_ui()
        self.engine = None

    def _build_ui(self) -> None:
        """Build the debate view UI."""
        # Search bar
        search_frame = tb.Frame(self)
        search_frame.pack(fill=X)

        tb.Label(search_frame, text="Search:").pack(side=LEFT)
        self.search_entry = tb.Entry(search_frame)
        self.search_entry.pack(side=LEFT, padx=(5, 0))

        tb.Button(search_frame, text="Search", command=self._search).pack(side=LEFT, padx=(5, 0))

        # Filter combobox
        tb.Label(search_frame, text="Filter:").pack(side=LEFT, padx=(20, 0))
        self.filter_combo = tb.Combobox(
            search_frame,
            values=["All", "Existentialist", "Stoic", "Nihilist", "Spiritual Philosopher", "Skeptic"],
            state="readonly",
            width=20,
        )
        self.filter_combo.set("All")
        self.filter_combo.pack(side=LEFT, padx=(5, 0))

        # Debate text
        self.debate_text = tb.Text(self, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        scrollbar = tb.Scrollbar(self, orient=tk.VERTICAL, command=self.debate_text.yview)
        self.debate_text.configure(yscrollcommand=scrollbar.set)
        self.debate_text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

    def _search(self) -> None:
        """Search the debate transcript."""
        query = self.search_entry.get().lower()
        if not query:
            return

        # This would search through stored turns
        logger.info("Searching for: %s", query)

    def update_turn(self, turn_data: dict) -> None:
        """Display a new turn in the transcript."""
        self.debate_text.config(state=NORMAL)

        # Add separator
        self.debate_text.insert(tk.END, "\n" + "=" * 60 + "\n")

        # Round info
        self.debate_text.insert(tk.END, f"\nROUND {turn_data.get('round', '?')}\n\n")

        # Moderator instructions
        if turn_data.get('moderator_question'):
            self.debate_text.insert(tk.END, "MODERATOR\n\n")
            self.debate_text.insert(tk.END, f"Challenge: {turn_data['moderator_question']}\n\n")
            if turn_data.get('moderator_reason'):
                self.debate_text.insert(tk.END, f"Reason: {turn_data['moderator_reason']}\n\n")
            self.debate_text.insert(tk.END, "-" * 60 + "\n\n")

        # Speaker response
        speaker = turn_data.get('speaker', 'Unknown')
        self.debate_text.insert(tk.END, f"{speaker}\n\n")
        self.debate_text.insert(tk.END, turn_data.get('response', ''))
        self.debate_text.insert(tk.END, "\n" + "=" * 60)

        self.debate_text.config(state=tk.DISABLED)
        self.debate_text.see(tk.END)

    def clear(self) -> None:
        """Clear the debate view."""
        self.debate_text.config(state=NORMAL)
        self.debate_text.delete(1.0, tk.END)
        self.debate_text.config(state=tk.DISABLED)
