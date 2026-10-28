"""WorkspaceManager — Git worktree-based isolation for multi-agent code modification.

Provides isolated workspaces per branch/agent, preventing concurrent writes
to the main workspace and ensuring clean resource lifecycle management.

Design rules:
  - Each agent gets its own Git worktree (or temp dir for non-Git projects).
  - Branch state is tracked: modifications, test results, integration readiness.
  - No automatic destructive merges; explicit approval required.
  - Resources are cleaned up after success, failure, timeout, or cancellation.
  - Unsaved modifications are preserved unless explicitly discarded.
"""

from __future__ import annotations

import enum
import json
import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Life_mean.Orchestrator.WorkspaceManager")


# ── Branch state ─────────────────────────────────────────────────────────────


class WorkspaceBranchStatus(str, enum.Enum):
    """Lifecycle status of a branch/workspace."""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    TESTS_PASSING = "tests_passing"
    TESTS_FAILING = "tests_failing"
    CONFLICT_DETECTED = "conflict_detected"
    READY_FOR_INTEGRATION = "ready_for_integration"
    MERGED = "merged"
    DISCARDED = "discarded"
    FAILED = "failed"


@dataclass
class TestResult:
    """Outcome of running tests in a branch."""
    passed: bool
    output: str = ""
    returncode: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class BranchInfo:
    """State and metadata for an isolated branch/workspace."""
    branch_id: str
    workspace_path: Path
    status: WorkspaceBranchStatus = WorkspaceBranchStatus.CREATED
    modifications: Dict[str, Any] = field(default_factory=dict)
    test_result: Optional[TestResult] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            WorkspaceBranchStatus.MERGED,
            WorkspaceBranchStatus.DISCARDED,
            WorkspaceBranchStatus.FAILED,
        )

    @property
    def is_ready_for_integration(self) -> bool:
        return self.status == WorkspaceBranchStatus.READY_FOR_INTEGRATION


# ── WorkspaceManager ─────────────────────────────────────────────────────────


class WorkspaceManager:
    """Manages isolated workspaces using Git worktrees or temp directories."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        max_workspaces: int = 10,
        cleanup_on_delete: bool = True,
    ) -> None:
        """
        Args:
            base_dir: Root directory for workspaces (default: temp/life_mean_workspaces).
            max_workspaces: Maximum concurrent workspaces.
            cleanup_on_delete: Remove workspace files when deleted.
        """
        self.base_dir = Path(base_dir or tempfile.mkdtemp(prefix="life_mean_workspaces_"))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_workspaces = max_workspaces
        self.cleanup_on_delete = cleanup_on_delete

        self._branches: Dict[str, BranchInfo] = {}
        self._lock = None  # Simplified: no explicit lock for now

    @property
    def branch_count(self) -> int:
        return len(self._branches)

    @property
    def active_branches(self) -> List[BranchInfo]:
        return [b for b in self._branches.values() if not b.is_terminal]

    def create_workspace(
        self,
        branch_id: str,
        source_path: Optional[Path] = None,
        use_git_worktree: bool = True,
    ) -> BranchInfo:
        """Create an isolated workspace for a branch.

        Args:
            branch_id: Unique identifier for the branch.
            source_path: Path to copy from (for temp dirs) or Git repo root (for worktrees).
            use_git_worktree: If True, use Git worktree; otherwise use temp dir.

        Returns:
            BranchInfo for the new workspace.
        """
        if self.branch_count >= self.max_workspaces:
            raise RuntimeError(f"Maximum workspaces ({self.max_workspaces}) reached")

        if branch_id in self._branches:
            raise ValueError(f"Branch '{branch_id}' already exists")

        workspace_path = self.base_dir / branch_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        if use_git_worktree and source_path:
            self._init_git_worktree(str(source_path), str(workspace_path))
        elif source_path:
            shutil.copytree(source_path, workspace_path, dirs_exist_ok=True)

        branch = BranchInfo(
            branch_id=branch_id,
            workspace_path=workspace_path,
            status=WorkspaceBranchStatus.CREATED,
        )
        self._branches[branch_id] = branch
        logger.info("Created workspace '%s' at %s", branch_id, workspace_path)
        return branch

    def _init_git_worktree(self, repo_path: str, worktree_path: str) -> None:
        """Initialize a Git worktree for the given repo."""
        try:
            subprocess.run(
                ["git", "worktree", "add", worktree_path],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning("Failed to create Git worktree: %s", e.stderr)
            # Fallback to simple copy.
            if Path(repo_path).exists():
                shutil.copytree(repo_path, worktree_path, dirs_exist_ok=True)

    def get_branch(self, branch_id: str) -> Optional[BranchInfo]:
        """Get branch info by ID."""
        return self._branches.get(branch_id)

    def update_status(self, branch_id: str, status: WorkspaceBranchStatus) -> None:
        """Update branch status."""
        if branch_id in self._branches:
            self._branches[branch_id].status = status
            self._branches[branch_id].updated_at = time.time()

    def run_tests(
        self,
        branch_id: str,
        test_command: Optional[List[str]] = None,
        timeout_seconds: float = 60.0,
    ) -> TestResult:
        """Run tests in a branch workspace.

        Args:
            branch_id: Branch to test.
            test_command: Command to run (default: pytest -q).
            timeout_seconds: Maximum execution time.

        Returns:
            TestResult with outcome.
        """
        branch = self._branches.get(branch_id)
        if branch is None:
            return TestResult(passed=False, errors=[f"Branch '{branch_id}' not found"])

        cmd = test_command or ["python", "-m", "pytest", "-q", "--no-header"]
        start = time.time()

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(branch.workspace_path),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration = time.time() - start
            passed = proc.returncode == 0
            result = TestResult(
                passed=passed,
                output=proc.stdout or "",
                returncode=proc.returncode,
                duration_seconds=duration,
                errors=[] if passed else [proc.stderr or "Tests failed"],
            )
            branch.test_result = result
            self.update_status(
                branch_id,
                WorkspaceBranchStatus.TESTS_PASSING if passed else WorkspaceBranchStatus.TESTS_FAILING,
            )
            return result
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            return TestResult(
                passed=False,
                errors=[f"Test timeout after {timeout_seconds}s"],
                duration_seconds=duration,
            )
        except Exception as e:
            duration = time.time() - start
            return TestResult(
                passed=False,
                errors=[str(e)],
                duration_seconds=duration,
            )

    def detect_conflicts(self, branch_id: str) -> List[str]:
        """Detect merge conflicts for a branch.

        Args:
            branch_id: Branch to check.

        Returns:
            List of conflict descriptions.
        """
        branch = self._branches.get(branch_id)
        if branch is None:
            return [f"Branch '{branch_id}' not found"]

        # Check for uncommitted changes that might conflict.
        conflicts = []
        workspace = branch.workspace_path
        if (workspace / ".git").exists():
            try:
                proc = subprocess.run(
                    ["git", "diff", "--name-only", "--diff-filter=U"],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                )
                if proc.stdout.strip():
                    conflicts.append(f"Unmerged files: {proc.stdout.strip()}")
            except Exception as e:
                conflicts.append(f"Conflict detection error: {e}")

        branch.metadata["conflicts"] = conflicts
        if conflicts:
            self.update_status(branch_id, WorkspaceBranchStatus.CONFLICT_DETECTED)
        return conflicts

    def mark_ready_for_integration(self, branch_id: str) -> bool:
        """Mark a branch as ready for manual integration.

        Args:
            branch_id: Branch to mark.

        Returns:
            True if marked successfully.
        """
        branch = self._branches.get(branch_id)
        if branch is None:
            return False

        # Require tests to pass.
        if branch.test_result is None or not branch.test_result.passed:
            logger.warning("Branch '%s' cannot be marked ready: tests not passing", branch_id)
            return False

        # Check for conflicts.
        conflicts = self.detect_conflicts(branch_id)
        if conflicts:
            logger.warning("Branch '%s' has conflicts: %s", branch_id, conflicts)
            return False

        self.update_status(branch_id, WorkspaceBranchStatus.READY_FOR_INTEGRATION)
        logger.info("Branch '%s' is ready for integration", branch_id)
        return True

    def approve_merge(self, branch_id: str, target_branch: str = "main") -> bool:
        """Approve and perform a non-destructive merge.

        This is an explicit approval step — no automatic merges.

        Args:
            branch_id: Branch to merge.
            target_branch: Target branch name.

        Returns:
            True if merge succeeded.
        """
        branch = self._branches.get(branch_id)
        if branch is None:
            return False

        if branch.status != WorkspaceBranchStatus.READY_FOR_INTEGRATION:
            logger.warning("Branch '%s' is not ready for integration", branch_id)
            return False

        # Perform merge (non-destructive: creates merge commit, doesn't force).
        workspace = branch.workspace_path
        if (workspace / ".git").exists():
            try:
                proc = subprocess.run(
                    ["git", "merge", "--no-ff", "-m", f"Merge branch {branch_id}"],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                )
                if proc.returncode == 0:
                    self.update_status(branch_id, WorkspaceBranchStatus.MERGED)
                    logger.info("Branch '%s' merged successfully", branch_id)
                    return True
                else:
                    logger.warning("Merge failed for '%s': %s", branch_id, proc.stderr)
                    return False
            except Exception as e:
                logger.error("Merge error: %s", e)
                return False
        else:
            # Non-Git workspace: mark as merged (manual integration required).
            self.update_status(branch_id, BranchStatus.MERGED)
            return True

    def discard_branch(self, branch_id: str, preserve_files: bool = False) -> bool:
        """Discard a branch and optionally clean up files.

        Args:
            branch_id: Branch to discard.
            preserve_files: If True, keep workspace files for inspection.

        Returns:
            True if discarded successfully.
        """
        branch = self._branches.get(branch_id)
        if branch is None:
            return False

        self.update_status(branch_id, WorkspaceBranchStatus.DISCARDED)
        logger.info("Branch '%s' discarded", branch_id)

        if not preserve_files and self.cleanup_on_delete:
            self._cleanup_workspace(branch_id)

        return True

    def _cleanup_workspace(self, branch_id: str) -> None:
        """Remove workspace files."""
        branch = self._branches.get(branch_id)
        if branch is None:
            return

        workspace = branch.workspace_path
        try:
            if (workspace / ".git").exists():
                # Remove Git worktree.
                subprocess.run(
                    ["git", "worktree", "remove", str(workspace)],
                    capture_output=True,
                )
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
            logger.info("Cleaned up workspace '%s'", branch_id)
        except Exception as e:
            logger.warning("Cleanup failed for '%s': %s", branch_id, e)

    def cleanup_all(self, preserve_files: bool = False) -> int:
        """Cleanup all branches.

        Args:
            preserve_files: If True, keep workspace files.

        Returns:
            Number of branches cleaned up.
        """
        count = 0
        for branch_id in list(self._branches.keys()):
            if self.discard_branch(branch_id, preserve_files):
                count += 1
        return count

    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary of all branches."""
        return {
            "total": len(self._branches),
            "active": len(self.active_branches),
            "branches": {
                bid: {
                    "status": b.status.value,
                    "tests_passed": b.test_result.passed if b.test_result else None,
                    "created_at": b.created_at,
                    "updated_at": b.updated_at,
                }
                for bid, b in self._branches.items()
            },
        }
