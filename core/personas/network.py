"""PersonaNetwork — Graph-based persona relationship management.

Manages relationships between personas, enabling:
- Connection/disconnection of personas
- Workflow orchestration based on relationships
- Debate session configuration from network topology
- Relationship validation and cycle detection
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .schema import PersonaConfig, PersonaRelationship, RelationshipType

logger = logging.getLogger("core.personas.network")


# ── Network Node ─────────────────────────────────────────────────────────────


@dataclass
class PersonaNode:
    """A node in the persona network."""

    role_id: str
    persona: PersonaConfig
    connections: List[str] = field(default_factory=list)  # connected role_ids
    connection_strengths: Dict[str, float] = field(default_factory=dict)  # role_id -> strength

    @property
    def is_isolated(self) -> bool:
        return len(self.connections) == 0

    @property
    def degree(self) -> int:
        return len(self.connections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "persona": self.persona.to_dict(),
            "connections": list(self.connections),
            "connection_strengths": dict(self.connection_strengths),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaNode":
        persona_data = data.get("persona", {})
        if not persona_data or not persona_data.get("role_id"):
            raise ValueError(f"Invalid persona data in node: {data.get('role_id', 'UNKNOWN')}")

        # Validate required fields before constructing
        role_id = str(persona_data.get("role_id", ""))
        name = str(persona_data.get("name", ""))
        description = str(persona_data.get("description", ""))
        system_prompt = str(persona_data.get("system_prompt", ""))

        if not role_id:
            raise ValueError("Persona role_id is required")
        if not system_prompt or not system_prompt.strip():
            # Allow template placeholders but flag them
            logger.warning("Persona '%s' has empty system_prompt — may be a template", role_id)

        # persona_type: fall back to ANALYTICAL_PHILOSOPHER if missing/invalid
        ptype_val = persona_data.get("persona_type")
        try:
            persona_type = PersonaType(str(ptype_val)) if ptype_val else PersonaType.ANALYTICAL_PHILOSOPHER
        except (ValueError, TypeError):
            persona_type = PersonaType.ANALYTICAL_PHILOSOPHER

        persona = PersonaConfig(
            role_id=role_id,
            name=name,
            persona_type=persona_type,
            description=description,
            system_prompt=system_prompt,
            color=str(persona_data.get("color", "#888888")),
            version=str(persona_data.get("version", "1.0.0")),
            metadata=dict(persona_data.get("metadata", {}) or {}),
            parent_persona_id=persona_data.get("parent_persona_id"),
        )

        return cls(
            role_id=role_id,
            persona=persona,
            connections=list(data.get("connections", []) or []),
            connection_strengths=dict(data.get("connection_strengths", {}) or {}),
        )


# ── PersonaNetwork ───────────────────────────────────────────────────────────


class PersonaNetwork:
    """Graph-based management of persona relationships.

    Enables:
    - Connecting personas with typed relationships
    - Detecting cycles and validating topology
    - Generating debate workflows from network structure
    - Exporting/importing network configurations
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, PersonaNode] = {}
        self._relationships: List[PersonaRelationship] = []

    # ── Node Management ────────────────────────────────────────────────────

    def add_persona(self, persona: PersonaConfig) -> None:
        """Add a persona to the network."""
        self._nodes[persona.role_id] = PersonaNode(
            role_id=persona.role_id,
            persona=persona,
        )
        logger.info("Added persona '%s' to network", persona.role_id)

    def remove_persona(self, role_id: str) -> bool:
        """Remove a persona and all its connections."""
        if role_id not in self._nodes:
            return False

        # Remove all relationships involving this persona
        self._relationships = [
            r for r in self._relationships
            if r.source_id != role_id and r.target_id != role_id
        ]

        # Remove from all connection lists
        for node in self._nodes.values():
            if role_id in node.connections:
                node.connections.remove(role_id)
                node.connection_strengths.pop(role_id, None)

        del self._nodes[role_id]
        logger.info("Removed persona '%s' from network", role_id)
        return True

    def get_node(self, role_id: str) -> Optional[PersonaNode]:
        """Get a node by role_id."""
        return self._nodes.get(role_id)

    def list_nodes(self) -> List[PersonaNode]:
        """List all nodes in the network."""
        return list(self._nodes.values())

    # ── Relationship Management ────────────────────────────────────────────

    def connect(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType,
        strength: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a relationship between two personas."""
        if source_id not in self._nodes:
            logger.warning("Source persona '%s' not found", source_id)
            return False
        if target_id not in self._nodes:
            logger.warning("Target persona '%s' not found", target_id)
            return False
        if source_id == target_id:
            logger.warning("Cannot connect persona to itself")
            return False

        # Check for existing relationship
        existing = self._find_relationship(source_id, target_id)
        if existing:
            # Update existing relationship
            existing.relationship_type = relationship_type
            existing.strength = strength
            if metadata:
                existing.metadata.update(metadata)
            logger.info("Updated relationship %s -%s-> %s", source_id, relationship_type.value, target_id)
            return True

        # Create new relationship
        rel = PersonaRelationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            strength=strength,
            metadata=metadata or {},
        )
        self._relationships.append(rel)

        # Update node connections
        self._nodes[source_id].connections.append(target_id)
        self._nodes[source_id].connection_strengths[target_id] = strength
        self._nodes[target_id].connections.append(source_id)
        self._nodes[target_id].connection_strengths[source_id] = strength

        logger.info("Connected %s -%s-> %s (strength=%.2f)", source_id, relationship_type.value, target_id, strength)
        return True

    def disconnect(self, source_id: str, target_id: str) -> bool:
        """Remove a relationship between two personas."""
        rel = self._find_relationship(source_id, target_id)
        if not rel:
            return False

        self._relationships.remove(rel)

        # Update node connections
        if target_id in self._nodes[source_id].connections:
            self._nodes[source_id].connections.remove(target_id)
            self._nodes[source_id].connection_strengths.pop(target_id, None)
        if source_id in self._nodes[target_id].connections:
            self._nodes[target_id].connections.remove(source_id)
            self._nodes[target_id].connection_strengths.pop(source_id, None)

        logger.info("Disconnected %s - %s", source_id, target_id)
        return True

    def _find_relationship(self, source_id: str, target_id: str) -> Optional[PersonaRelationship]:
        """Find a relationship between two personas."""
        for rel in self._relationships:
            if rel.source_id == source_id and rel.target_id == target_id:
                return rel
        return None

    def get_relationships(self, role_id: Optional[str] = None) -> List[PersonaRelationship]:
        """Get relationships, optionally filtered by role_id."""
        if role_id is None:
            return list(self._relationships)
        return [r for r in self._relationships if r.source_id == role_id or r.target_id == role_id]

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(self) -> Dict[str, Any]:
        """Validate the network topology."""
        errors: List[str] = []
        warnings: List[str] = []

        # Check for isolated personas (except when intentional)
        isolated = [n.role_id for n in self._nodes.values() if n.is_isolated]
        if isolated and len(self._nodes) > 1:
            warnings.append(f"Isolated personas: {', '.join(isolated)}")

        # Check for cycles in directed relationships
        cycles = self._detect_cycles()
        if cycles:
            errors.append(f"Cyclic relationships detected: {cycles}")

        # Check relationship types are valid
        for rel in self._relationships:
            if rel.strength < 0.0 or rel.strength > 1.0:
                errors.append(f"Invalid strength {rel.strength} for {rel.source_id}-{rel.relationship_type.value}-{rel.target_id}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "node_count": len(self._nodes),
            "relationship_count": len(self._relationships),
        }

    def _detect_cycles(self) -> List[List[str]]:
        """Detect cycles in the directed relationship graph."""
        cycles = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for rel in self._relationships:
                if rel.source_id == node_id:
                    target = rel.target_id
                    if target not in visited:
                        dfs(target)
                    elif target in rec_stack:
                        # Found a cycle
                        cycle_start = path.index(target)
                        cycles.append(path[cycle_start:] + [target])

            path.pop()
            rec_stack.remove(node_id)

        for node_id in self._nodes:
            if node_id not in visited:
                dfs(node_id)

        return cycles

    # ── Workflow Generation ────────────────────────────────────────────────

    def generate_workflow(self, start_role_id: Optional[str] = None) -> List[str]:
        """Generate an execution workflow from the canonical relationship graph.

        The workflow is DERIVED from relationships, not stored separately.
        Uses topological sort for DAGs, or depth-first for connected components.
        """
        if not self._nodes:
            return []

        # If a start node is specified, do DFS from there
        if start_role_id and start_role_id in self._nodes:
            return self._dfs_workflow(start_role_id)

        # Otherwise, find root nodes (no incoming relationships)
        roots = self._find_root_nodes()
        if roots:
            workflow = []
            for root in roots:
                workflow.extend(self._dfs_workflow(root))
            return workflow

        # If no roots (all cycles), do DFS from first node
        first_node = next(iter(self._nodes))
        return self._dfs_workflow(first_node)

    def _dfs_workflow(self, start_id: str) -> List[str]:
        """Generate workflow via depth-first search from relationship graph."""
        visited: Set[str] = set()
        workflow: List[str] = []

        def dfs(node_id: str) -> None:
            if node_id in visited:
                return
            visited.add(node_id)
            workflow.append(node_id)

            # Visit neighbors sorted by connection strength (strongest first)
            neighbors = sorted(
                self._nodes[node_id].connections,
                key=lambda n: self._nodes[node_id].connection_strengths.get(n, 0.0),
                reverse=True,
            )
            for neighbor in neighbors:
                dfs(neighbor)

        dfs(start_id)
        return workflow

    def _find_root_nodes(self) -> List[str]:
        """Find nodes with no incoming relationships."""
        has_incoming: Set[str] = set()
        for rel in self._relationships:
            has_incoming.add(rel.target_id)

        roots = [n.role_id for n in self._nodes.values() if n.role_id not in has_incoming]
        return sorted(roots)

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the network to a dictionary."""
        return {
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "relationships": [rel.to_dict() for rel in self._relationships],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaNetwork":
        """Create a network from a dictionary."""
        network = cls()

        # Add nodes
        for node_data in data.get("nodes", []):
            persona = PersonaConfig.from_dict(node_data.get("persona", {}))
            network.add_persona(persona)

        # Add relationships
        for rel_data in data.get("relationships", []):
            rel = PersonaRelationship.from_dict(rel_data)
            if rel.source_id in network._nodes and rel.target_id in network._nodes:
                network._relationships.append(rel)
                # Update connections
                network._nodes[rel.source_id].connections.append(rel.target_id)
                network._nodes[rel.source_id].connection_strengths[rel.target_id] = rel.strength
                network._nodes[rel.target_id].connections.append(rel.source_id)
                network._nodes[rel.target_id].connection_strengths[rel.source_id] = rel.strength

        return network

    def export_json(self, path: str) -> None:
        """Export the network to a JSON file atomically."""
        import json
        import os
        import shutil
        p = Path(path)
        tmp = p.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(str(tmp), str(p))
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
        logger.info("Exported network to %s", path)

    @classmethod
    def import_json(cls, path: str) -> "PersonaNetwork":
        """Import a network from a JSON file."""
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
