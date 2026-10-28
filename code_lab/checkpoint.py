"""Checkpoint and rollback system for autonomous repair.

Saves project state before major repairs and enables rollback to known-good states.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CodeLab.Checkpoint")


class CheckpointManager:
    """Manages checkpoints for project state restoration."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.checkpoints_dir = workspace_root / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints: List[Dict[str, Any]] = []

    def save(self, name: str, files: Dict[str, str], metadata: Optional[Dict[str, Any]] = None) -> str:
        """Save a checkpoint of current project state."""
        cp_id = f"{name}_{int(time.time())}"
        checkpoint_path = self.checkpoints_dir / f"{cp_id}.json"

        # Save file contents
        checkpoint_data = {
            "id": cp_id,
            "name": name,
            "timestamp": time.time(),
            "files": files,
            "metadata": metadata or {},
        }

        checkpoint_path.write_text(json.dumps(checkpoint_data, indent=2), encoding="utf-8")
        self._checkpoints.append(checkpoint_data)

        logger.info("Checkpoint saved: %s (%d files)", cp_id, len(files))
        return cp_id

    def restore(self, checkpoint_id: str) -> bool:
        """Restore a checkpoint by ID."""
        for cp in reversed(self._checkpoints):
            if cp["id"] == checkpoint_id:
                return self._apply_checkpoint(cp)

        # Try loading from disk
        cp_path = self.checkpoints_dir / f"{checkpoint_id}.json"
        if cp_path.exists():
            try:
                data = json.loads(cp_path.read_text(encoding="utf-8"))
                return self._apply_checkpoint(data)
            except Exception as e:
                logger.error("Failed to restore checkpoint %s: %s", checkpoint_id, e)
                return False

        logger.warning("Checkpoint not found: %s", checkpoint_id)
        return False

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all available checkpoints."""
        result = []
        for cp_path in sorted(self.checkpoints_dir.glob("*.json")):
            try:
                data = json.loads(cp_path.read_text(encoding="utf-8"))
                result.append({
                    "id": data["id"],
                    "name": data.get("name", "unknown"),
                    "timestamp": data.get("timestamp", 0),
                    "files_count": len(data.get("files", {})),
                })
            except Exception:
                pass
        return result

    def auto_save(self, workspace_root: Path, prefix: str = "auto") -> str:
        """Automatically save current state from workspace."""
        files = {}
        workspace_path = workspace_root / "workspace"
        if workspace_path.exists():
            for f in workspace_path.rglob("*.py"):
                rel = str(f.relative_to(workspace_path))
                try:
                    files[rel] = f.read_text(encoding="utf-8")
                except Exception:
                    pass

        return self.save(f"{prefix}_{int(time.time())}", files)

    def _apply_checkpoint(self, checkpoint_data: Dict[str, Any]) -> bool:
        """Apply a checkpoint by restoring file contents."""
        try:
            files = checkpoint_data.get("files", {})
            for rel_path, content in files.items():
                target = self.workspace_root / "workspace" / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            logger.info("Checkpoint applied: %s (%d files)",
                       checkpoint_data.get("id", "unknown"), len(files))
            return True
        except Exception as e:
            logger.error("Failed to apply checkpoint: %s", e)
            return False

    def create_backup_before_repair(self, workspace_root: Path) -> str:
        """Create a backup before attempting a repair."""
        files = {}
        workspace_path = workspace_root / "workspace"
        if workspace_path.exists():
            for f in workspace_path.rglob("*"):
                if f.is_file():
                    rel = str(f.relative_to(workspace_path))
                    try:
                        files[rel] = f.read_text(encoding="utf-8")
                    except Exception:
                        pass

        return self.save("pre_repair", files)
