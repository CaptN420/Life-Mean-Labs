"""
ResourceLimits — CPU, memory, and time constraints for agent execution

Provides resource monitoring and enforcement for isolated processes.
Supports both Unix (resource module) and Windows (process priority).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("Life_mean.Lab.ResourceLimits")


@dataclass
class ResourceLimits:
    """
    Resource constraints for a sandboxed process.
    
    Attributes:
        max_cpu_percent: Maximum CPU usage percentage (0-100)
        max_memory_mb: Maximum memory in megabytes
        max_duration_seconds: Maximum execution time in seconds
        soft_limits: Apply soft limits (warnings) vs hard limits (kills)
    """
    max_cpu_percent: float = 100.0
    max_memory_mb: int = 2048  # 2GB default
    max_duration_seconds: int = 3600  # 1 hour default
    soft_limits: bool = True


@dataclass
class ResourceUsage:
    """Current resource usage snapshot."""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    elapsed_seconds: float = 0.0
    
    def exceeds_limits(self, limits: ResourceLimits) -> bool:
        """Check if current usage exceeds limits."""
        if self.cpu_percent > limits.max_cpu_percent:
            return True
        if self.memory_mb > limits.max_memory_mb:
            return True
        if self.elapsed_seconds > limits.max_duration_seconds:
            return True
        return False


class ProcessMonitor:
    """
    Monitors resource usage of a sandboxed process.
    
    Tracks CPU, memory, and elapsed time, enforcing limits as configured.
    """
    
    def __init__(
        self,
        process: subprocess.Popen,
        limits: ResourceLimits,
        run_id: str,
    ):
        """
        Initialize process monitor.
        
        Args:
            process: The subprocess to monitor
            limits: Resource constraints
            run_id: Unique identifier for this run
        """
        self.process = process
        self.limits = limits
        self.run_id = run_id
        self.start_time = time.time()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._current_usage = ResourceUsage()
        
        # Apply resource limits based on OS
        self._apply_limits()
    
    def _apply_limits(self):
        """Apply resource limits to the process."""
        if os.name == "posix":
            self._apply_unix_limits()
        else:
            self._apply_windows_limits()
    
    def _apply_unix_limits(self):
        """Apply Unix-style resource limits."""
        try:
            import resource
            
            # Set memory limit (RLIMIT_AS = address space size)
            max_memory_bytes = self.limits.max_memory_mb * 1024 * 1024
            resource.setrlimit(
                resource.RLIMIT_AS, 
                (max_memory_bytes, max_memory_bytes)
            )
            
            # Set CPU time limit
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (self.limits.max_duration_seconds, self.limits.max_duration_seconds)
            )
        except (ImportError, ValueError) as e:
            logger.warning("Could not apply Unix limits: %s", e)
    
    def _apply_windows_limits(self):
        """Apply Windows-style process priority."""
        try:
            import psutil
            
            proc = psutil.Process(self.process.pid)
            # Set below normal priority to reduce CPU impact
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except Exception as e:
            logger.warning("Could not apply Windows limits: %s", e)
    
    def start_monitoring(self):
        """Start background resource monitoring."""
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name=f"resource-monitor-{self.run_id}",
        )
        self._monitor_thread.start()
        logger.info("Resource monitoring started for run %s", self.run_id)
    
    def _monitor_loop(self):
        """Background loop to check resource usage."""
        while not self._stop_event.is_set():
            try:
                # Get current process stats
                if self.process.poll() is not None:
                    # Process already finished
                    break
                
                # Update elapsed time
                self._current_usage.elapsed_seconds = time.time() - self.start_time
                
                # Try to get CPU and memory usage
                try:
                    import psutil
                    proc = psutil.Process(self.process.pid)
                    stats = proc.cpu_percent(interval=0.1), proc.memory_info()
                    self._current_usage.cpu_percent = stats[0]
                    self._current_usage.memory_mb = stats[1].rss / (1024 * 1024)
                except Exception:
                    # psutil not available, use defaults
                    pass
                
                # Check limits
                if self._current_usage.exceeds_limits(self.limits):
                    logger.warning(
                        "Resource limit exceeded for run %s: CPU=%.1f%%, MEM=%.1fMB, TIME=%.1fs",
                        self.run_id,
                        self._current_usage.cpu_percent,
                        self._current_usage.memory_mb,
                        self._current_usage.elapsed_seconds,
                    )
                    if not self.limits.soft_limits:
                        self.process.terminate()
                        break
                
            except Exception as e:
                logger.error("Monitor error: %s", e)
                break
            
            # Check every second
            time.sleep(1)
    
    def stop_monitoring(self):
        """Stop resource monitoring."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
    
    @property
    def current_usage(self) -> ResourceUsage:
        """Get current resource usage snapshot."""
        return self._current_usage
    
    def is_running(self) -> bool:
        """Check if the monitored process is still running."""
        return self.process.poll() is None


def create_monitor(
    process: subprocess.Popen,
    limits: Optional[ResourceLimits] = None,
    run_id: str = "default",
) -> ProcessMonitor:
    """
    Create a resource monitor for a process.
    
    Args:
        process: The subprocess to monitor
        limits: Resource constraints (uses defaults if None)
        run_id: Unique identifier
        
    Returns:
        Configured ProcessMonitor
    """
    limits = limits or ResourceLimits()
    return ProcessMonitor(process, limits, run_id)
