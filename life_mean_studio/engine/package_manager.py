"""
Package Manager for Life_mean Studio.

Handles .lmpack format: a ZIP archive containing:
  - manifest.json (package metadata)
  - agents/*.json (agent definitions)
  - workflows/*.json (workflow definitions)

Security: never executes code from packages; validates paths against ZIP-slip;
enforces max size; strips secrets from exports.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LifeMean.Studio.PackageManager")

# Format version — bump when schema changes
FORMAT_VERSION = "1.0"

# Max package size (5 MB)
MAX_PACKAGE_SIZE = 5 * 1024 * 1024

# Keys to exclude from export (secrets)
SECRET_KEYS = {"api_key", "password", "secret", "token", "private_key"}


@dataclass
class PackageInfo:
    """Metadata about a .lmpack package."""

    name: str = ""
    format_version: str = ""
    package_version: str = ""
    agents_count: int = 0
    workflows_count: int = 0
    created_at: str = ""
    description: str = ""
    errors: List[str] = field(default_factory=list)


@dataclass
class ImportResult:
    """Result of an import operation."""

    success: bool
    message: str
    package_info: Optional[PackageInfo] = None
    agents_imported: int = 0
    workflows_imported: int = 0
    conflicts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    message: str
    path: Optional[Path] = None
    agents_exported: int = 0
    workflows_exported: int = 0
    errors: List[str] = field(default_factory=list)


class PackageManager:
    """Manages .lmpack package import/export."""

    def __init__(self, storage, agent_manager=None, workflow_manager=None):
        self.storage = storage
        self.agent_manager = agent_manager
        self.workflow_manager = workflow_manager

    # ---- Validation ----

    @staticmethod
    def _is_safe_path(arcname: str) -> bool:
        """Check that an arcname doesn't escape the archive root (ZIP-slip)."""
        # Normalize Windows backslashes to forward slashes first
        arcname = arcname.replace("\\", "/")
        if arcname.startswith("/") or arcname.startswith(".."):
            return False
        parts = Path(arcname).parts
        for part in parts:
            if part == "..":
                return False
        return True

    @staticmethod
    def _safe_arcname(relative_path: Path, root: Path) -> str:
        """Convert a relative path to a ZIP-safe arcname (forward slashes)."""
        arcname = str(relative_path.relative_to(root))
        return arcname.replace("\\", "/")

    @staticmethod
    def _strip_secrets(agent: Dict[str, Any]) -> Dict[str, Any]:
        """Remove secret keys from agent config before export."""
        safe = {}
        for key, value in agent.items():
            if key.lower() in SECRET_KEYS:
                continue
            if key == "config" and isinstance(value, dict):
                safe[key] = {k: v for k, v in value.items() if k.lower() not in SECRET_KEYS}
            else:
                safe[key] = value
        return safe

    # ---- Import ----

    def import_package(self, package_path: str) -> ImportResult:
        """
        Import a .lmpack package.

        Args:
            package_path: Path to the .lmpack file.

        Returns:
            ImportResult with success/failure info.
        """
        errors: List[str] = []
        conflicts: List[str] = []
        agents_imported = 0
        workflows_imported = 0
        package_info = PackageInfo()

        # Validate file exists
        path = Path(package_path)
        if not path.exists():
            return ImportResult(False, f"Package not found: {package_path}", errors=[f"File not found: {package_path}"])

        if not path.suffix == ".lmpack" and not path.name.endswith(".lmpack"):
            return ImportResult(False, "Invalid file type", errors=["Expected .lmpack extension"])

        # Validate size
        if path.stat().st_size > MAX_PACKAGE_SIZE:
            return ImportResult(False, "Package too large", errors=[f"Package exceeds {MAX_PACKAGE_SIZE // 1024 // 1024} MB limit"])

        # Open and validate ZIP
        try:
            with zipfile.ZipFile(path, "r") as zf:
                # Check for dangerous paths
                for name in zf.namelist():
                    if not self._is_safe_path(name):
                        return ImportResult(False, "Unsafe path in package", errors=[f"Dangerous arcname: {name}"])

                # Read manifest
                if "manifest.json" not in zf.namelist():
                    return ImportResult(False, "Invalid package: missing manifest.json", errors=["manifest.json required"])

                manifest_text = zf.read("manifest.json")
                try:
                    manifest = json.loads(manifest_text)
                except json.JSONDecodeError as e:
                    return ImportResult(False, "Invalid manifest JSON", errors=[f"Manifest parse error: {e}"])

                # Validate manifest schema
                if "name" not in manifest:
                    errors.append("Manifest missing 'name' field")
                if "format_version" not in manifest:
                    errors.append("Manifest missing 'format_version' field")

                package_info.name = manifest.get("name", "Unknown")
                package_info.format_version = manifest.get("format_version", "")
                package_info.package_version = manifest.get("package_version", "1.0")
                package_info.description = manifest.get("description", "")
                package_info.created_at = manifest.get("created_at", "")

                # Import agents
                if "agents" in manifest:
                    for agent_spec in manifest["agents"]:
                        # Handle both dict format and string ID format
                        if isinstance(agent_spec, str):
                            agent_id = agent_spec
                        else:
                            agent_id = agent_spec.get("id")
                        if not agent_id:
                            errors.append("Agent missing 'id' field")
                            continue

                        # Check if agent already exists (by name or id)
                        existing = self.storage.get_agent(agent_id)
                        if existing:
                            conflicts.append(f"Agent '{existing.get('name', agent_id)}' already exists — skipping")
                            continue

                        # Find agent JSON file (case-insensitive lookup)
                        agent_file = f"agents/{agent_id}.json"
                        if agent_file not in zf.namelist():
                            # Try case-insensitive lookup
                            agent_file_lower = agent_file.lower()
                            agent_file_found = None
                            for existing in zf.namelist():
                                if existing.lower() == agent_file_lower:
                                    agent_file_found = existing
                                    break
                            if agent_file_found:
                                agent_file = agent_file_found
                            else:
                                errors.append(f"Agent file missing: {agent_file}")
                                continue

                        try:
                            agent_data = json.loads(zf.read(agent_file))
                        except json.JSONDecodeError as e:
                            errors.append(f"Invalid agent JSON for {agent_id}: {e}")
                            continue

                        # Import agent
                        try:
                            self.storage.create_agent(
                                name=agent_data.get("name", agent_id),
                                system_prompt=agent_data.get("system_prompt", ""),
                                persona=agent_data.get("persona", "general"),
                                description=agent_data.get("description", ""),
                                model=agent_data.get("model"),
                                provider=agent_data.get("provider"),
                                config=agent_data.get("config", {}),
                                tools=agent_data.get("tools", []),
                            )
                            agents_imported += 1
                        except Exception as e:
                            errors.append(f"Failed to import agent '{agent_id}': {e}")

                # Import workflows
                if "workflows" in manifest and self.workflow_manager is not None:
                    for wf_spec in manifest["workflows"]:
                        # Handle both dict format and string ID format
                        if isinstance(wf_spec, str):
                            wf_id = wf_spec
                        else:
                            wf_id = wf_spec.get("id")
                        if not wf_id:
                            errors.append("Workflow missing 'id' field")
                            continue

                        # Check if workflow already exists
                        existing_wf = self.storage.get_workflow(wf_id)
                        if existing_wf:
                            conflicts.append(f"Workflow '{existing_wf.get('name', wf_id)}' already exists — skipping")
                            continue

                        wf_file = f"workflows/{wf_id}.json"
                        if wf_file not in zf.namelist():
                            errors.append(f"Workflow file missing: {wf_file}")
                            continue

                        try:
                            wf_data = json.loads(zf.read(wf_file))
                            # Import directly via storage since we have the raw config
                            self.storage.create_workflow(
                                name=wf_data.get("name", wf_id),
                                config=wf_data.get("config", {}),
                                description=wf_data.get("description", ""),
                            )
                            workflows_imported += 1
                        except Exception as e:
                            errors.append(f"Failed to import workflow '{wf_id}': {e}")

                package_info.agents_count = agents_imported
                package_info.workflows_count = workflows_imported

        except zipfile.BadZipFile:
            return ImportResult(False, "Corrupted package", errors=["Not a valid ZIP file"])
        except Exception as e:
            return ImportResult(False, f"Import failed: {e}", errors=[str(e)])

        if not errors and agents_imported == 0 and workflows_imported == 0:
            return ImportResult(False, "No content imported", errors=["Package contained no importable agents or workflows"])

        success = len(errors) == 0
        message = f"Imported {agents_imported} agent(s), {workflows_imported} workflow(s)"
        if conflicts:
            message += f"; {len(conflicts)} conflict(s) skipped"
        if errors:
            message += f"; {len(errors)} error(s)"

        return ImportResult(
            success=success,
            message=message,
            package_info=package_info,
            agents_imported=agents_imported,
            workflows_imported=workflows_imported,
            conflicts=conflicts,
            errors=errors,
        )

    # ---- Export ----

    def export_package(
        self,
        output_path: str,
        agent_ids: Optional[List[str]] = None,
        workflow_ids: Optional[List[str]] = None,
        package_name: Optional[str] = None,
    ) -> ExportResult:
        """
        Export agents and/or workflows to a .lmpack package.

        Args:
            output_path: Where to write the .lmpack file.
            agent_ids: List of agent IDs to export (None = all).
            workflow_ids: List of workflow IDs to export (None = all).
            package_name: Package display name (auto-generated if None).

        Returns:
            ExportResult with success/failure info.
        """
        errors: List[str] = []
        agents_exported = 0
        workflows_exported = 0

        # Gather agents
        all_agents = self.storage.list_agents()
        if agent_ids:
            agents_to_export = [a for a in all_agents if a["id"] in agent_ids]
            missing = set(agent_ids) - {a["id"] for a in agents_to_export}
            if missing:
                return ExportResult(False, "Some agents not found", errors=[f"Agent IDs not found: {', '.join(missing)}"])
        else:
            agents_to_export = all_agents

        # Gather workflows
        all_workflows = self.storage.list_workflows()
        if workflow_ids:
            workflows_to_export = [w for w in all_workflows if w["id"] in workflow_ids]
            missing = set(workflow_ids) - {w["id"] for w in workflows_to_export}
            if missing:
                return ExportResult(False, "Some workflows not found", errors=[f"Workflow IDs not found: {', '.join(missing)}"])
        else:
            workflows_to_export = all_workflows

        if not agents_to_export and not workflows_to_export:
            return ExportResult(False, "Nothing to export", errors=["No agents or workflows selected"])

        # Build package
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            manifest = {
                "format_version": FORMAT_VERSION,
                "name": package_name or f"Life_mean_Package_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "package_version": "1.0",
                "description": f"Exported on {datetime.now().isoformat()}",
                "created_at": datetime.now().isoformat(),
                "agents": [],
                "workflows": [],
            }

            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)

                # Write agents
                agents_dir = tmppath / "agents"
                agents_dir.mkdir()
                for agent in agents_to_export:
                    safe_agent = self._strip_secrets(agent)
                    agent_file = agents_dir / f"{agent['id']}.json"
                    with open(agent_file, "w", encoding="utf-8") as f:
                        json.dump(safe_agent, f, indent=2, ensure_ascii=False)
                    manifest["agents"].append({
                        "id": agent["id"],
                        "name": agent["name"],
                    })
                    agents_exported += 1

                # Write workflows
                workflows_dir = tmppath / "workflows"
                workflows_dir.mkdir()
                for wf in workflows_to_export:
                    wf_file = workflows_dir / f"{wf['id']}.json"
                    with open(wf_file, "w", encoding="utf-8") as f:
                        json.dump(wf, f, indent=2, ensure_ascii=False)
                    manifest["workflows"].append({
                        "id": wf["id"],
                        "name": wf["name"],
                    })
                    workflows_exported += 1

                # Write manifest
                with open(tmppath / "manifest.json", "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)

                # Create ZIP
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(tmppath):
                        for file in files:
                            file_path = Path(root) / file
                            arcname = self._safe_arcname(file_path, tmppath)
                            if not self._is_safe_path(arcname):
                                errors.append(f"Skipping unsafe path: {arcname}")
                                continue
                            zf.write(file_path, arcname)

        except Exception as e:
            return ExportResult(False, f"Export failed: {e}", errors=[str(e)])

        message = f"Exported {agents_exported} agent(s), {workflows_exported} workflow(s)"
        if errors:
            message += f"; {len(errors)} warning(s)"

        return ExportResult(
            success=True,
            message=message,
            path=path,
            agents_exported=agents_exported,
            workflows_exported=workflows_exported,
            errors=errors,
        )

    # ---- Info ----

    def get_package_info(self, package_path: str) -> Optional[PackageInfo]:
        """Read package metadata without importing."""
        path = Path(package_path)
        if not path.exists():
            return None

        try:
            with zipfile.ZipFile(path, "r") as zf:
                if "manifest.json" not in zf.namelist():
                    return None
                manifest = json.loads(zf.read("manifest.json"))
                info = PackageInfo(
                    name=manifest.get("name", "Unknown"),
                    format_version=manifest.get("format_version", ""),
                    package_version=manifest.get("package_version", "1.0"),
                    agents_count=len(manifest.get("agents", [])),
                    workflows_count=len(manifest.get("workflows", [])),
                    created_at=manifest.get("created_at", ""),
                    description=manifest.get("description", ""),
                )
                return info
        except Exception:
            return None
