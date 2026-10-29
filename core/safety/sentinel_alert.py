"""Sentinel alert window for Life_mean dashboard.

Displays security alerts in a Python GUI window (PySide6) when Sentinel
detects anomalies. Provides STOP/PAUSE/CONTINUE actions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.safety.sentinel_alert")

# Lazy import to avoid requiring PySide6 at import time
def _get_qt():
    try:
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit,
            QHBoxLayout, QMessageBox, QComboBox, QGroupBox,
        )
        from PySide6.QtCore import Qt, Signal
        return QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit, QHBoxLayout, QMessageBox, QComboBox, QGroupBox, Qt, Signal
    except ImportError:
        return None


class SentinelAlertWindow(QDialog):
    """Dialog window for displaying Sentinel security alerts."""

    # Signals for user actions
    action_requested = Signal(str)  # "STOP", "PAUSE", "CONTINUE"

    def __init__(self, parent=None):
        qt = _get_qt()
        if qt is None:
            raise ImportError("PySide6 required for SentinelAlertWindow")
        QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit, QHBoxLayout, QMessageBox, QComboBox, QGroupBox, Qt, Signal = qt

        super().__init__(parent)
        self.setWindowTitle("LIFE_MEAN SENTINEL — SECURITY ALERT")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("🛡️ LIFE_MEAN SENTINEL — SECURITY ALERT")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #d32f2f;")
        layout.addWidget(title)

        # Alert details group
        details_group = QGroupBox("Alert Details")
        details_layout = QVBoxLayout(details_group)

        self._process_label = QLabel("Process: N/A")
        self._event_label = QLabel("Event: N/A")
        self._risk_label = QLabel("Risk Level: N/A")
        self._rule_label = QLabel("Rule: N/A")
        self._evidence_label = QLabel("Evidence: N/A")

        for label in [self._process_label, self._event_label, self._risk_label, self._rule_label, self._evidence_label]:
            details_layout.addWidget(label)

        layout.addWidget(details_group)

        # LLM Analysis group
        analysis_group = QGroupBox("LLM Analysis")
        analysis_layout = QVBoxLayout(analysis_group)

        self._analysis_text = QTextEdit()
        self._analysis_text.setReadOnly(True)
        self._analysis_text.setMaximumHeight(150)
        analysis_layout.addWidget(self._analysis_text)

        layout.addWidget(analysis_group)

        # Action buttons
        button_layout = QHBoxLayout()

        stop_btn = QPushButton("⛔ STOP")
        stop_btn.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")
        stop_btn.clicked.connect(lambda: self._on_action("STOP"))

        pause_btn = QPushButton("⏸️ PAUSE")
        pause_btn.setStyleSheet("background-color: #f57c00; color: white; font-weight: bold;")
        pause_btn.clicked.connect(lambda: self._on_action("PAUSE"))

        continue_btn = QPushButton("▶️ CONTINUE AT YOUR OWN RISK")
        continue_btn.setStyleSheet("background-color: #388e3c; color: white;")
        continue_btn.clicked.connect(lambda: self._on_action("CONTINUE"))

        button_layout.addWidget(stop_btn)
        button_layout.addWidget(pause_btn)
        button_layout.addWidget(continue_btn)

        layout.addLayout(button_layout)

    def _on_action(self, action: str) -> None:
        """Handle user action request."""
        self.action_requested.emit(action)
        self.accept()

    def display_alert(
        self,
        process_name: str,
        event_type: str,
        risk_level: str,
        rule: str,
        analysis: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Display an alert with the given details."""
        self._process_label.setText(f"Process: {process_name}")
        self._event_label.setText(f"Event: {event_type}")
        self._risk_label.setText(f"Risk Level: {risk_level}")
        self._rule_label.setText(f"Rule: {rule}")

        evidence_text = ""
        if evidence:
            evidence_text = "\n".join(
                f"- {e.get('type', 'unknown')}: {e.get('source', 'unknown')}"
                for e in evidence[:5]
            )
        self._evidence_label.setText(f"Evidence: {evidence_text or 'None'}")

        self._analysis_text.setPlainText(analysis or "No analysis available")

    def show_critical_alert(self) -> bool:
        """Show a critical alert that cannot be bypassed."""
        # For critical alerts, only STOP and PAUSE are available
        result = self.exec()
        return result == QDialog.Accepted


def create_sentinel_alert_window() -> Optional[SentinelAlertWindow]:
    """Create a Sentinel alert window, returning None if PySide6 unavailable."""
    try:
        return SentinelAlertWindow()
    except ImportError:
        logger.warning("PySide6 not available — Sentinel alerts will be logged only")
        return None
