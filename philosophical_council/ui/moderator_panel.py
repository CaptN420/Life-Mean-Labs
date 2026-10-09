"""Moderator panel for the GUI."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)


class ModeratorPanel(tb.Frame):
    """Panel displaying moderator decisions and current state."""

    def __init__(self, parent: tb.Frame, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the moderator panel UI."""
        # Current decision
        decision_frame = tb.LabelFrame(self, text="Current Decision", padding=10)
        decision_frame.pack(fill=X, pady=(0, 5))

        tb.Label(decision_frame, text="Selected Speaker:", font=("Consolas", 10, "bold")).pack(anchor=W)
        self.speaker_label = tb.Label(decision_frame, text="(Waiting...)", font=("Consolas", 12), foreground="#FFD700")
        self.speaker_label.pack(anchor=W, pady=(0, 10))

        tb.Label(decision_frame, text="Challenge:", font=("Consolas", 10, "bold")).pack(anchor=W)
        self.challenge_text = tb.Text(decision_frame, height=3, wrap=tk.WORD, state=tk.DISABLED)
        self.challenge_text.pack(fill=X, pady=(0, 10))

        tb.Label(decision_frame, text="Reason:", font=("Consolas", 10, "bold")).pack(anchor=W)
        self.reason_text = tb.Text(decision_frame, height=2, wrap=tk.WORD, state=tk.DISABLED)
        self.reason_text.pack(fill=X, pady=(0, 10))

        # Detected issues
        tb.Label(self, text="Detected Issues:", font=("Consolas", 10, "bold")).pack(anchor=W)
        self.issues_text = tb.Text(self, height=3, wrap=tk.WORD, state=tk.DISABLED)
        self.issues_text.pack(fill=X, pady=(5, 0))

    def update_decision(self, decision: dict) -> None:
        """Update the moderator panel with a new decision."""
        self.speaker_label.config(text=decision.get('selected_speaker', 'Unknown'))
        self.challenge_text.config(state=NORMAL)
        self.challenge_text.delete(1.0, tk.END)
        self.challenge_text.insert(tk.END, decision.get('challenge', ''))
        self.challenge_text.config(state=tk.DISABLED)

        self.reason_text.config(state=NORMAL)
        self.reason_text.delete(1.0, tk.END)
        self.reason_text.insert(tk.END, decision.get('reason', ''))
        self.reason_text.config(state=tk.DISABLED)

        issues = decision.get('detected_issues') or decision.get('question', '')
        self.issues_text.config(state=NORMAL)
        self.issues_text.delete(1.0, tk.END)
        self.issues_text.insert(tk.END, issues or "(None detected)")
        self.issues_text.config(state=tk.DISABLED)
