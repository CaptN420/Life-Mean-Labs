"""Tests for checkpoint and rollback system."""

import tempfile
from pathlib import Path

import pytest

from code_lab.checkpoint import CheckpointManager


class TestCheckpointManager:
    def test_save_and_restore(self, tmp_path):
        manager = CheckpointManager(tmp_path)

        # Save a checkpoint
        cp_id = manager.save("test", {"main.py": "x = 1", "test.py": "def test(): pass"})
        assert cp_id.startswith("test_")

        # List checkpoints
        cps = manager.list_checkpoints()
        assert len(cps) == 1
        assert cps[0]["name"] == "test"

    def test_restore_restores_files(self, tmp_path):
        manager = CheckpointManager(tmp_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create initial files
        (workspace / "main.py").write_text("x = 1", encoding="utf-8")
        (workspace / "test.py").write_text("def test(): pass", encoding="utf-8")

        # Save checkpoint
        cp_id = manager.save("before_change", {"main.py": "x = 1", "test.py": "def test(): pass"})

        # Modify files
        (workspace / "main.py").write_text("x = 2", encoding="utf-8")
        (workspace / "test.py").write_text("def test(): fail", encoding="utf-8")

        # Restore checkpoint
        assert manager.restore(cp_id) is True

        # Verify files restored
        assert (workspace / "main.py").read_text(encoding="utf-8") == "x = 1"
        assert (workspace / "test.py").read_text(encoding="utf-8") == "def test(): pass"

    def test_auto_save(self, tmp_path):
        manager = CheckpointManager(tmp_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create some files
        (workspace / "main.py").write_text("x = 1", encoding="utf-8")
        (workspace / "test.py").write_text("def test(): pass", encoding="utf-8")

        # Auto save
        cp_id = manager.auto_save(tmp_path, "auto")
        assert cp_id.startswith("auto_")

        cps = manager.list_checkpoints()
        assert len(cps) == 1
        assert cps[0]["files_count"] == 2

    def test_create_backup_before_repair(self, tmp_path):
        manager = CheckpointManager(tmp_path)
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create some files
        (workspace / "main.py").write_text("x = 1", encoding="utf-8")

        # Create backup
        cp_id = manager.create_backup_before_repair(tmp_path)
        assert cp_id.startswith("pre_repair_")

        cps = manager.list_checkpoints()
        assert len(cps) == 1
        assert cps[0]["name"] == "pre_repair"

    def test_restore_nonexistent(self, tmp_path):
        manager = CheckpointManager(tmp_path)
        assert manager.restore("nonexistent") is False
