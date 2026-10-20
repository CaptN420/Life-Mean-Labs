"""
AbortMechanism — Independent stop control for sandboxed processes

Provides a registry to track and abort running agent sessions.
Each run can be stopped independently without affecting others.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("Life_mean.Lab.Abort")


@dataclass
class RunContext:
    """
    Context for a running agent session.
    
    Attributes:
        run_id: Unique identifier
        process: The subprocess being monitored
        abort_event: Threading event for signaling abort
        start_time: When the run started
        status: Current execution status
    """
    run_id: str
    process: Optional[subprocess.Popen] = None
    abort_event: threading.Event = field(default_factory=threading.Event)
    start_time: float = 0.0
    status: str = "pending"  # pending, running, aborted, completed


class AbortRegistry:
    """
    Registry for tracking and aborting agent runs.
    
    Provides thread-safe management of active sessions
    and independent abort capability.
    """
    
    def __init__(self):
        self._runs: Dict[str, RunContext] = {}
        self._lock = threading.Lock()
    
    def register(
        self,
        run_id: str,
        process: Optional[subprocess.Popen] = None,
    ) -> RunContext:
        """
        Register a new run in the registry.
        
        Args:
            run_id: Unique identifier for this run
            process: The subprocess (if already started)
            
        Returns:
            Created RunContext
        """
        with self._lock:
            context = RunContext(
                run_id=run_id,
                process=process,
                start_time=__import__("time").time(),
                status="running" if process else "pending",
            )
            self._runs[run_id] = context
            logger.info("Registered run: %s", run_id)
            return context
    
    def unregister(self, run_id: str):
        """
        Remove a run from the registry.
        
        Args:
            run_id: Run identifier to remove
        """
        with self._lock:
            self._runs.pop(run_id, None)
            logger.info("Unregistered run: %s", run_id)
    
    def abort(self, run_id: str) -> bool:
        """
        Abort a running session.
        
        Signals the abort event and terminates the process if needed.
        
        Args:
            run_id: Run identifier to abort
            
        Returns:
            True if abort was initiated, False if not found
        """
        with self._lock:
            context = self._runs.get(run_id)
            if not context:
                logger.warning("Run not found for abort: %s", run_id)
                return False
            
            # Signal abort
            context.abort_event.set()
            context.status = "aborted"
            
            # Terminate process if running
            if context.process and context.process.poll() is None:
                logger.info("Terminating process for run: %s", run_id)
                self._terminate_process(context.process)
            
            return True
    
    def abort_all(self):
        """Abort all registered runs."""
        with self._lock:
            run_ids = list(self._runs.keys())
        
        for run_id in run_ids:
            self.abort(run_id)
    
    def get_run(self, run_id: str) -> Optional[RunContext]:
        """
        Get the context for a run.
        
        Args:
            run_id: Run identifier
            
        Returns:
            RunContext or None if not found
        """
        with self._lock:
            return self._runs.get(run_id)
    
    def list_runs(self) -> Dict[str, str]:
        """
        List all registered runs with their status.
        
        Returns:
            Dictionary mapping run_id to status
        """
        with self._lock:
            return {rid: ctx.status for rid, ctx in self._runs.items()}
    
    def _terminate_process(self, process: subprocess.Popen):
        """
        Terminate a subprocess safely.
        
        Args:
            process: The process to terminate
        """
        try:
            if process.poll() is None:
                # Try graceful termination first
                process.terminate()
                
                # Wait briefly for graceful shutdown
                import time
                process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force kill if still running
            process.kill()
        except Exception as e:
            logger.error("Error terminating process: %s", e)


# Global abort registry instance
_abort_registry = AbortRegistry()


def abort_run(run_id: str) -> bool:
    """
    Abort a specific run.
    
    Args:
        run_id: Run identifier
        
    Returns:
        True if abort was initiated
    """
    return _abort_registry.abort(run_id)


def get_abort_registry() -> AbortRegistry:
    """
    Get the global abort registry.
    
    Returns:
        AbortRegistry instance
    """
    return _abort_registry
