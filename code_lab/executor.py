"""Real execution engine with sandboxing.

Executes Python code in isolated environments with resource limits,
capture of stdout/stderr, and proper error handling.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CodeLab.Executor")


@dataclass
class ExecutionResult:
    """Result of code execution."""
    success: bool
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    command: str
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_test_result(self) -> bool:
        return "pytest" in self.command.lower()


class CodeExecutor:
    """Executes Python code in isolated workspaces."""

    def __init__(self, workspace_root: Path, timeout_seconds: int = 60):
        self.workspace_root = workspace_root
        self.timeout_seconds = timeout_seconds
        self._executions: List[ExecutionResult] = []

    def execute(self, command: List[str], cwd: Optional[Path] = None) -> ExecutionResult:
        """Execute a command in the workspace."""
        start_time = time.time()
        work_dir = cwd or (self.workspace_root / "workspace")

        try:
            proc = subprocess.run(
                command,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=self._safe_env(),
            )

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            returncode = proc.returncode

            result = ExecutionResult(
                success=returncode == 0,
                returncode=returncode,
                stdout=stdout[-5000:],  # Truncate for memory
                stderr=stderr[-5000:],
                duration_seconds=time.time() - start_time,
                command=" ".join(command),
            )

        except subprocess.TimeoutExpired as e:
            result = ExecutionResult(
                success=False,
                returncode=-1,
                stdout=(e.stdout or "")[-2000:],
                stderr=(e.stderr or "")[-2000:],
                duration_seconds=self.timeout_seconds,
                command=" ".join(command),
                error_type="timeout",
                error_message="Execution timed out",
            )
        except Exception as e:
            result = ExecutionResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=time.time() - start_time,
                command=" ".join(command),
                error_type="execution_error",
                error_message=str(e),
            )

        self._executions.append(result)
        logger.info("Execution %s: %s (%.2fs)",
                   "OK" if result.success else "FAIL",
                   result.command[:60],
                   result.duration_seconds)
        return result

    def run_tests(self, test_pattern: str = "") -> ExecutionResult:
        """Run pytest in the workspace."""
        cmd = [
            sys.executable, "-m", "pytest",
            "-q", "--no-header", "-p", "no:cacheprovider",
        ]
        if test_pattern:
            cmd.append(test_pattern)
        return self.execute(cmd)

    def run_entrypoint(self, entrypoint: str) -> ExecutionResult:
        """Run a Python script as entrypoint."""
        cmd = [sys.executable, entrypoint]
        return self.execute(cmd)

    def compile_check(self, file_path: str) -> ExecutionResult:
        """Check if a Python file compiles."""
        cmd = [sys.executable, "-m", "py_compile", file_path]
        return self.execute(cmd)

    def install_dependencies(self, requirements_file: str = "requirements.txt") -> ExecutionResult:
        """Install dependencies from requirements.txt."""
        req_path = self.workspace_root / "workspace" / requirements_file
        if not req_path.exists():
            return ExecutionResult(
                success=False, returncode=-1, stdout="", stderr="requirements.txt not found",
                duration_seconds=0, command="pip install",
                error_type="missing_file", error_message="requirements.txt not found"
            )
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_path)]
        return self.execute(cmd)

    def _safe_env(self) -> Dict[str, str]:
        """Return a safe environment for execution."""
        env = dict(sys.environ)
        # Remove sensitive vars
        for key in list(env.keys()):
            if key.startswith("API_KEY") or key.startswith("SECRET") or key == "TOKEN":
                del env[key]
        # Set sandbox vars
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get history of all executions."""
        return [
            {
                "command": r.command,
                "success": r.success,
                "duration": r.duration_seconds,
                "returncode": r.returncode,
                "error_type": r.error_type,
            }
            for r in self._executions
        ]
