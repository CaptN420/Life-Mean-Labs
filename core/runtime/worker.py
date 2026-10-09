"""Core runtime — Worker interface and base implementation.

Adapted from Mia_Brain (External/Mia_Brain/CaptN-BRAIN-main/captn/runtime/base.py)
and captn/runtime/workers.py.

Plugin -> Worker: Renamed for clarity in the new architecture.
BaseWorker: Copied with minimal changes, adapted to new imports.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.events.message import Message

logger = logging.getLogger(__name__)


class Worker:
    """The base class for all workers and capabilities.

    Adapted from Mia_Brain's Plugin class.
    Renamed to Worker for clarity in the new architecture.
    """

    name: str = "base"

    def __init__(self, bus=None):
        self.bus = bus
        self.is_active = False

    def initialize(self) -> bool:
        """Setup resources, connections, etc."""
        logger.info(f"[{self.name}] Initializing...")
        self.is_active = True
        return True

    def execute(self, message: Message) -> None:
        """Process a message and publish a response back to the bus.

        To be implemented by subclasses.
        """
        raise NotImplementedError

    def shutdown(self) -> bool:
        """Cleanup resources."""
        logger.info(f"[{self.name}] Shutting down...")
        self.is_active = False
        return True


class BaseWorker(Worker):
    """Base worker implementation with default behavior.

    Copied from Mia_Brain/captn/runtime/workers.py with minimal adaptation.
    """

    def __init__(self, name: str, bus=None):
        super().__init__(bus)
        self.name = name
        self.is_active = True

    def initialize(self) -> bool:
        """Setup resources, connections, etc."""
        logger.info(f"[{self.name}] Initializing...")
        self.is_active = True
        return True

    def execute(self, message: Message) -> None:
        """Execute the logic for this specific worker.

        Publishes a response back to the bus.
        """
        payload = message.payload

        # Placeholder for actual logic - to be implemented by subclasses
        result = {
            "worker_name": self.name,
            "status": "success",
            "findings": []
        }

        response = Message(
            sender=self.name,
            destination="core",
            type="response",
            payload={
                "task_id": payload.get("task_id"),
                "current_step_plugin": self.name,
                "valid": True,
                "result": result
            }
        )

        if self.bus:
            self.bus.publish(response)
        else:
            logger.warning(f"Worker {self.name}: Response generated but bus not available.")


class DeterministicWorker(BaseWorker):
    """A worker that produces deterministic output for testing.

    Used in Phase 0 characterization tests.
    """

    def __init__(self, name: str, result: Dict[str, Any], bus=None):
        super().__init__(name, bus)
        self._result = result

    def execute(self, message: Message) -> None:
        payload = message.payload
        response = Message(
            sender=self.name,
            destination="core",
            type="response",
            payload={
                "task_id": payload.get("task_id"),
                "current_step_plugin": self.name,
                "valid": True,
                "result": self._result
            }
        )
        if self.bus:
            self.bus.publish(response)
