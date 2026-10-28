"""
Tests for life_mean_lab isolation components.

Verifies sandbox path validation, resource monitoring, and abort mechanisms.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase, main

from life_mean_lab.sandbox import SandboxWorkspace, SandboxError
from life_mean_lab.resource_limits import ResourceLimits, ProcessMonitor
from life_mean_lab.abort_mechanism import AbortRegistry
from life_mean_lab.lab_orchestrator import LabOrchestrator


class TestSandboxWorkspace(TestCase):
    """Test sandbox path validation."""
    
    def test_valid_path(self):
        """Valid paths within workspace should be accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = SandboxWorkspace("test", Path(tmpdir))
            result = workspace.validate_path("subdir/file.txt")
            self.assertTrue(str(result).startswith(tmpdir))
    
    def test_path_traversal_blocked(self):
        """Path traversal attempts should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = SandboxWorkspace("test", Path(tmpdir))
            
            # Test various traversal patterns
            patterns = [
                "../etc/passwd",
                "..\\windows\\system32",
                "subdir/../../etc",
            ]
            
            for pattern in patterns:
                with self.assertRaises(SandboxError):
                    workspace.validate_path(pattern)
    
    def test_escape_blocked(self):
        """Paths escaping sandbox should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = SandboxWorkspace("test", Path(tmpdir))
            
            # Try to escape using absolute path
            with self.assertRaises(SandboxError):
                workspace.validate_path("/etc/passwd")
    
    def test_temp_file_creation(self):
        """Temp files should be created within sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = SandboxWorkspace("test", Path(tmpdir))
            temp_file = workspace.create_temp_file(".txt")
            self.assertTrue(temp_file.exists())
            self.assertTrue(str(temp_file).startswith(tmpdir))
    
    def test_workspace_info(self):
        """Workspace info should report correct metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = SandboxWorkspace("test", Path(tmpdir))
            
            # Create a test file
            (Path(tmpdir) / "test.txt").write_text("hello")
            
            info = workspace.get_workspace_info()
            self.assertEqual(info["workspace_id"], "test")
            self.assertEqual(info["file_count"], 1)


class TestResourceLimits(TestCase):
    """Test resource limit enforcement."""
    
    def test_default_limits(self):
        """Default limits should be reasonable."""
        limits = ResourceLimits()
        self.assertEqual(limits.max_cpu_percent, 100.0)
        self.assertEqual(limits.max_memory_mb, 2048)
        self.assertEqual(limits.max_duration_seconds, 3600)
    
    def test_custom_limits(self):
        """Custom limits should override defaults."""
        limits = ResourceLimits(
            max_cpu_percent=50.0,
            max_memory_mb=1024,
            max_duration_seconds=60,
        )
        self.assertEqual(limits.max_cpu_percent, 50.0)
        self.assertEqual(limits.max_memory_mb, 1024)
        self.assertEqual(limits.max_duration_seconds, 60)


class TestAbortRegistry(TestCase):
    """Test abort mechanism."""
    
    def test_register_and_abort(self):
        """Runs should be registrable and abortable."""
        registry = AbortRegistry()
        
        # Register a run
        context = registry.register("run_123")
        self.assertEqual(context.run_id, "run_123")
        self.assertEqual(context.status, "pending")
        
        # Abort the run
        result = registry.abort("run_123")
        self.assertTrue(result)
        
        # Verify status updated
        context = registry.get_run("run_123")
        self.assertEqual(context.status, "aborted")
    
    def test_abort_nonexistent(self):
        """Aborting non-existent run should return False."""
        registry = AbortRegistry()
        result = registry.abort("nonexistent")
        self.assertFalse(result)
    
    def test_list_runs(self):
        """Should list all registered runs."""
        registry = AbortRegistry()
        
        registry.register("run_1")
        registry.register("run_2")
        
        runs = registry.list_runs()
        self.assertEqual(len(runs), 2)
        self.assertIn("run_1", runs)
        self.assertIn("run_2", runs)


class TestLabOrchestrator(TestCase):
    """Test lab orchestration."""
    
    def test_execute_simple_command(self):
        """Should execute simple commands in sandbox."""
        orchestrator = LabOrchestrator()
        workspace = orchestrator.create_workspace("test_exec")
        
        result = orchestrator.execute(
            workspace,
            ["echo", "hello world"],
            run_id="test_run_1",
        )
        
        self.assertEqual(result.status, "success")
        self.assertIn("hello world", result.output)
        self.assertEqual(result.exit_code, 0)
    
    def test_execute_with_limits(self):
        """Should respect resource limits."""
        orchestrator = LabOrchestrator()
        workspace = orchestrator.create_workspace("test_limits")
        
        # Set very strict limits with hard enforcement
        limits = ResourceLimits(
            max_duration_seconds=1,
            soft_limits=False,  # Kill on limit exceeded
        )
        
        result = orchestrator.execute(
            workspace,
            ["sleep", "5"],
            limits=limits,
            run_id="test_run_2",
        )
        
        # Should have been aborted due to timeout
        self.assertIn(result.status, ["aborted", "failed"])
    
    def test_workspace_isolation(self):
        """Workspace should be isolated from parent."""
        orchestrator = LabOrchestrator()
        workspace = orchestrator.create_workspace("test_isolate")
        
        # Execute a command that tries to access parent
        result = orchestrator.execute(
            workspace,
            ["python", "-c", "import os; print(os.getcwd())"],
            run_id="test_run_3",
        )
        
        self.assertEqual(result.status, "success")
        # Output should be the sandbox path, not parent
        self.assertIn(str(workspace.root_path), result.output)


if __name__ == "__main__":
    main()
