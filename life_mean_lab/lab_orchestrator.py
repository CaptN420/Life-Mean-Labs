"""
LabOrchestrator — Coordinates isolated agent execution

Manages the lifecycle of sandboxed runs, from workspace creation
to process monitoring and cleanup.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .sandbox import SandboxWorkspace
from .resource_limits import ResourceLimits, ProcessMonitor
from .abort_mechanism import AbortRegistry, RunContext

logger = logging.getLogger("Life_mean.Lab.Orchestrator")


class LabResult:
    """
    Result of a lab execution.
    
    Attributes:
        run_id: Unique identifier
        status: Execution status (success, failed, aborted)
        output: Captured stdout
        errors: Captured stderr
        exit_code: Process exit code
        duration_seconds: Execution time
        workspace_path: Path to the sandbox workspace
    """
    
    def __init__(
        self,
        run_id: str,
        status: str = "pending",
        output: str = "",
        errors: str = "",
        exit_code: Optional[int] = None,
        duration_seconds: float = 0.0,
        workspace_path: Optional[Path] = None,
    ):
        self.run_id = run_id
        self.status = status
        self.output = output
        self.errors = errors
        self.exit_code = exit_code
        self.duration_seconds = duration_seconds
        self.workspace_path = workspace_path


class LabOrchestrator:
    """
    Orchestrates isolated agent execution in sandboxes.
    
    Manages workspace creation, process lifecycle, resource monitoring,
    and result collection for sandboxed runs.
    """
    
    def __init__(
        self,
        abort_registry: Optional[AbortRegistry] = None,
        default_limits: Optional[ResourceLimits] = None,
    ):
        """
        Initialize the lab orchestrator.
        
        Args:
            abort_registry: Registry for tracking runs (creates new if None)
            default_limits: Default resource constraints
        """
        self.abort_registry = abort_registry or AbortRegistry()
        self.default_limits = default_limits or ResourceLimits()
        self._monitors: Dict[str, ProcessMonitor] = {}
    
    def create_workspace(self, workspace_id: str) -> SandboxWorkspace:
        """
        Create a new sandbox workspace.
        
        Args:
            workspace_id: Unique identifier
            
        Returns:
            Configured SandboxWorkspace
        """
        # Create workspace in temp directory with secure permissions
        import tempfile
        
        base_dir = Path(tempfile.gettempdir()) / "life_mean_lab"
        base_dir.mkdir(parents=True, exist_ok=True)
        
        workspace_path = base_dir / workspace_id
        
        return SandboxWorkspace(workspace_id, workspace_path)
    
    def execute(
        self,
        workspace: SandboxWorkspace,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        limits: Optional[ResourceLimits] = None,
        run_id: Optional[str] = None,
    ) -> LabResult:
        """
        Execute a command in the sandbox.
        
        Args:
            workspace: SandboxWorkspace to use
            command: Command to execute (as list of strings)
            env: Environment variables (merged with defaults)
            limits: Resource constraints (uses default if None)
            run_id: Unique identifier (auto-generated if None)
            
        Returns:
            LabResult with execution outcome
        """
        run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self)}"
        limits = limits or self.default_limits
        
        logger.info("Executing in sandbox %s: %s", workspace.workspace_id, command)
        
        # Prepare environment
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        
        # Start process
        try:
            process = subprocess.Popen(
                command,
                cwd=str(workspace.root_path),
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logger.error("Failed to start process: %s", e)
            return LabResult(
                run_id=run_id,
                status="failed",
                errors=f"Process startup failed: {e}",
                exit_code=-1,
                workspace_path=workspace.root_path,
            )
        
        # Register in abort registry
        context = self.abort_registry.register(run_id, process)
        
        # Start resource monitoring
        monitor = ProcessMonitor(process, limits, run_id)
        monitor.start_monitoring()
        self._monitors[run_id] = monitor
        
        # Wait for completion or abort
        try:
            stdout, stderr = process.communicate()
            exit_code = process.returncode
            
            # Check if aborted
            if context.abort_event.is_set():
                status = "aborted"
            elif exit_code == 0:
                status = "success"
            else:
                status = "failed"
            
            duration = (datetime.now().timestamp()) - context.start_time
            
            result = LabResult(
                run_id=run_id,
                status=status,
                output=stdout,
                errors=stderr,
                exit_code=exit_code,
                duration_seconds=duration,
                workspace_path=workspace.root_path,
            )
            
        except Exception as e:
            logger.error("Execution error: %s", e)
            result = LabResult(
                run_id=run_id,
                status="failed",
                errors=str(e),
                exit_code=-1,
                workspace_path=workspace.root_path,
            )
        finally:
            # Cleanup
            monitor.stop_monitoring()
            self.abort_registry.unregister(run_id)
            del self._monitors[run_id]
        
        logger.info("Run %s completed: %s", run_id, status)
        return result
    
    def abort(self, run_id: str) -> bool:
        """
        Abort a running session.
        
        Args:
            run_id: Run identifier
            
        Returns:
            True if abort was initiated
        """
        return self.abort_registry.abort(run_id)
    
    def list_runs(self) -> Dict[str, Any]:
        """
        List all registered runs.
        
        Returns:
            Dictionary of run information
        """
        runs = self.abort_registry.list_runs()
        return {
            "total": len(runs),
            "runs": runs,
        }


# Convenience function for quick execution
def execute_in_sandbox(
    workspace_id: str,
    command: List[str],
    **kwargs,
) -> LabResult:
    """
    Execute a command in a new sandbox workspace.
    
    Args:
        workspace_id: Unique identifier for the workspace
        command: Command to execute
        **kwargs: Additional arguments passed to LabOrchestrator.execute
        
    Returns:
        LabResult with execution outcome
    """
    orchestrator = LabOrchestrator()
    workspace = orchestrator.create_workspace(workspace_id)
    return orchestrator.execute(workspace, command, **kwargs)
