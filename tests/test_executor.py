"""Tests for code executor with sandboxing."""

import tempfile
from pathlib import Path

import pytest

from code_lab.executor import CodeExecutor, ExecutionResult


class TestExecutionResult:
    def test_is_test_result(self):
        result = ExecutionResult(
            success=True,
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=1.0,
            command="python -m pytest",
        )
        assert result.is_test_result is True

    def test_not_test_result(self):
        result = ExecutionResult(
            success=True,
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=1.0,
            command="python script.py",
        )
        assert result.is_test_result is False


class TestCodeExecutor:
    def test_run_tests(self, tmp_path):
        executor = CodeExecutor(tmp_path)

        # Create a simple test file
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "test_example.py").write_text(
            "def test_pass():\n    assert 1 == 1\n",
            encoding="utf-8"
        )

        result = executor.run_tests()
        assert result.success is True
        assert "1 passed" in result.stdout

    def test_run_tests_fails(self, tmp_path):
        executor = CodeExecutor(tmp_path)

        # Create a failing test
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "test_example.py").write_text(
            "def test_fail():\n    assert 1 == 2\n",
            encoding="utf-8"
        )

        result = executor.run_tests()
        assert result.success is False

    def test_compile_check(self, tmp_path):
        executor = CodeExecutor(tmp_path)

        # Create a valid Python file
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "example.py").write_text(
            "def hello():\n    return 'world'\n",
            encoding="utf-8"
        )

        result = executor.compile_check("example.py")
        assert result.success is True

    def test_compile_check_syntax_error(self, tmp_path):
        executor = CodeExecutor(tmp_path)

        # Create a file with syntax error
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "bad.py").write_text(
            "def broken(:\n    pass\n",
            encoding="utf-8"
        )

        result = executor.compile_check("bad.py")
        assert result.success is False

    def test_get_execution_history(self, tmp_path):
        executor = CodeExecutor(tmp_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "test_example.py").write_text(
            "def test_pass():\n    assert 1 == 1\n",
            encoding="utf-8"
        )

        executor.run_tests()
        history = executor.get_execution_history()
        assert len(history) == 1
        assert history[0]["success"] is True
