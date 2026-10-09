"""
Structured logging for Hermes orchestrator.
Provides observability into debate execution.
"""

import logging
import json
from datetime import datetime
from typing import Optional, Any


class HermesLogger:
    """Structured logger for Hermes system."""

    def __init__(self, name: str = "hermes", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Add handler if not exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)

    def log_event(self, event_type: str, data: dict, level: int = logging.INFO) -> None:
        """Log a structured event."""
        message = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'data': data,
        }
        self.logger.log(level, json.dumps(message, default=str))

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        extra = kwargs.get('extra', {})
        self.logger.info(f"{message} | {json.dumps(extra)}")

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        extra = kwargs.get('extra', {})
        self.logger.debug(f"{message} | {json.dumps(extra)}")

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        extra = kwargs.get('extra', {})
        self.logger.warning(f"{message} | {json.dumps(extra)}")

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        extra = kwargs.get('extra', {})
        self.logger.error(f"{message} | {json.dumps(extra)}", exc_info=kwargs.get('exc_info', False))


# Predefined event types for observability
EVENT_TYPES = {
    'request_received': 'Debate request received',
    'clef_loaded': 'Clef model loaded',
    'clef_decision': 'Clef made a decision',
    'clef_unloaded': 'Clef model unloaded',
    'agent_loaded': 'Reasoning agent loaded',
    'agent_started': 'Agent started reasoning',
    'agent_completed': 'Agent completed reasoning',
    'agent_unloaded': 'Agent unloaded',
    'state_updated': 'Debate state updated',
    'loop_detected': 'Loop detected in debate',
    'consensus_detected': 'Consensus detected',
    'judge_started': 'Judge started',
    'judge_completed': 'Judge completed',
    'request_completed': 'Debate request completed',
    'error': 'Error occurred',
}


def get_logger(name: str = "hermes") -> HermesLogger:
    """Get a Hermes logger instance."""
    return HermesLogger(name)
