"""Python Execution Environment for Life_mean Studio.

Provides a controlled, sandboxed execution environment for running Python code
within the Studio UI. Supports multiple Python environments, module indexing,
and safe code execution with output capture.

Design rules:
  - Never execute untrusted code without explicit user action (Run button).
  - Isolate execution from the stable core — no side effects on Life_mean state.
  - Capture stdout/stderr for display in the UI.
  - Support module indexing for search functionality.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("LifeMean.Studio.PythonExecutor")


@dataclass
class ExecutionResult:
    """Result of a Python code execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    error_type: Optional[str] = None
    error_msg: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time_ms": self.execution_time_ms,
            "error_type": self.error_type,
            "error_msg": self.error_msg,
        }


@dataclass
class PythonEnvironment:
    """Represents a Python environment (system or venv)."""
    name: str
    path: str
    is_venv: bool = False
    python_executable: Optional[str] = None

    @property
    def executable(self) -> str:
        if self.python_executable:
            return self.python_executable
        # Default to python in the env's bin directory
        if self.is_venv:
            if os.name == "nt":
                return os.path.join(self.path, "Scripts", "python.exe")
            else:
                return os.path.join(self.path, "bin", "python3")
        return sys.executable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "is_venv": self.is_venv,
            "executable": self.executable,
        }


class PythonExecutor:
    """Controlled Python execution environment for Studio."""

    def __init__(self, envs: Optional[List[PythonEnvironment]] = None):
        self._envs: List[PythonEnvironment] = envs or []
        self._current_env: Optional[PythonEnvironment] = None
        self._module_index: Dict[str, Dict[str, Any]] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def register_environment(self, env: PythonEnvironment) -> bool:
        """Register a Python environment."""
        if not os.path.exists(env.executable):
            logger.warning("Python executable not found: %s", env.executable)
            return False
        with self._lock:
            self._envs.append(env)
        logger.info("Registered environment: %s", env.name)
        return True

    def list_environments(self) -> List[Dict[str, Any]]:
        """List all registered environments."""
        with self._lock:
            return [env.to_dict() for env in self._envs]

    def set_current_environment(self, name: str) -> bool:
        """Set the active Python environment."""
        with self._lock:
            for env in self._envs:
                if env.name == name and os.path.exists(env.executable):
                    self._current_env = env
                    return True
            return False

    def get_current_environment(self) -> Optional[Dict[str, Any]]:
        """Get the current environment info."""
        with self._lock:
            if self._current_env is None:
                # Default to system python
                default_env = PythonEnvironment(
                    name="System Python",
                    path=sys.prefix,
                    python_executable=sys.executable
                )
                if os.path.exists(default_env.executable):
                    return default_env.to_dict()
            return self._current_env.to_dict() if self._current_env else None

    def execute_code(
        self,
        code: str,
        timeout_seconds: float = 30.0,
        env_name: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute Python code in a controlled environment.

        Args:
            code: Python source code to execute.
            timeout_seconds: Maximum execution time.
            env_name: Optional environment name (overrides current).

        Returns:
            ExecutionResult with stdout, stderr, and status.
        """
        start_time = time.time()

        # Select environment
        if env_name:
            with self._lock:
                for env in self._envs:
                    if env.name == env_name:
                        selected_env = env
                        break
                else:
                    return ExecutionResult(
                        success=False,
                        stderr=f"Environment not found: {env_name}",
                        error_type="EnvironmentError",
                    )
        else:
            selected_env = self._current_env

        # Build command
        if selected_env and os.path.exists(selected_env.executable):
            python_cmd = selected_env.executable
        else:
            python_cmd = sys.executable

        # Write code to temp file for execution
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write(code)
            code_file = f.name

        try:
            import subprocess

            # Execute in a subprocess for isolation
            result = subprocess.run(
                [python_cmd, code_file],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=self._build_execution_env(),
            )

            execution_time = (time.time() - start_time) * 1000

            exec_result = ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time_ms=execution_time,
            )

            # Capture any exceptions from the subprocess
            if result.returncode != 0 and not result.stderr:
                exec_result.error_type = "RuntimeError"
                exec_result.error_msg = f"Execution failed with code {result.returncode}"
                exec_result.success = False

        except subprocess.TimeoutExpired:
            execution_time = (time.time() - start_time) * 1000
            exec_result = ExecutionResult(
                success=False,
                stderr="Execution timed out",
                exit_code=-1,
                execution_time_ms=execution_time,
                error_type="TimeoutError",
            )
        except Exception as exc:
            execution_time = (time.time() - start_time) * 1000
            exec_result = ExecutionResult(
                success=False,
                stderr=str(exc),
                exit_code=-1,
                execution_time_ms=execution_time,
                error_type=type(exc).__name__,
            )
        finally:
            # Clean up temp file
            try:
                os.unlink(code_file)
            except OSError:
                pass

        # Record in history
        with self._lock:
            self._execution_history.append({
                "timestamp": time.time(),
                "env": selected_env.name if selected_env else "system",
                "code_preview": code[:100] + "..." if len(code) > 100 else code,
                "result": exec_result.to_dict(),
            })

        return exec_result

    def _build_execution_env(self) -> Dict[str, str]:
        """Build execution environment variables."""
        env = os.environ.copy()
        # Restrict PYTHONPATH to prevent importing project code
        env.pop('PYTHONPATH', None)
        # Add a marker that we're in Studio sandbox mode
        env['LIFE_MEAN_STUDIO_SANDBOX'] = '1'
        return env

    def index_modules(self, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Index available Python modules for search."""
        import subprocess
        import json as json_mod

        results: Dict[str, Any] = {"modules": {}, "count": 0}

        # Get module list from selected environment or system
        env_cmd = [sys.executable, "-m", "pip", "list", "--format=json"]
        try:
            proc = subprocess.run(
                env_cmd,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            if proc.returncode == 0:
                modules = json_mod.loads(proc.stdout)
                for mod in modules:
                    name = mod.get("Name", "")
                    version = mod.get("Version", "")
                    results["modules"][name] = {
                        "name": name,
                        "version": version,
                        "type": "package",
                    }
                results["count"] = len(modules)
        except Exception as exc:
            logger.warning("Failed to index modules: %s", exc)

        # Also scan for built-in modules
        import pkgutil
        builtins = [m.name for m in pkgutil.iter_modules()]
        for name in builtins[:50]:  # Limit to first 50
            if name not in results["modules"]:
                results["modules"][name] = {
                    "name": name,
                    "version": "built-in",
                    "type": "builtin",
                }

        self._module_index = results
        return results

    def search_modules(self, query: str) -> List[Dict[str, Any]]:
        """Search indexed modules by name or description."""
        if not self._module_index:
            self.index_modules()

        query = query.lower()
        results = []
        for name, info in self._module_index.get("modules", {}).items():
            if query in name.lower():
                results.append(info)
        return results[:20]  # Limit results

    def get_execution_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent execution history."""
        with self._lock:
            return self._execution_history[-limit:]

    def clear_history(self) -> None:
        """Clear execution history."""
        with self._lock:
            self._execution_history.clear()

    def get_status(self) -> Dict[str, Any]:
        """Get executor status."""
        return {
            "environments": len(self._envs),
            "current_env": self.get_current_environment(),
            "modules_indexed": self._module_index.get("count", 0),
            "history_count": len(self._execution_history),
        }


# Module-level singleton for the Studio
_executor_instance: Optional[PythonExecutor] = None


def get_executor() -> PythonExecutor:
    """Get the global Python executor instance."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = PythonExecutor()
        # Auto-discover venvs in common locations
        _discover_venvs(_executor_instance)
    return _executor_instance


def _discover_venvs(executor: PythonExecutor) -> None:
    """Auto-discover Python virtual environments."""
    import glob

    # Common venv locations
    search_paths = [
        str(Path.home() / ".virtualenvs"),
        str(Path.home() / "Environments"),
        str(Path.cwd() / "venv"),
        str(Path.cwd() / ".venv"),
    ]

    for base in search_paths:
        if not os.path.exists(base):
            continue
        for item in os.listdir(base):
            venv_path = os.path.join(base, item)
            # Check if it's a valid venv
            python_exe = None
            if os.name == "nt":
                candidate = os.path.join(venv_path, "Scripts", "python.exe")
                if os.path.exists(candidate):
                    python_exe = candidate
            else:
                candidate = os.path.join(venv_path, "bin", "python3")
                if os.path.exists(candidate):
                    python_exe = candidate

            if python_exe:
                env = PythonEnvironment(
                    name=item,
                    path=venv_path,
                    is_venv=True,
                    python_executable=python_exe,
                )
                executor.register_environment(env)

    # Always add system Python as fallback
    system_env = PythonEnvironment(
        name="System Python",
        path=sys.prefix,
        python_executable=sys.executable,
    )
    executor.register_environment(system_env)
