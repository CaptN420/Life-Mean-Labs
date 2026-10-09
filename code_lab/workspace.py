"""Code Lab workspace manager.

Every run executes inside its own isolated directory tree. Generated code
never touches host paths outside the run workspace (rule 8/18). RAW data is
written once and never overwritten (rule 11).

Layout:
    code_lab/runs/<run_id>/
        workspace/          # writable: code the agents may change
        raw/                # immutable RAW provenance (append-only)
        logs/               # run logging
        artifacts/          # final outputs
        metadata.json       # full provenance
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import CodeLabConfig

logger = logging.getLogger("CodeLab.Workspace")

# Paths generated code is never allowed to reference.
_BLOCKED_PATH_FRAGMENTS = (
    "C:\\Users", "/Users/", "/home/", "/etc/", "/var/", "/proc/",
    "\\AccessToken", "\\credentials", ".ssh", "__pycache__", "site-packages",
)


class WorkspaceError(Exception):
    """Raised when a workspace/security boundary is violated."""


class CodeLabWorkspace:
    """Isolated directory workspace for one Code Lab run."""

    def __init__(self, config: CodeLabConfig, base_dir: Optional[Path] = None) -> None:
        # Runs land relative to the CWD when no base_dir is given, so they are
        # writable both in a source checkout AND a wheel install (never inside
        # site-packages, which may be read-only). Tests pass an explicit tmp
        # base_dir.
        base_dir = base_dir or (Path.cwd() / "code_lab_runs")
        self.base = base_dir
        self.root = base_dir / config.run_id
        self.workspace = self.root / "workspace"
        self.raw = self.root / "raw"
        self.logs = self.root / "logs"
        self.artifacts = self.root / "artifacts"
        self.metadata_path = self.root / "metadata.json"
        self.config = config
        self._safe_probe_done = False

    # ── lifecycle ─────────────────────────────────────────────────────────
    def create(self) -> "CodeLabWorkspace":
        """Create the run directory structure."""
        for d in (self.workspace, self.raw, self.logs, self.artifacts):
            d.mkdir(parents=True, exist_ok=True)
        self._write_metadata()
        return self

    def _write_metadata(self) -> None:
        """Write provenance metadata. Written once at create; append-only."""
        meta = self.config.to_dict()
        meta["workspace_root"] = str(self.root)
        meta["_created_once"] = True
        if not self.metadata_path.exists():
            self.metadata_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def cleanup(self) -> None:
        """Remove the run workspace entirely (manual user action only)."""
        # Destructive action — only called explicitly by user (rule 9).
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
            logger.info("Cleaned up workspace %s", self.root)

    # ── path safety ───────────────────────────────────────────────────────
    def resolve(self, rel_path: str) -> Path:
        """Resolve a run-relative path, refusing to escape the workspace."""
        base = self.workspace.resolve()
        target = (base / rel_path).resolve()
        if not str(target).startswith(str(base)):
            raise WorkspaceError(
                f"Path escapes workspace: {rel_path!r} -> {target} (blocked)"
            )
        # Refuse relative inputs that reference blocked host locations; the
        # absolute check is redundant (startsWith already constrains to the
        # workspace base), so inspect only the *relative* argument here.
        rel_lower = rel_path.replace("\\", "/").lower()
        for blk in _BLOCKED_PATH_FRAGMENTS:
            frag = blk.replace("\\", "/").lower()
            if frag and frag in rel_lower:
                raise WorkspaceError(
                    f"Path touches blocked location {blk!r}: {rel_path!r} (blocked for safety)"
                )
        return target

    def write_text(self, rel_path: str, content: str) -> Path:
        """Write a file inside the workspace (workspace is the source of truth)."""
        target = self.resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        bytes_len = len(content.encode("utf-8"))
        if bytes_len > self.config.max_output_bytes:
            raise WorkspaceError(
                f"File too large: {bytes_len} bytes > limit {self.config.max_output_bytes}"
            )
        target.write_text(content, encoding="utf-8")
        logger.info("Wrote workspace file %s (%d bytes)", rel_path, bytes_len)
        return target

    def read_text(self, rel_path: str) -> str:
        """Read a file from the workspace."""
        return self.resolve(rel_path).read_text(encoding="utf-8")

    def list_files(self, subdir: str = ".") -> List[str]:
        """List files (relative to workspace root) as strings."""
        base = self.workspace / subdir
        if not base.exists():
            return []
        return [
            str(p.relative_to(self.workspace))
            for p in sorted(base.rglob("*"))
            if p.is_file()
        ]

    # ── RAW (immutable) ───────────────────────────────────────────────────
    def append_raw(self, filename: str, entry: Dict[str, Any]) -> None:
        """Append a JSON line to an immutable RAW file (rules 11/15)."""
        path = self.raw / f"{filename}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def write_raw_snapshot(self, filename: str, data: Dict[str, Any]) -> Path:
        """Write a RAW snapshot. Refuses to overwrite an existing snapshot."""
        path = self.raw / f"{filename}.json"
        if path.exists():
            raise WorkspaceError(
                f"RAW snapshot already exists: {path.name} — not overwriting (immutable)."
            )
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        return path

    def read_raw(self, filename: str) -> List[Dict[str, Any]]:
        """Read all appended RAW lines of a given file."""
        path = self.raw / f"{filename}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ── command allowlist (security) ──────────────────────────────────────
    def assert_command_allowed(self, argv: Iterable[str]) -> None:
        """Refuse to run a command not on the allowlist (rule 8/18)."""
        argv = list(argv)
        if not argv:
            raise WorkspaceError("Empty command refused")
        base = argv[0]
        if base not in self.config.allowed_commands:
            raise WorkspaceError(
                f"Command {base!r} not on allowlist {list(self.config.allowed_commands)} — refused"
            )
        # '..' must not appear in any argument (path traversal).
        for arg in argv[1:]:
            if ".." in arg:
                raise WorkspaceError(f"Path traversal in command arg blocked: {arg!r}")


def clean_find_identity() -> str:
    """Return an identity string for the code lab package (used in provenance)."""
    from importlib.metadata import version

    try:
        return version("life_mean")
    except Exception:  # pragma: no cover
        return "0.0.0-dev"
