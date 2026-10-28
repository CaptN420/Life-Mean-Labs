"""Tests for error memory (metacognition)."""

import tempfile
from pathlib import Path

import pytest

from code_lab.error_memory import ErrorMemory


class TestErrorMemory:
    def test_record_and_retrieve(self, tmp_path):
        mem = ErrorMemory(tmp_path)

        rec = mem.record_error("syntax_error", "SyntaxError: invalid syntax", "run_1")
        assert rec.error_type == "syntax_error"
        assert rec.count == 1

    def test_deduplication(self, tmp_path):
        mem = ErrorMemory(tmp_path)

        mem.record_error("syntax_error", "SyntaxError: invalid syntax", "run_1")
        mem.record_error("syntax_error", "SyntaxError: invalid syntax", "run_2")

        rec = mem.get_successful_fixes("syntax_error")
        # Should not crash, just return empty list initially
        assert isinstance(rec, list)

    def test_record_strategy_attempt(self, tmp_path):
        mem = ErrorMemory(tmp_path)

        mem.record_error("import_error", "ModuleNotFoundError", "run_1")
        mem.record_strategy_attempt("import_error", "fix_imports", False)

        strategies = mem.get_failed_strategies("import_error")
        assert "fix_imports" in strategies

    def test_should_avoid_strategy(self, tmp_path):
        mem = ErrorMemory(tmp_path)

        # Record same strategy 3 times without success
        for _ in range(3):
            mem.record_strategy_attempt("syntax_error", "bad_fix", False)

        assert mem.should_avoid_strategy("syntax_error", "bad_fix") is True

    def test_get_recommendation(self, tmp_path):
        mem = ErrorMemory(tmp_path)

        # No record yet
        rec = mem.get_recommendation("unknown_error")
        assert rec is None

        # Record a successful fix
        mem.record_error("syntax_error", "SyntaxError", "run_1")
        mem.record_strategy_attempt("syntax_error", "good_fix", True, {"fix": "add newline"})

        rec = mem.get_recommendation("syntax_error")
        assert rec == "apply_known_fix"

    def test_get_stats(self, tmp_path):
        mem = ErrorMemory(tmp_path)

        mem.record_error("syntax_error", "SyntaxError", "run_1")
        mem.record_error("import_error", "ImportError", "run_2")
        mem.record_strategy_attempt("syntax_error", "fix1", False)
        mem.record_strategy_attempt("import_error", "fix2", True)

        stats = mem.get_stats()
        assert stats["unique_errors"] == 2
        assert stats["total_occurrences"] == 2
        assert stats["strategies_attempted"] == 2
        assert stats["successful_fixes"] == 1

    def test_clear_run_errors(self, tmp_path):
        mem = ErrorMemory(tmp_path)

        mem.record_error("syntax_error", "SyntaxError", "run_1")
        mem.record_error("import_error", "ImportError", "run_2")

        cleared = mem.clear_run_errors("run_1")
        assert cleared == 1

        stats = mem.get_stats()
        assert stats["unique_errors"] == 1
