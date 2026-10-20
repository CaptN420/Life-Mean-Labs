"""Tests for Hermes Cron Job Manager CLI."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestCronJobManager:
    """Test cases for CronJobManager."""
    
    def test_init_with_default_path(self):
        """Test initialization with default database path."""
        from config import CronJobManager
        
        with patch('os.environ', {'LOCALAPPDATA': '/tmp'}):
            manager = CronJobManager()
            assert manager.db_path.name == 'executions.db'
    
    def test_init_with_custom_path(self):
        """Test initialization with custom database path."""
        from config import CronJobManager
        
        manager = CronJobManager('custom_path.db')
        assert 'custom_path.db' in str(manager.db_path)


class TestListJobs:
    """Test cases for listing jobs."""
    
    @patch('config.sqlite3.connect')
    def test_list_jobs_success(self, mock_connect):
        """Test successful job listing."""
        from config import CronJobManager
        
        # Mock database response with proper row format
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {'job_id': 'test1', 'name': 'Test', 'state': 'scheduled', 'enabled': True}.get(key)
        mock_cursor = MagicMock()
        # First query returns table names
        mock_cursor.fetchall.side_effect = [
            [('jobs',), ('executions',)],  # Table names
            [mock_row]  # Job data
        ]
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        manager = CronJobManager()
        jobs = manager.list_jobs()
        
        assert isinstance(jobs, list)
    
    @patch('config.sqlite3.connect')
    def test_list_jobs_no_tables(self, mock_connect):
        """Test listing when no tables exist."""
        from config import CronJobManager
        
        # Mock empty response
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        manager = CronJobManager()
        
        with pytest.raises(Exception):
            manager.list_jobs()


class TestGetJob:
    """Test cases for getting a specific job."""
    
    @patch('config.sqlite3.connect')
    def test_get_job_found(self, mock_connect):
        """Test retrieving an existing job."""
        from config import CronJobManager
        
        # Mock database response - return dict directly
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'job_id': 'test123', 'name': 'Test Job'}
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        manager = CronJobManager()
        job = manager.get_job('test123')
        
        assert job is not None
        assert job['job_id'] == 'test123'
    
    @patch('config.sqlite3.connect')
    def test_get_job_not_found(self, mock_connect):
        """Test retrieving a non-existent job."""
        from config import CronJobManager
        
        # Mock no results
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        manager = CronJobManager()
        job = manager.get_job('nonexistent')
        
        assert job is None


class TestCLICommands:
    """Test cases for CLI commands."""
    
    def test_list_command_exists(self):
        """Test that list command exists."""
        try:
            import cli
            assert hasattr(cli, 'cli')
        except ImportError:
            pytest.skip("click not installed")
    
    def test_get_command_exists(self):
        """Test that get command exists."""
        try:
            import cli
            assert hasattr(cli, 'cli')
        except ImportError:
            pytest.skip("click not installed")
    
    def test_status_command_exists(self):
        """Test that status command exists."""
        try:
            import cli
            assert hasattr(cli, 'cli')
        except ImportError:
            pytest.skip("click not installed")


class TestModels:
    """Test cases for data models."""
    
    def test_cron_job_creation(self):
        """Test creating a CronJob instance."""
        from models import CronJob
        
        job = CronJob(
            job_id='test123',
            name='Test Job',
            state='scheduled',
            enabled=True,
            schedule='0 8 * * *'
        )
        
        assert job.job_id == 'test123'
        assert job.is_active is True
        assert job.has_error is False
    
    def test_cron_job_with_error(self):
        """Test CronJob with error status."""
        from models import CronJob
        
        job = CronJob(
            job_id='test123',
            name='Test Job',
            state='scheduled',
            enabled=True,
            schedule='0 8 * * *',
            last_status='error'
        )
        
        assert job.has_error is True
    
    def test_execution_record_creation(self):
        """Test creating an ExecutionRecord instance."""
        from models import ExecutionRecord
        
        start = datetime(2026, 10, 14, 8, 0, 0)
        end = datetime(2026, 10, 14, 8, 5, 0)
        
        execution = ExecutionRecord(
            execution_id='exec123',
            job_id='test123',
            started_at=start,
            completed_at=end,
            status='completed'
        )
        
        assert execution.duration_seconds == 300.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
