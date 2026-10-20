"""
SandboxWorkspace — Isolated workspace with path restrictions

Ensures all file operations are confined to the designated workspace.
Blocks path traversal and enforces strict directory boundaries.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path, PurePosixPath
from typing import Optional

logger = logging.getLogger("Life_mean.Lab.Sandbox")


class SandboxError(Exception):
    """Raised when a sandbox violation is detected."""


class SandboxWorkspace:
    """
    Manages an isolated workspace for agent execution.
    
    All file operations must pass through this class to ensure
    they remain within the allowed workspace boundaries.
    """
    
    def __init__(self, workspace_id: str, root_path: Path):
        """
        Initialize sandbox workspace.
        
        Args:
            workspace_id: Unique identifier for this workspace
            root_path: Absolute path to the workspace root
        """
        self.workspace_id = workspace_id
        self.root_path = root_path.resolve()
        self._allowed_operations = set()
        
        # Ensure workspace exists
        self.root_path.mkdir(parents=True, exist_ok=True)
        
        logger.info("Sandbox initialized: %s at %s", workspace_id, self.root_path)
    
    def validate_path(self, requested_path: str | Path) -> Path:
        """
        Validate that a path is within the sandbox.
        
        Args:
            requested_path: Path to validate
            
        Returns:
            Resolved absolute path if valid
            
        Raises:
            SandboxError: If path escapes sandbox
        """
        if isinstance(requested_path, str):
            # Normalize and resolve
            normalized = requested_path.replace("\\", "/")
            
            # Block path traversal attempts
            if ".." in normalized.split("/"):
                raise SandboxError(
                    f"Path traversal detected: {requested_path}"
                )
            
            # Resolve against workspace root
            target = (self.root_path / normalized).resolve()
        else:
            target = requested_path.resolve()
        
        # Verify target is within sandbox
        try:
            target.relative_to(self.root_path)
        except ValueError:
            raise SandboxError(
                f"Path escapes sandbox: {target} not in {self.root_path}"
            )
        
        return target
    
    def create_temp_file(self, suffix: str = "") -> Path:
        """
        Create a temporary file within the sandbox.
        
        Args:
            suffix: File extension
            
        Returns:
            Path to created temp file
        """
        import tempfile
        
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            dir=str(self.root_path),
            delete=False
        ) as tmp:
            return Path(tmp.name)
    
    def create_temp_dir(self) -> Path:
        """
        Create a temporary directory within the sandbox.
        
        Returns:
            Path to created temp directory
        """
        import tempfile
        
        temp_dir = tempfile.mkdtemp(dir=str(self.root_path))
        return Path(temp_dir)
    
    def list_workspace(self, recursive: bool = False) -> list[Path]:
        """
        List all files in the workspace.
        
        Args:
            recursive: If True, include subdirectories
            
        Returns:
            List of paths
        """
        if recursive:
            return list(self.root_path.rglob("*"))
        return list(self.root_path.iterdir())
    
    def get_workspace_info(self) -> dict:
        """
        Get workspace metadata.
        
        Returns:
            Dictionary with workspace information
        """
        return {
            "workspace_id": self.workspace_id,
            "root_path": str(self.root_path),
            "file_count": len(list(self.root_path.iterdir())),
            "size_bytes": sum(
                f.stat().st_size 
                for f in self.root_path.rglob("*") 
                if f.is_file()
            ),
        }


def validate_path(workspace: SandboxWorkspace, path: str) -> Path:
    """
    Validate a path against the sandbox.
    
    Args:
        workspace: The sandbox to validate against
        path: Path to validate
        
    Returns:
        Validated absolute path
    """
    return workspace.validate_path(path)
