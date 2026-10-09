"""Memory view for the GUI."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)


class MemoryView(tb.Frame):
    """View for displaying memory at different levels."""

    def __init__(self, parent: tb.Frame, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the memory view UI."""
        # Tabs for different memory levels
        self.tabs = tb.Notebook(self)
        self.tabs.pack(fill=BOTH, expand=True)

        # Short-term memory
        st_frame = tb.Frame(self.tabs)
        self.tabs.add(st_frame, text="Short-Term")
        self.st_text = tb.Text(st_frame, wrap=tk.WORD, state=tk.DISABLED)
        sb = tb.Scrollbar(st_frame, orient=tk.VERTICAL, command=self.st_text.yview)
        self.st_text.configure(yscrollcommand=sb.set)
        self.st_text.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        # Mid-term memory
        mt_frame = tb.Frame(self.tabs)
        self.tabs.add(mt_frame, text="Mid-Term")
        self.mt_text = tb.Text(mt_frame, wrap=tk.WORD, state=tk.DISABLED)
        sb = tb.Scrollbar(mt_frame, orient=tk.VERTICAL, command=self.mt_text.yview)
        self.mt_text.configure(yscrollcommand=sb.set)
        self.mt_text.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        # Long-term memory
        lt_frame = tb.Frame(self.tabs)
        self.tabs.add(lt_frame, text="Long-Term")
        self.lt_text = tb.Text(lt_frame, wrap=tk.WORD, state=tk.DISABLED)
        sb = tb.Scrollbar(lt_frame, orient=tk.VERTICAL, command=self.lt_text.yview)
        self.lt_text.configure(yscrollcommand=sb.set)
        self.lt_text.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

    def update_short_term(self, context: str) -> None:
        """Update short-term memory display."""
        self.st_text.config(state=NORMAL)
        self.st_text.delete(1.0, tk.END)
        self.st_text.insert(tk.END, context or "(Empty)")
        self.st_text.config(state=tk.DISABLED)

    def update_mid_term(self, entries: list) -> None:
        """Update mid-term memory display."""
        self.mt_text.config(state=NORMAL)
        self.mt_text.delete(1.0, tk.END)
        if not entries:
            self.mt_text.insert(tk.END, "(Empty)")
        else:
            for entry in entries:
                self.mt_text.insert(tk.END, f"\n=== {entry.period} ===\n")
                for arg in entry.main_arguments[:5]:
                    self.mt_text.insert(tk.END, f"- {arg}\n")
                if entry.important_questions:
                    self.mt_text.insert(tk.END, "\nQuestions:\n")
                    for q in entry.important_questions[:3]:
                        self.mt_text.insert(tk.END, f"? {q}\n")
        self.mt_text.config(state=tk.DISABLED)

    def update_long_term(self, entries: list) -> None:
        """Update long-term memory display."""
        self.lt_text.config(state=NORMAL)
        self.lt_text.delete(1.0, tk.END)
        if not entries:
            self.lt_text.insert(tk.END, "(Empty)")
        else:
            for entry in entries:
                cat = entry.category or "other"
                self.mt_text.insert(tk.END, f"\n[{cat}] {entry.key}: {entry.content[:200]}\n")
        self.lt_text.config(state=tk.DISABLED)
