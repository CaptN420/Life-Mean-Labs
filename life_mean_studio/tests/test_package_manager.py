"""
Tests for Life_mean Studio package manager (.lmpack format).

Covers: valid import/export, round-trip, corrupted packages, invalid manifests,
duplicate handling, ZIP-slip protection, secret stripping, and size limits.
"""

import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

from life_mean_studio.engine.storage import StudioStorage
from life_mean_studio.engine.package_manager import (
    PackageManager,
    PackageInfo,
    ImportResult,
    ExportResult,
    FORMAT_VERSION,
    MAX_PACKAGE_SIZE,
)


@pytest.fixture
def tmpdb():
    """Create a temp DB file and return its path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name


@pytest.fixture
def storage(tmpdb):
    """Create storage backed by a temp DB."""
    s = StudioStorage(db_path=tmpdb)
    yield s
    try:
        os.unlink(tmpdb)
    except OSError:
        pass


@pytest.fixture
def workflow_manager(storage):
    """Create a WorkflowManager bound to the test storage."""
    from life_mean_studio.workflows.manager import WorkflowManager
    return WorkflowManager(storage)


@pytest.fixture
def package_manager(storage, workflow_manager):
    """Create a PackageManager bound to the test storage."""
    return PackageManager(storage, workflow_manager=workflow_manager)


@pytest.fixture
def sample_agent():
    """Return a minimal agent dict for testing."""
    return {
        "id": "test-agent-001",
        "name": "Test Agent",
        "persona": "general",
        "system_prompt": "You are a test agent.",
        "model": "qwen3.5-2b",
        "provider": "lm-studio",
        "config": {"temperature": 0.7},
        "tools": ["reasoning"],
    }


@pytest.fixture
def sample_workflow():
    """Return a minimal workflow dict for testing."""
    return {
        "id": "test-wf-001",
        "name": "Test Workflow",
        "version": "1.0",
        "config": {"mode": "single", "domain": "philosophy", "num_tasks": 5},
    }


# =============================================================================
# Export tests
# =============================================================================

class TestExport:
    """Test package export functionality."""

    def test_export_empty_fails(self, storage, package_manager, tmp_path):
        """Export with nothing to export returns failure."""
        result = package_manager.export_package(str(tmp_path / "test.lmpack"))
        assert not result.success
        assert "Nothing to export" in result.message

    def test_export_single_agent(self, storage, package_manager, sample_agent, tmp_path):
        """Export a single agent produces a valid .lmpack."""
        aid = storage.create_agent(
            name=sample_agent["name"],
            system_prompt=sample_agent["system_prompt"],
            persona=sample_agent["persona"],
            model=sample_agent["model"],
            provider=sample_agent["provider"],
            config=sample_agent["config"],
            tools=sample_agent["tools"],
        )
        out = tmp_path / "export.lmpack"
        result = package_manager.export_package(str(out), agent_ids=[aid])

        assert result.success
        assert result.agents_exported == 1
        assert out.exists()
        assert out.suffix == ".lmpack"

        # Validate ZIP structure
        with zipfile.ZipFile(out, "r") as zf:
            assert "manifest.json" in zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["format_version"] == FORMAT_VERSION
            assert len(manifest["agents"]) == 1
            assert manifest["agents"][0]["name"] == "Test Agent"
            # The exported agent ID should match the one we exported
            assert manifest["agents"][0]["id"] == aid
            assert f"agents/{aid}.json" in zf.namelist()

    def test_export_single_workflow(self, storage, package_manager, sample_workflow, tmp_path):
        """Export a single workflow produces a valid .lmpack."""
        wid = storage.create_workflow(
            name=sample_workflow["name"],
            config=sample_workflow["config"],
        )
        out = tmp_path / "export.lmpack"
        result = package_manager.export_package(str(out), workflow_ids=[wid])

        assert result.success
        assert result.workflows_exported == 1
        assert out.exists()

        with zipfile.ZipFile(out, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert len(manifest["workflows"]) == 1
            assert manifest["workflows"][0]["id"] == wid

    def test_export_strips_secrets(self, storage, package_manager, tmp_path):
        """Export removes secret keys from agent config."""
        aid = storage.create_agent(
            name="Secret Agent",
            system_prompt="Test",
            config={"api_key": "supersecret", "temperature": 0.7},
        )
        out = tmp_path / "export.lmpack"
        result = package_manager.export_package(str(out), agent_ids=[aid])

        assert result.success
        with zipfile.ZipFile(out, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            agent_id = manifest["agents"][0]["id"]
            agent_data = json.loads(zf.read(f"agents/{agent_id}.json"))
            assert "api_key" not in agent_data.get("config", {})
            assert agent_data["config"]["temperature"] == 0.7

    def test_export_nonexistent_agent_fails(self, package_manager, tmp_path):
        """Export with non-existent agent ID returns failure."""
        result = package_manager.export_package(
            str(tmp_path / "out.lmpack"),
            agent_ids=["nonexistent-id"],
        )
        assert not result.success
        assert "not found" in result.message.lower()


# =============================================================================
# Import tests
# =============================================================================

class TestImport:
    """Test package import functionality."""

def _make_package(tmp_path, agents=None, workflows=None):
    """Helper to create a minimal valid .lmpack in tmp_path."""
    agents = agents or []
    workflows = workflows or []
    manifest = {
        "format_version": FORMAT_VERSION,
        "name": "Test Package",
        "package_version": "1.0",
        "created_at": "2026-01-01T00:00:00",
        "description": "Test package",
        "agents": agents,
        "workflows": workflows,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "agents").mkdir()
        (tmppath / "workflows").mkdir()

        for agent in agents:
            with open(tmppath / "agents" / f"{agent['id']}.json", "w") as f:
                json.dump(agent, f)
        for wf in workflows:
            with open(tmppath / "workflows" / f"{wf['id']}.json", "w") as f:
                json.dump(wf, f)

        with open(tmppath / "manifest.json", "w") as f:
            json.dump(manifest, f)

        out = tmp_path / f"package_{len(agents)}a_{len(workflows)}w.lmpack"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(tmppath):
                for file in files:
                    fp = Path(root) / file
                    arcname = str(fp.relative_to(tmppath)).replace("\\", "/")
                    zf.write(fp, arcname)
        return out

    def test_import_valid_package(self, storage, package_manager, tmp_path):
        """Import a valid package imports agents and workflows."""
        agent = {
            "id": "imported-agent-1",
            "name": "Imported Agent",
            "persona": "scientist",
            "system_prompt": "I am imported.",
            "config": {},
            "tools": [],
        }
        wf = {
            "id": "imported-wf-1",
            "name": "Imported Workflow",
            "config": {"mode": "single"},
        }
        pkg = _make_package(tmp_path, agents=[agent], workflows=[wf])

        result = package_manager.import_package(str(pkg))
        assert result.success
        assert result.agents_imported == 1
        assert result.workflows_imported == 1
        assert storage.get_agent("imported-agent-1") is not None
        assert storage.get_workflow("imported-wf-1") is not None

    def test_import_missing_manifest(self, tmp_path):
        """Import a ZIP without manifest.json fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.lmpack"
            with zipfile.ZipFile(bad, "w") as zf:
                zf.writestr("agents/foo.json", "{}")
        pm = PackageManager(StudioStorage())
        result = pm.import_package(str(bad))
        assert not result.success
        assert "manifest" in result.errors[0].lower()

    def test_import_corrupted_zip(self, tmp_path):
        """Import a non-ZIP file fails gracefully."""
        with tempfile.NamedTemporaryFile(suffix=".lmpack", delete=False) as f:
            f.write(b"this is not a zip")
            bad = Path(f.name)
        try:
            pm = PackageManager(StudioStorage())
            result = pm.import_package(str(bad))
            assert not result.success
        finally:
            bad.unlink(missing_ok=True)

    def test_import_invalid_json_in_agent(self, storage, package_manager, tmp_path):
        """Import with invalid agent JSON reports error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "agents").mkdir()
            (tmppath / "agents" / "bad.json").write_text("not json{{")
            manifest = {
                "format_version": FORMAT_VERSION,
                "name": "Bad Package",
                "package_version": "1.0",
                "agents": [{"id": "bad"}],
                "workflows": [],
            }
            with open(tmppath / "manifest.json", "w") as f:
                json.dump(manifest, f)
            bad = tmp_path / "bad.lmpack"
            with zipfile.ZipFile(bad, "w") as zf:
                for root, _, files in os.walk(tmppath):
                    for file in files:
                        fp = Path(root) / file
                        zf.write(fp, str(fp.relative_to(tmppath)))

        result = package_manager.import_package(str(bad))
        assert not result.success
        assert any("JSON" in e for e in result.errors)

    def test_import_duplicate_agents_skipped(self, storage, package_manager, tmp_path):
        """Importing an agent that already exists skips it with a conflict."""
        storage.create_agent(name="Existing", system_prompt="I exist", persona="general")
        agent = {
            "id": "existing-agent-id",  # same ID
            "name": "Existing",
            "persona": "general",
            "system_prompt": "I exist",
            "config": {},
            "tools": [],
        }
        pkg = _make_package(tmp_path, agents=[agent])
        result = package_manager.import_package(str(pkg))
        assert "conflict" in result.message.lower() or result.agents_imported == 0

    def test_import_empty_package_fails(self, storage, package_manager, tmp_path):
        """Import a package with no agents and no workflows fails."""
        pkg = _make_package(tmp_path, agents=[], workflows=[])
        result = package_manager.import_package(str(pkg))
        assert not result.success
        assert "No content imported" in result.message


# =============================================================================
# Round-trip tests
# =============================================================================

class TestRoundTrip:
    """Test export → import round-trip."""

    def test_roundtrip_agent(self, storage, package_manager, tmp_path):
        """Export an agent and re-import it."""
        aid = storage.create_agent(
            name="RoundTrip Agent",
            system_prompt="I go around.",
            persona="researcher",
            config={"temperature": 0.5},
            tools=["search"],
        )
        export_path = tmp_path / "roundtrip.lmpack"
        export_result = package_manager.export_package(str(export_path), agent_ids=[aid])
        assert export_result.success

        # Remove original
        storage.delete_agent(aid)
        assert storage.get_agent(aid) is None

        # Re-import
        import_result = package_manager.import_package(str(export_path))
        assert import_result.success, f"Errors: {import_result.errors}"
        assert import_result.agents_imported == 1
        # Verify by name since IDs are regenerated on import
        agents = storage.list_agents()
        imported = next((a for a in agents if a["name"] == "RoundTrip Agent"), None)
        assert imported is not None

    def test_roundtrip_workflow(self, storage, package_manager, tmp_path):
        """Export a workflow and re-import it."""
        wid = storage.create_workflow(
            name="RoundTrip Workflow",
            config={"mode": "multi", "domain": "science", "num_tasks": 10},
        )
        export_path = tmp_path / "rt_wf.lmpack"
        export_result = package_manager.export_package(str(export_path), workflow_ids=[wid])
        assert export_result.success

        storage.delete_workflow(wid)
        import_result = package_manager.import_package(str(export_path))
        assert import_result.success, f"Errors: {import_result.errors}"
        # Verify by name since IDs are regenerated on import
        workflows = storage.list_workflows()
        imported = next((w for w in workflows if w["name"] == "RoundTrip Workflow"), None)
        assert imported is not None


# =============================================================================
# Security tests
# =============================================================================

class TestSecurity:
    """Test security constraints."""

    def test_zip_slip_rejected(self, tmp_path):
        """Packages with path-traversal arcnames are rejected."""
        pm = PackageManager(StudioStorage())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            manifest = {
                "format_version": FORMAT_VERSION,
                "name": "Malicious",
                "package_version": "1.0",
                "agents": [],
                "workflows": [],
            }
            with open(tmppath / "manifest.json", "w") as f:
                json.dump(manifest, f)
            bad = tmp_path / "evil.lmpack"
            with zipfile.ZipFile(bad, "w") as zf:
                zf.writestr("manifest.json", json.dumps(manifest))
                zf.writestr("../etc/passwd", "hacked")

        result = pm.import_package(str(bad))
        assert not result.success
        assert any("unsafe" in e.lower() or "dangerous" in e.lower() for e in result.errors)

    def test_absolute_path_rejected(self, tmp_path):
        """Absolute paths in ZIP are rejected."""
        pm = PackageManager(StudioStorage())
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            manifest = {
                "format_version": FORMAT_VERSION,
                "name": "Abs",
                "package_version": "1.0",
                "agents": [],
                "workflows": [],
            }
            with open(tmppath / "manifest.json", "w") as f:
                json.dump(manifest, f)
            bad = tmp_path / "abs.lmpack"
            with zipfile.ZipFile(bad, "w") as zf:
                zf.writestr("manifest.json", json.dumps(manifest))
                zf.writestr("/etc/shadow", "hacked")

        result = pm.import_package(str(bad))
        assert not result.success

    def test_package_size_limit(self, tmp_path):
        """Oversized packages are rejected."""
        pm = PackageManager(StudioStorage())
        big = tmp_path / "big.lmpack"
        # Create a package that's actually over 5MB
        large_data = '{"x":"' + "a" * (6 * 1024 * 1024) + '"}'  # ~6MB
        with zipfile.ZipFile(big, "w") as zf:
            manifest = {"format_version": FORMAT_VERSION, "name": "Big", "package_version": "1.0",
                        "agents": [{"id": "a1", "name": "A"}], "workflows": []}
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("agents/a1.json", large_data)

        result = pm.import_package(str(big))
        assert not result.success
        assert any("large" in e.lower() or "limit" in e.lower() for e in result.errors)


# =============================================================================
# Info / metadata tests
# =============================================================================

class TestPackageInfo:
    """Test get_package_info."""

    def test_get_info_valid(self, tmp_path, package_manager):
        """get_package_info reads metadata from a valid package."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            manifest = {
                "format_version": FORMAT_VERSION,
                "name": "Info Test",
                "package_version": "2.0",
                "created_at": "2026-03-15T10:00:00",
                "description": "A test package",
                "agents": [{"id": "a1", "name": "Agent A"}],
                "workflows": [{"id": "w1", "name": "Workflow W"}],
            }
            with open(tmppath / "manifest.json", "w") as f:
                json.dump(manifest, f)
            pkg = tmp_path / "info.lmpack"
            with zipfile.ZipFile(pkg, "w") as zf:
                zf.writestr("manifest.json", json.dumps(manifest))

            info = package_manager.get_package_info(str(pkg))
            assert info is not None
            assert info.name == "Info Test"
            assert info.format_version == FORMAT_VERSION
            assert info.agents_count == 1
            assert info.workflows_count == 1

    def test_get_info_nonexistent(self, package_manager):
        """get_package_info returns None for missing files."""
        assert package_manager.get_package_info("/tmp/does_not_exist.lmpack") is None

    def test_get_info_no_manifest(self, tmp_path, package_manager):
        """get_package_info returns None when manifest is missing."""
        bad = tmp_path / "nomani.lmpack"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("agents/foo.json", "{}")
        assert package_manager.get_package_info(str(bad)) is None

    def test_import_string_agent_ids(self, storage, package_manager, tmp_path):
        """Import a package with string agent IDs (not dicts)."""
        # Create an agent, then delete it so import can succeed
        aid = storage.create_agent(name="Test Agent", system_prompt="Test")
        storage.delete_agent(aid)

        # Create a package with string IDs in manifest
        pkg = tmp_path / "string_ids.lmpack"
        with zipfile.ZipFile(pkg, "w") as zf:
            manifest = {
                "format_version": FORMAT_VERSION,
                "name": "String Test",
                "package_version": "1.0",
                "agents": [aid],  # string ID, not dict
                "workflows": [],
            }
            agent_data = {"id": aid, "name": "Test Agent", "system_prompt": "Test",
                          "persona": "general", "config": {}, "tools": []}
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr(f"agents/{aid}.json", json.dumps(agent_data))
        result = package_manager.import_package(str(pkg))
        assert result.success, f"Errors: {result.errors}"

    def test_import_string_workflow_ids(self, storage, package_manager, tmp_path):
        """Import a package with string workflow IDs (not dicts)."""
        wid = storage.create_workflow(name="Test WF", config={"mode": "single"})
        storage.delete_workflow(wid)

        pkg = tmp_path / "string_wf.lmpack"
        with zipfile.ZipFile(pkg, "w") as zf:
            manifest = {
                "format_version": FORMAT_VERSION,
                "name": "String WF Test",
                "package_version": "1.0",
                "agents": [],
                "workflows": [wid],  # string ID, not dict
            }
            wf_data = {"id": wid, "name": "Test WF", "config": {"mode": "single"}}
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr(f"workflows/{wid}.json", json.dumps(wf_data))
        result = package_manager.import_package(str(pkg))
        assert result.success, f"Errors: {result.errors}"


# =============================================================================
# Integration with app (structure check)
# =============================================================================

class TestAppIntegration:
    """Verify the app wires up the package manager correctly."""

    def test_packages_page_has_import_export_buttons(self):
        """The packages page creates import and export buttons that are enabled."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp
        source = inspect.getsource(LifeMeanStudioApp._create_packages_page)
        assert "Import Package" in source
        assert "Export Package" in source
        # Buttons should NOT be disabled
        assert "setEnabled(False)" not in source or "import_btn.setEnabled(False)" not in source
        assert "export_btn.setEnabled(False)" not in source

    def test_package_manager_initialized(self):
        """The app creates a PackageManager instance."""
        import inspect
        from life_mean_studio.launcher.app import LifeMeanStudioApp
        source = inspect.getsource(LifeMeanStudioApp.__init__)
        assert "PackageManager" in source
