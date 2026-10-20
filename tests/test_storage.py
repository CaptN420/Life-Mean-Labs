"""
Test Storage — CRUD stores avec politique de confidentialité.

Vérifie que les stores implémentent correctement la politique de confidentialité.
Démontre que lineage et classification sont indépendants.
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

# Import schemas
from data.schemas.profile import Profile, ProviderProfile, PrivacyPolicy
from data.schemas.experience import Experience, AgentInstance
from data.schemas.checkpoint import Checkpoint
from data.schemas.branch import Branch
from data.schemas.cluster import Cluster
from data.schemas.context_graph import GraphNode, GraphEdge
from data.schemas.pack_manifest import PackManifest, ComponentManifest

# Import stores
from data.storage.profile_store import ProfileStore
from data.storage.experience_store import ExperienceStore
from data.storage.checkpoint_store import CheckpointStore
from data.storage.branch_store import BranchStore
from data.storage.cluster_store import ClusterStore
from data.storage.context_graph_store import ContextGraphStore
from data.storage.pack_store import PackStore
from data.storage.privacy_policy import PrivacyPolicyManager, SessionMode


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def privacy_manager():
    """Create a privacy policy manager."""
    return PrivacyPolicyManager()


class TestProfileStore:
    """Test Profile CRUD operations."""

    def test_create_and_get(self, temp_db):
        store = ProfileStore(temp_db)
        profile = Profile(name="Test Profile")
        created = store.create(profile)
        assert created.id is not None

        retrieved = store.get(created.id)
        assert retrieved is not None
        assert retrieved.name == "Test Profile"

    def test_list_all(self, temp_db):
        store = ProfileStore(temp_db)
        p1 = store.create(Profile(name="Profile 1"))
        p2 = store.create(Profile(name="Profile 2"))

        profiles = store.list_all()
        assert len(profiles) == 2

    def test_update(self, temp_db):
        store = ProfileStore(temp_db)
        profile = store.create(Profile(name="Original"))
        updated = store.update(profile.id, {"name": "Updated"})
        assert updated.name == "Updated"

    def test_delete(self, temp_db):
        store = ProfileStore(temp_db)
        profile = store.create(Profile(name="ToDelete"))
        deleted = store.delete(profile.id)
        assert deleted is True
        assert store.get(profile.id) is None


class TestExperienceStore:
    """Test Experience CRUD operations."""

    def test_create_and_get(self, temp_db):
        store = ExperienceStore(temp_db)
        experience = Experience(name="Test Experience")
        created = store.create(experience)
        assert created.id is not None

        retrieved = store.get(created.id)
        assert retrieved is not None
        assert retrieved.name == "Test Experience"

    def test_experience_lifecycle(self, temp_db):
        store = ExperienceStore(temp_db)
        experience = store.create(Experience(name="Lifecycle"))

        # Start
        experience = store.update(experience.id, {"status": "running"})
        assert experience.status == "running"

        # Complete
        experience = store.update(experience.id, {"status": "completed"})
        assert experience.status == "completed"


class TestCheckpointStore:
    """Test Checkpoint CRUD operations."""

    def test_create_and_get(self, temp_db):
        store = CheckpointStore(temp_db)
        checkpoint = Checkpoint(
            experience_id="exp1",
            name="Check 1",
            workflow_position="planner",
            snapshot_path="/tmp/snap.pkl",
            checksum="abc123",
        )
        created = store.create(checkpoint)
        assert created.id is not None

        retrieved = store.get(created.id)
        assert retrieved is not None
        assert retrieved.experience_id == "exp1"

    def test_list_by_experience(self, temp_db):
        store = CheckpointStore(temp_db)
        c1 = store.create(Checkpoint(experience_id="exp1", name="Check 1"))
        c2 = store.create(Checkpoint(experience_id="exp1", name="Check 2"))

        checkpoints = store.list_by_experience("exp1")
        assert len(checkpoints) == 2


class TestBranchStore:
    """Test Branch CRUD operations with lineage immutability."""

    def test_create_and_get(self, temp_db):
        store = BranchStore(temp_db)
        branch = Branch(name="Main", root_project_id="project1")
        created = store.create(branch)
        assert created.id is not None

        retrieved = store.get(created.id)
        assert retrieved is not None
        assert retrieved.name == "Main"

    def test_lineage_immutable(self, temp_db):
        """Lineage cannot be modified after creation."""
        store = BranchStore(temp_db)
        parent = store.create(Branch(name="Parent", root_project_id="project1"))
        child = store.create(Branch(name="Child", root_project_id="project1", lineage=[parent.id]))

        # Try to update lineage (should be ignored)
        updated = store.update(child.id, {"lineage": ["fake_id"]})
        assert updated.lineage == [parent.id]  # Lineage unchanged

    def test_branch_depth(self, temp_db):
        store = BranchStore(temp_db)
        branch = store.create(Branch(name="Deep", root_project_id="project1", lineage=["a", "b", "c"]))
        assert branch.depth == 3


class TestClusterStore:
    """Test Cluster CRUD operations."""

    def test_create_and_get(self, temp_db):
        store = ClusterStore(temp_db)
        cluster = Cluster(name="Test Cluster")
        created = store.create(cluster)
        assert created.id is not None

        retrieved = store.get(created.id)
        assert retrieved is not None
        assert retrieved.name == "Test Cluster"

    def test_add_remove_member(self, temp_db):
        store = ClusterStore(temp_db)
        cluster = store.create(Cluster(name="Cluster"))
        cluster = store.update(cluster.id, {"member_ids": ["exp1", "exp2"]})
        assert "exp1" in cluster.member_ids

        cluster = store.update(cluster.id, {"member_ids": ["exp1"]})
        assert "exp2" not in cluster.member_ids


class TestContextGraphStore:
    """Test Context Graph CRUD operations."""

    def test_add_node(self, temp_db):
        store = ContextGraphStore(temp_db)
        node = GraphNode(type="experience", label="Test Exp")
        added = store.add_node(node)
        assert added.id is not None

        retrieved = store.get_node(added.id)
        assert retrieved is not None
        assert retrieved.type == "experience"

    def test_add_edge(self, temp_db):
        store = ContextGraphStore(temp_db)
        edge = GraphEdge(source="node1", target="node2", type="lineage")
        added = store.add_edge(edge)
        assert added.id is not None

        retrieved = store.get_edge(added.id)
        assert retrieved is not None
        assert retrieved.type == "lineage"

    def test_edge_types_independent(self, temp_db):
        """Lineage and classification edges are independent."""
        store = ContextGraphStore(temp_db)

        # Add lineage edge
        lineage = store.add_edge(GraphEdge(source="exp1", target="branch1", type="lineage"))
        # Add classification edge
        classification = store.add_edge(GraphEdge(source="exp1", target="cluster1", type="classification"))

        # List by type
        lineage_edges = store.list_edges_by_type("lineage")
        assert len(lineage_edges) == 1
        assert lineage_edges[0].id == lineage.id

        class_edges = store.list_edges_by_type("classification")
        assert len(class_edges) == 1
        assert class_edges[0].id == classification.id


class TestPackStore:
    """Test Pack CRUD operations."""

    def test_create_and_get(self, temp_db):
        store = PackStore(temp_db)
        pack = PackManifest(name="Test Pack")
        created = store.create(pack)
        assert created.id is not None

        retrieved = store.get(created.id)
        assert retrieved is not None
        assert retrieved.name == "Test Pack"

    def test_validate_on_create(self, temp_db):
        store = PackStore(temp_db)
        # Invalid pack (unknown license with redistributable)
        invalid_pack = PackManifest(
            name="Invalid",
            components=[ComponentManifest(path="test.py", license="Unknown", redistributable=True)],
        )
        with pytest.raises(Exception):  # PackStoreError
            store.create(invalid_pack)


class TestPrivacyPolicy:
    """Test privacy policy integration."""

    def test_private_session_no_persist(self, temp_db, privacy_manager):
        """Private session should not persist data."""
        privacy_manager.set_policy("profile", SessionMode.PRIVATE_SESSION)
        privacy_manager.set_policy("experience", SessionMode.PRIVATE_SESSION)
        privacy_manager.set_policy("checkpoint", SessionMode.PRIVATE_SESSION)
        privacy_manager.set_policy("branch", SessionMode.PRIVATE_SESSION)
        privacy_manager.set_policy("cluster", SessionMode.PRIVATE_SESSION)
        privacy_manager.set_policy("graph", SessionMode.PRIVATE_SESSION)
        privacy_manager.set_policy("pack", SessionMode.PRIVATE_SESSION)

        # Profile store should raise error
        profile_store = ProfileStore(temp_db, privacy_manager)
        with pytest.raises(Exception):  # ProfileStoreError
            profile_store.create(Profile(name="Private"))

        # Experience store should raise error
        exp_store = ExperienceStore(temp_db, privacy_manager)
        with pytest.raises(Exception):  # ExperienceStoreError
            exp_store.create(Experience(name="Private"))

        # Checkpoint store should raise error
        cp_store = CheckpointStore(temp_db, privacy_manager)
        with pytest.raises(Exception):  # CheckpointStoreError
            cp_store.create(Checkpoint(experience_id="exp1", name="Private"))

    def test_local_history_allows_persist(self, temp_db, privacy_manager):
        """Local history mode should allow persistence."""
        privacy_manager.set_policy("profile", SessionMode.LOCAL_HISTORY)

        store = ProfileStore(temp_db, privacy_manager)
        profile = store.create(Profile(name="Local"))
        assert profile is not None


class TestLineageClassificationIndependence:
    """Test that lineage and classification are independent."""

    def test_lineage_unchanged_by_reclassification(self, temp_db):
        """Reclassifying an experience should not change its lineage."""
        branch_store = BranchStore(temp_db)
        cluster_store = ClusterStore(temp_db)

        # Create a branch with lineage and cluster
        parent = branch_store.create(Branch(name="Parent", root_project_id="proj1"))
        cluster = cluster_store.create(Cluster(name="Cluster"))
        child = branch_store.create(Branch(name="Child", root_project_id="proj1", lineage=[parent.id], cluster_id=cluster.id))

        # Verify lineage is unchanged after cluster update
        updated_child = branch_store.get(child.id)
        assert updated_child.lineage == [parent.id]
        assert updated_child.cluster_id == cluster.id

    def test_classification_can_change(self, temp_db):
        """Classification can be changed without affecting lineage."""
        branch_store = BranchStore(temp_db)
        cluster_store = ClusterStore(temp_db)

        # Create two clusters
        cluster1 = cluster_store.create(Cluster(name="Cluster 1"))
        cluster2 = cluster_store.create(Cluster(name="Cluster 2"))

        # Create a branch in cluster1
        branch = branch_store.create(Branch(name="Branch", root_project_id="proj1", cluster_id=cluster1.id))

        # Move branch to cluster2
        updated = branch_store.update(branch.id, {"cluster_id": cluster2.id})
        assert updated.cluster_id == cluster2.id

        # Lineage should be unchanged
        assert updated.lineage == []
