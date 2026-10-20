"""
Test Schemas — Validation des dataclasses Python.

Vérifie que les schémas sont valides et cohérents.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path

# Import schemas
from data.schemas.profile import Profile, ProviderProfile, ResourceBudget, PrivacyPolicy
from data.schemas.experience import Experience, AgentInstance, ExperienceResult
from data.schemas.checkpoint import Checkpoint, NodeState, ContextReference
from data.schemas.branch import Branch
from data.schemas.cluster import Cluster
from data.schemas.context_graph import ContextGraph, GraphNode, GraphEdge
from data.schemas.pack_manifest import (
    PackManifest,
    CreatorMetadata,
    ProvenanceChain,
    ComponentManifest,
    AssetReference,
)


class TestProfileSchema:
    """Test Profile schema."""

    def test_create_profile(self):
        profile = Profile(name="Test Profile")
        assert profile.name == "Test Profile"
        assert profile.id is not None
        assert isinstance(profile.created_at, datetime)

    def test_profile_with_providers(self):
        provider = ProviderProfile(
            agent_id="agent1",
            provider="lm_studio",
            model_id="test-model",
            api_endpoint="http://localhost:1234/v1",
        )
        profile = Profile(name="Test", providers=[provider])
        assert len(profile.providers) == 1
        assert profile.providers[0].agent_id == "agent1"

    def test_profile_with_budget(self):
        budget = ResourceBudget(vram_target_mb=8192, context_max_tokens=16384)
        profile = Profile(name="Test", budgets={"agent1": budget})
        assert profile.budgets["agent1"].vram_target_mb == 8192

    def test_profile_privacy_modes(self):
        # Test private_session mode
        privacy = PrivacyPolicy(mode="private_session")
        assert not privacy.persists_raw
        assert not privacy.persists_checkpoints
        assert not privacy.allows_cloud

        # Test local_history mode
        privacy = PrivacyPolicy(mode="local_history")
        assert privacy.persists_raw
        assert privacy.persists_checkpoints
        assert not privacy.allows_cloud

        # Test observability mode (cloud_allowed=False by default)
        privacy = PrivacyPolicy(mode="observability")
        assert privacy.persists_raw
        assert privacy.persists_checkpoints
        assert not privacy.allows_cloud  # requires full_observatory

        # Test full_observatory mode with cloud
        privacy = PrivacyPolicy(mode="full_observatory", cloud_allowed=True)
        assert privacy.persists_raw
        assert privacy.persists_checkpoints
        assert privacy.allows_cloud


class TestExperienceSchema:
    """Test Experience schema."""

    def test_create_experience(self):
        experience = Experience(name="Test Experience")
        assert experience.name == "Test Experience"
        assert experience.status == "prepared"

    def test_experience_lifecycle(self):
        experience = Experience(name="Test")
        assert experience.status == "prepared"

        experience = experience.start()
        assert experience.status == "running"
        assert experience.started_at is not None

        experience = experience.complete(success=True)
        assert experience.status == "completed"
        assert experience.completed_at is not None

    def test_experience_with_agents(self):
        agent = AgentInstance(
            agent_id="agent1",
            persona_id="aristotle",
            role_id="developer",
            provider_profile_id="provider1",
        )
        experience = Experience(name="Test", agents=[agent])
        assert len(experience.agents) == 1
        assert experience.agents[0].persona_id == "aristotle"


class TestCheckpointSchema:
    """Test Checkpoint schema."""

    def test_create_checkpoint(self):
        checkpoint = Checkpoint(
            experience_id="exp1",
            name="Check 1",
            workflow_position="planner",
            snapshot_path="/tmp/snapshot.pkl",
            checksum="abc123",
        )
        assert checkpoint.is_valid

    def test_invalid_checkpoint(self):
        checkpoint = Checkpoint(experience_id="exp1", name="Check")
        # Missing snapshot_path and checksum
        assert not checkpoint.is_valid


class TestBranchSchema:
    """Test Branch schema."""

    def test_create_branch(self):
        branch = Branch(name="Main Branch", root_project_id="project1")
        assert branch.depth == 0
        assert branch.lineage == []

    def test_branch_lineage_immutable(self):
        branch = Branch(name="Branch", root_project_id="project1")
        new_branch = branch.add_to_lineage("parent1")
        assert new_branch.lineage == ["parent1"]
        assert branch.lineage == []  # Original unchanged (frozen)
        assert new_branch.depth == 1


class TestClusterSchema:
    """Test Cluster schema."""

    def test_create_cluster(self):
        cluster = Cluster(name="Test Cluster")
        assert cluster.member_ids == []

    def test_cluster_add_member(self):
        cluster = Cluster(name="Test")
        cluster = cluster.add_member("exp1")
        assert "exp1" in cluster.member_ids

    def test_cluster_remove_member(self):
        cluster = Cluster(name="Test", member_ids=["exp1", "exp2"])
        cluster = cluster.remove_member("exp1")
        assert "exp1" not in cluster.member_ids
        assert "exp2" in cluster.member_ids


class TestContextGraphSchema:
    """Test Context Graph schema."""

    def test_add_node(self):
        graph = ContextGraph()
        node = GraphNode(type="experience", label="Test Exp")
        graph = graph.add_node(node)
        assert node.id in graph.nodes

    def test_add_edge(self):
        graph = ContextGraph()
        edge = GraphEdge(source="node1", target="node2", type="lineage")
        graph = graph.add_edge(edge)
        assert edge.id in graph.edges

    def test_edge_types(self):
        lineage = GraphEdge(type="lineage")
        classification = GraphEdge(type="classification")
        dependency = GraphEdge(type="dependency")
        provenance = GraphEdge(type="provenance")

        assert lineage.is_lineage
        assert not lineage.is_classification
        assert not lineage.is_provenance

        assert classification.is_classification
        assert not classification.is_lineage

        assert provenance.is_provenance


class TestPackManifestSchema:
    """Test Pack Manifest schema."""

    def test_create_pack(self):
        pack = PackManifest(name="Test Pack")
        assert pack.name == "Test Pack"
        assert not pack.is_public
        assert not pack.has_provenance

    def test_pack_with_creator(self):
        creator = CreatorMetadata(
            id="creator1",
            display_name="testuser",
            visibility="public",
        )
        pack = PackManifest(name="Test", creator=creator)
        assert pack.is_public

    def test_pack_provenance(self):
        provenance = ProvenanceChain(
            original_pack_id="original1",
            derived_from="derived1",
            license="MIT",
            attribution="Créé par @test, adapté par @user",
        )
        pack = PackManifest(name="Test", provenance=provenance)
        assert pack.has_provenance

    def test_component_from_path(self):
        comp = ComponentManifest.from_file_path("persona.txt")
        assert comp.type == "persona"
        assert comp.license == "MIT"
        assert comp.redistributable is True

        comp = ComponentManifest.from_file_path("model.fbx")
        assert comp.type == "asset"
        assert comp.license == "Unknown"
        assert comp.redistributable is False

    def test_pack_validation(self):
        # Valid pack
        pack = PackManifest(name="Valid Pack")
        errors = pack.validate()
        assert errors == []

        # Invalid pack - unknown license with redistributable
        pack = PackManifest(
            name="Invalid Pack",
            components=[ComponentManifest(path="test.py", license="Unknown", redistributable=True)],
        )
        errors = pack.validate()
        assert len(errors) > 0

    def test_pack_redistribution(self):
        pack = PackManifest(
            name="Test Pack",
            components=[
                ComponentManifest(path="code.py", license="MIT", redistributable=True),
                ComponentManifest(path="asset.png", license="Unknown", redistributable=False),
            ],
        )
        redist = pack.get_redistributable_components()
        assert len(redist) == 1
        assert redist[0].path == "code.py"
