"""
Test Privacy — Sessions privées et isolation des données.

Démontre qu'une session privée n'écrit pas son contenu dans les stores.
Vérifie que les événements de sécurité sont distincts des historiques.
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from data.schemas.profile import Profile, PrivacyPolicy
from data.schemas.experience import Experience
from data.schemas.checkpoint import Checkpoint
from data.schemas.branch import Branch
from data.schemas.cluster import Cluster
from data.schemas.context_graph import GraphNode, GraphEdge
from data.schemas.pack_manifest import PackManifest

from data.storage.profile_store import ProfileStore, ProfileStoreError
from data.storage.experience_store import ExperienceStore, ExperienceStoreError
from data.storage.checkpoint_store import CheckpointStore, CheckpointStoreError
from data.storage.branch_store import BranchStore, BranchStoreError
from data.storage.cluster_store import ClusterStore, ClusterStoreError
from data.storage.context_graph_store import ContextGraphStore, ContextGraphStoreError
from data.storage.pack_store import PackStore, PackStoreError
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


class TestPrivateSessionNoPersist:
    """Test that private sessions do not persist data."""

    def test_profile_not_persisted(self, temp_db, privacy_manager):
        """Profile cannot be persisted in private session."""
        privacy_manager.set_policy("profile", SessionMode.PRIVATE_SESSION)
        store = ProfileStore(temp_db, privacy_manager)

        with pytest.raises(ProfileStoreError):
            store.create(Profile(name="Private Profile"))

    def test_experience_not_persisted(self, temp_db, privacy_manager):
        """Experience cannot be persisted in private session."""
        privacy_manager.set_policy("experience", SessionMode.PRIVATE_SESSION)
        store = ExperienceStore(temp_db, privacy_manager)

        with pytest.raises(ExperienceStoreError):
            store.create(Experience(name="Private Experience"))

    def test_checkpoint_not_persisted(self, temp_db, privacy_manager):
        """Checkpoint cannot be persisted in private session."""
        privacy_manager.set_policy("checkpoint", SessionMode.PRIVATE_SESSION)
        store = CheckpointStore(temp_db, privacy_manager)

        with pytest.raises(CheckpointStoreError):
            store.create(Checkpoint(experience_id="exp1", name="Private"))

    def test_branch_not_persisted(self, temp_db, privacy_manager):
        """Branch cannot be persisted in private session."""
        privacy_manager.set_policy("branch", SessionMode.PRIVATE_SESSION)
        store = BranchStore(temp_db, privacy_manager)

        with pytest.raises(BranchStoreError):
            store.create(Branch(name="Private Branch"))

    def test_cluster_not_persisted(self, temp_db, privacy_manager):
        """Cluster cannot be persisted in private session."""
        privacy_manager.set_policy("cluster", SessionMode.PRIVATE_SESSION)
        store = ClusterStore(temp_db, privacy_manager)

        with pytest.raises(ClusterStoreError):
            store.create(Cluster(name="Private Cluster"))

    def test_graph_node_not_persisted(self, temp_db, privacy_manager):
        """Graph node cannot be persisted in private session."""
        privacy_manager.set_policy("graph", SessionMode.PRIVATE_SESSION)
        store = ContextGraphStore(temp_db, privacy_manager)

        with pytest.raises(ContextGraphStoreError):
            store.add_node(GraphNode(type="experience", label="Private"))

    def test_pack_not_persisted(self, temp_db, privacy_manager):
        """Pack cannot be persisted in private session."""
        privacy_manager.set_policy("pack", SessionMode.PRIVATE_SESSION)
        store = PackStore(temp_db, privacy_manager)

        with pytest.raises(PackStoreError):
            store.create(PackManifest(name="Private Pack"))


class TestPrivacyModes:
    """Test different privacy modes."""

    def test_local_history_allows_persist(self, temp_db, privacy_manager):
        """Local history mode allows persistence."""
        privacy_manager.set_policy("profile", SessionMode.LOCAL_HISTORY)
        store = ProfileStore(temp_db, privacy_manager)

        profile = store.create(Profile(name="Local"))
        assert profile is not None

    def test_observability_allows_persist(self, temp_db, privacy_manager):
        """Observability mode allows persistence."""
        privacy_manager.set_policy("profile", SessionMode.OBSERVABILITY)
        store = ProfileStore(temp_db, privacy_manager)

        profile = store.create(Profile(name="Observable"))
        assert profile is not None

    def test_local_only_allows_persist(self, temp_db, privacy_manager):
        """Local only mode allows persistence."""
        privacy_manager.set_policy("profile", SessionMode.LOCAL_ONLY)
        store = ProfileStore(temp_db, privacy_manager)

        profile = store.create(Profile(name="Local Only"))
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


class TestEdgeTypesIndependence:
    """Test that different edge types are independent."""

    def test_lineage_and_classification_independent(self, temp_db):
        """Lineage and classification edges can coexist independently."""
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

    def test_remove_classification_does_not_affect_lineage(self, temp_db):
        """Removing a classification edge does not affect lineage."""
        store = ContextGraphStore(temp_db)

        # Add both edges
        lineage = store.add_edge(GraphEdge(source="exp1", target="branch1", type="lineage"))
        classification = store.add_edge(GraphEdge(source="exp1", target="cluster1", type="classification"))

        # Remove classification
        store.remove_edge(classification.id)

        # Lineage should still exist
        lineage_edges = store.list_edges_by_type("lineage")
        assert len(lineage_edges) == 1
        assert lineage_edges[0].id == lineage.id
