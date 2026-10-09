"""Controls for the GUI."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)


class Controls(tb.Frame):
    """Control panel for the debate."""

    def __init__(self, parent: tb.Frame, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the controls UI."""
        # Main control buttons
        btn_frame = tb.Frame(self)
        btn_frame.pack(fill=X, pady=(0, 10))

        self.start_btn = tb.Button(btn_frame, text="Start", command=self._on_start, width=12)
        self.start_btn.pack(side=LEFT, padx=(0, 5))

        self.pause_btn = tb.Button(btn_frame, text="Pause", command=self._on_pause, width=12)
        self.pause_btn.pack(side=LEFT, padx=5)

        self.stop_btn = tb.Button(btn_frame, text="Stop", command=self._on_stop, width=12)
        self.stop_btn.pack(side=LEFT, padx=5)

        self.step_btn = tb.Button(btn_frame, text="Next Turn", command=self._on_step, width=12)
        self.step_btn.pack(side=LEFT, padx=(20, 5))

        # Status
        self.status_label = tb.Label(self, text="Status: Idle", font=("Consolas", 10))
        self.status_label.pack(side=LEFT, padx=(20, 0))

        # Turn counter
        self.turn_label = tb.Label(self, text="Turns: 0", font=("Consolas", 10))
        self.turn_label.pack(side=LEFT, padx=(10, 0))

        # Save/Load buttons
        save_frame = tb.Frame(self)
        save_frame.pack(side=RIGHT)

        tb.Button(save_frame, text="Save Debate", command=self._on_save).pack(side=LEFT, padx=(0, 5))
        tb.Button(save_frame, text="Load Debate", command=self._on_load).pack(side=LEFT, padx=(0, 5))
        tb.Button(save_frame, text="Export", command=self._on_export).pack(side=LEFT)

    def _on_start(self) -> None:
        """Handle start button click."""
        if self.start_btn.cget('command'):
            self.start_btn.invoke()

    def _on_pause(self) -> None:
        """Handle pause button click."""
        pass

    def _on_stop(self) -> None:
        """Handle stop button click."""
        pass

    def _on_step(self) -> None:
        """Handle step button click."""
        pass

    def _on_save(self) -> None:
        """Handle save button click."""
        pass

    def _on_load(self) -> None:
        """Handle load button click."""
        pass

    def _on_export(self) -> None:
        """Handle export button click."""
        pass

    def update_status(self, status: str, turns: int = 0) -> None:
        """Update status and turn counter."""
        self.status_label.config(text=f"Status: {status}")
        self.turn_label.config(text=f"Turns: {turns}")
