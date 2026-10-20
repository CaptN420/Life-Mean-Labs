"""Models for Hermes Cron Job Manager."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CronJob:
    """Represents a scheduled cron job."""
    
    job_id: str
    name: str
    state: str  # "scheduled", "running", "completed", "error"
    enabled: bool
    schedule: str  # cron expression
    last_run_at: Optional[str] = None
    last_status: Optional[str] = None  # "ok", "error", "delivery_failed"
    last_error: Optional[str] = None
    next_run_at: Optional[str] = None
    arguments: dict = field(default_factory=dict)
    
    @property
    def is_active(self) -> bool:
        """Check if job is currently enabled and scheduled."""
        return self.enabled and self.state == "scheduled"
    
    @property
    def has_error(self) -> bool:
        """Check if job has any error status."""
        return self.last_status in ("error", "delivery_failed") if self.last_status else False


@dataclass
class ExecutionRecord:
    """Represents a single execution of a cron job."""
    
    execution_id: str
    job_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"  # "running", "completed", "error"
    output: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
