"""Configuration and database access for Hermes Cron Job Manager."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional


class CronConfigError(Exception):
    """Raised when there's an issue with cron configuration."""
    pass


class CronJobManager:
    """Manages access to Hermes cron job database."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize with database path.
        
        Args:
            db_path: Path to executions.db. Defaults to standard Hermes location.
        """
        if db_path is None:
            db_path = os.path.join(
                os.environ.get('LOCALAPPDATA', ''),
                'hermes',
                'cron',
                'executions.db'
            )
        self.db_path = Path(db_path)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection in read-only mode using URI."""
        if not self.db_path.exists():
            raise CronConfigError(f"Database not found: {self.db_path}")

        # CORRECTION D1: URI avec mode=ro explicite
        db_path_resolved = self.db_path.resolve()
        path_str = str(db_path_resolved).replace('\\', '/')
        uri = f"file:{path_str}?mode=ro&uri=true"
        conn = sqlite3.connect(uri, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def list_jobs(self) -> list[dict]:
        """List all cron jobs."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Try to get from jobs table if it exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            if 'jobs' in tables:
                cursor.execute("SELECT * FROM jobs")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

            # Fallback: check executions table
            if 'executions' in tables:
                cursor.execute("""
                    SELECT DISTINCT job_id, status, started_at
                    FROM executions
                    ORDER BY started_at DESC
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

            raise CronConfigError("No jobs found in database")

        except sqlite3.Error as e:
            raise CronConfigError(f"Database error: {e}")
        finally:
            if conn is not None:
                conn.close()
    
    def get_job(self, job_id: str) -> Optional[dict]:
        """Get a specific job by ID."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Try jobs table first
            cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Fallback to executions
            cursor.execute("""
                SELECT DISTINCT job_id, status, started_at
                FROM executions
                WHERE job_id = ?
                ORDER BY started_at DESC
                LIMIT 1
            """, (job_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            return None

        except sqlite3.Error as e:
            raise CronConfigError(f"Database error: {e}")
        finally:
            if conn is not None:
                conn.close()
    
    def get_job_stats(self, job_id: str) -> Optional[dict]:
        """Get execution statistics for a job."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Count executions
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                    AVG(duration_seconds) as avg_duration
                FROM executions
                WHERE job_id = ?
            """, (job_id,))
            stats = cursor.fetchone()

            if stats:
                return dict(stats)

            return None

        except sqlite3.Error as e:
            raise CronConfigError(f"Database error: {e}")
        finally:
            if conn is not None:
                conn.close()
    
    def update_job(self, job_id: str, updates: dict) -> bool:
        """Update a job configuration.

        THIS OPERATION IS FORBIDDEN IN READ-ONLY MODE.

        Args:
            job_id: The job ID to update
            updates: Dictionary of fields to update

        Returns:
            Always raises CronConfigError
        """
        raise CronConfigError(
            "Write operations are not allowed in read-only mode. "
            "This tool is for inspection only."
        )
    
    def get_last_executions(self, job_id: str, limit: int = 5) -> list[dict]:
        """Get recent executions for a job."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM executions
                WHERE job_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (job_id, limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            raise CronConfigError(f"Database error: {e}")
        finally:
            if conn is not None:
                conn.close()
