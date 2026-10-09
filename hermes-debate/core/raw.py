"""
RAW (Research Archive Workspace) module.

Manages immutable raw data artifacts from experiments.
RAW is the source of truth and must never be modified after creation.
"""

import json
from datetime import datetime
from typing import Any, Optional
from pathlib import Path


class RAWArtifact:
    """
    Immutable artifact representing raw experimental data.
    
    Contains all execution details, events, metrics, and provenance.
    """
    
    def __init__(
        self,
        run_id: str,
        experiment_id: str,
        data: dict[str, Any],
        metadata: Optional[dict] = None,
    ):
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.data = data
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'run_id': self.run_id,
            'experiment_id': self.experiment_id,
            'data': self.data,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
        }
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class RAWArchive:
    """
    Archive for storing and managing RAW artifacts.
    
    Provides immutable storage with provenance tracking.
    """
    
    def __init__(self, storage_path: str = "./raw"):
        self.storage_path = Path(storage_path)
        self._artifacts: dict[str, RAWArtifact] = {}
        
        # Create storage directory if needed
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def store(self, artifact: RAWArtifact) -> str:
        """
        Store a RAW artifact.
        
        Args:
            artifact: The artifact to store
            
        Returns:
            Artifact ID
        """
        artifact_id = f"RAW_{artifact.run_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self._artifacts[artifact_id] = artifact
        
        # Save to disk (immutable)
        self._save_to_disk(artifact_id, artifact)
        
        return artifact_id
    
    def get(self, artifact_id: str) -> Optional[RAWArtifact]:
        """Get a RAW artifact by ID."""
        return self._artifacts.get(artifact_id)
    
    def list_artifacts(self, experiment_id: Optional[str] = None) -> list[RAWArtifact]:
        """List artifacts, optionally filtered by experiment."""
        if experiment_id:
            return [a for a in self._artifacts.values() if a.experiment_id == experiment_id]
        return list(self._artifacts.values())
    
    def _save_to_disk(self, artifact_id: str, artifact: RAWArtifact) -> None:
        """Save artifact to disk as immutable JSON."""
        file_path = self.storage_path / f"{artifact_id}.json"
        
        # Only save if not exists (immutable)
        if not file_path.exists():
            with open(file_path, 'w') as f:
                json.dump(artifact.to_dict(), f, indent=2)
    
    def load_from_disk(self, artifact_id: str) -> Optional[RAWArtifact]:
        """Load an artifact from disk."""
        file_path = self.storage_path / f"{artifact_id}.json"
        
        if not file_path.exists():
            return None
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        return RAWArtifact(
            run_id=data['run_id'],
            experiment_id=data['experiment_id'],
            data=data['data'],
            metadata=data.get('metadata', {}),
        )


class ProvenanceTracker:
    """
    Tracks provenance of experimental results.
    
    Creates a complete chain from Study to Run to Assignment Event.
    """
    
    def __init__(self):
        self._chain: list[dict] = []
    
    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Add an event to the provenance chain.
        
        Args:
            event_type: Type of event (study, experiment, run, phase, assignment, etc.)
            data: Event data
        """
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.utcnow().isoformat(),
        }
        self._chain.append(event)
    
    def get_chain(self) -> list[dict]:
        """Get the complete provenance chain."""
        return self._chain.copy()
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'provenance_chain': self._chain,
            'created_at': datetime.utcnow().isoformat(),
        }
