"""LLMPackager — Create and manage .lmpack persona packages.

A .lmpack file is a zip archive containing:
- manifest.json: Pack metadata (name, version, creator, license)
- personas/: Persona configurations (JSON files)
- providers/: Provider configurations (JSON files)
- models/: Model specifications (JSON files)
- network/: Network topology (network.json)
- sessions/: Example debate sessions (JSON files)
- README.md: Human-readable documentation

Usage:
    packager = LLMPackager("my_pack")
    packager.add_persona(persona_config)
    packager.add_provider(provider_config)
    packager.add_model(model_spec)
    packager.create_package(output_path="/path/to/output.lmpack")
"""
from __future__ import annotations

import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..personas.schema import ModelSpec, PersonaConfig, ProviderType
from ..personas.network import PersonaNetwork

logger = logging.getLogger("core.packager")


# ── Pack Manifest ────────────────────────────────────────────────────────────


@dataclass
class PackManifest:
    """Metadata for an .lmpack package."""

    id: str = field(default_factory=lambda: uuid4().hex[:8])
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    license: str = "MIT"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Tags for discovery
    tags: List[str] = field(default_factory=list)

    # Compatibility
    compatible_with: List[str] = field(default_factory=list)  # Life_mean versions

    # Dependencies
    required_providers: List[str] = field(default_factory=list)  # provider IDs
    required_models: List[str] = field(default_factory=list)      # model IDs

    @property
    def is_complete(self) -> bool:
        """Check if manifest has required fields."""
        return bool(self.name.strip())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": list(self.tags),
            "compatible_with": list(self.compatible_with),
            "required_providers": list(self.required_providers),
            "required_models": list(self.required_models),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PackManifest":
        created = data.get("created_at", datetime.now(timezone.utc).isoformat())
        updated = data.get("updated_at", datetime.now(timezone.utc).isoformat())
        return cls(
            id=data.get("id", uuid4().hex[:8]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            license=data.get("license", "MIT"),
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else created,
            updated_at=datetime.fromisoformat(updated) if isinstance(updated, str) else updated,
            tags=list(data.get("tags", []) or []),
            compatible_with=list(data.get("compatible_with", []) or []),
            required_providers=list(data.get("required_providers", []) or []),
            required_models=list(data.get("required_models", []) or []),
        )


# ── LLMPackager ──────────────────────────────────────────────────────────────


class LLMPackager:
    """Create and manage .lmpack persona packages."""

    # Required files in the archive
    _REQUIRED_FILES = {
        "manifest.json": None,
        "personas/personas.json": None,
        "providers/providers.json": None,
        "models/models.json": None,
        "network/network.json": None,
    }

    def __init__(self, name: str, description: str = "") -> None:
        self._manifest = PackManifest(name=name, description=description)
        self._personas: Dict[str, PersonaConfig] = {}
        self._providers: Dict[str, Any] = {}  # provider_id -> config
        self._models: Dict[str, ModelSpec] = {}
        self._network: Optional[PersonaNetwork] = None
        self._sessions: List[Dict[str, Any]] = []
        self._readme: str = ""

    @property
    def manifest(self) -> PackManifest:
        return self._manifest

    @property
    def network(self) -> Optional[PersonaNetwork]:
        return self._network

    # ── Persona Management ─────────────────────────────────────────────────

    def add_persona(self, persona: PersonaConfig) -> None:
        """Add a persona to the pack."""
        self._personas[persona.role_id] = persona
        logger.info("Added persona '%s' to pack", persona.role_id)

    def remove_persona(self, role_id: str) -> bool:
        """Remove a persona from the pack."""
        if role_id in self._personas:
            del self._personas[role_id]
            logger.info("Removed persona '%s' from pack", role_id)
            return True
        return False

    def list_personas(self) -> List[PersonaConfig]:
        """List all personas in the pack."""
        return list(self._personas.values())

    # ── Provider Management ────────────────────────────────────────────────

    def add_provider(self, provider_id: str, config: Dict[str, Any]) -> None:
        """Add a provider configuration to the pack."""
        self._providers[provider_id] = config
        if provider_id not in self._manifest.required_providers:
            self._manifest.required_providers.append(provider_id)

    def remove_provider(self, provider_id: str) -> bool:
        """Remove a provider from the pack."""
        if provider_id in self._providers:
            del self._providers[provider_id]
            self._manifest.required_providers = [
                p for p in self._manifest.required_providers if p != provider_id
            ]
            return True
        return False

    # ── Model Management ───────────────────────────────────────────────────

    def add_model(self, model: ModelSpec) -> None:
        """Add a model specification to the pack."""
        self._models[model.model_id] = model
        if model.model_id not in self._manifest.required_models:
            self._manifest.required_models.append(model.model_id)

    def remove_model(self, model_id: str) -> bool:
        """Remove a model from the pack."""
        if model_id in self._models:
            del self._models[model_id]
            self._manifest.required_models = [
                m for m in self._manifest.required_models if m != model_id
            ]
            return True
        return False

    # ── Network Management ─────────────────────────────────────────────────

    def set_network(self, network: PersonaNetwork) -> None:
        """Set the persona network for the pack."""
        self._network = network

    # ── Session Management ─────────────────────────────────────────────────

    def add_session(self, session_config: Dict[str, Any]) -> None:
        """Add an example debate session to the pack."""
        self._sessions.append(session_config)

    # ── Documentation ──────────────────────────────────────────────────────

    def set_readme(self, readme: str) -> None:
        """Set the README documentation for the pack."""
        self._readme = readme

    # ── Package Creation ───────────────────────────────────────────────────

    def create_package(self, output_path: str) -> Path:
        """Create a .lmpack file at the specified path."""
        output = Path(output_path)
        if not output.suffix == ".lmpack":
            output = output.with_suffix(".lmpack")

        # Validate before creating — raise on any error.
        errors = self._validate()
        if errors:
            raise ValueError(f"Invalid package: {'; '.join(errors)}")

        # Create the zip archive
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
            zf.writestr("manifest.json", json.dumps(
                self._manifest.to_dict(), indent=2, ensure_ascii=False
            ))

            # Write personas
            personas_data = {rid: p.to_dict() for rid, p in self._personas.items()}
            zf.writestr("personas/personas.json", json.dumps(
                personas_data, indent=2, ensure_ascii=False
            ))

            # Write providers
            zf.writestr("providers/providers.json", json.dumps(
                self._providers, indent=2, ensure_ascii=False
            ))

            # Write models
            models_data = {mid: m.to_dict() for mid, m in self._models.items()}
            zf.writestr("models/models.json", json.dumps(
                models_data, indent=2, ensure_ascii=False
            ))

            # Write network
            if self._network:
                zf.writestr("network/network.json", json.dumps(
                    self._network.to_dict(), indent=2, ensure_ascii=False
                ))

            # Write sessions
            if self._sessions:
                zf.writestr("sessions/sessions.json", json.dumps(
                    self._sessions, indent=2, ensure_ascii=False
                ))

            # Write README
            if self._readme:
                zf.writestr("README.md", self._readme)

        logger.info("Created package at %s (%d personas, %d providers, %d models)",
                    output, len(self._personas), len(self._providers), len(self._models))

        return output

    # ── Package Import ─────────────────────────────────────────────────────

    @classmethod
    def from_package(cls, package_path: str) -> "LLMPackager":
        """Load a packager from an existing .lmpack file."""
        path = Path(package_path)
        if not path.exists():
            raise FileNotFoundError(f"Package not found: {package_path}")

        packager = cls(name=path.stem)

        with zipfile.ZipFile(path, "r") as zf:
            # Read manifest
            with zf.open("manifest.json") as f:
                packager._manifest = PackManifest.from_dict(json.load(f))

            # Read personas
            try:
                with zf.open("personas/personas.json") as f:
                    personas_data = json.load(f)
                    for rid, pdata in personas_data.items():
                        packager._personas[rid] = PersonaConfig.from_dict(pdata)
            except KeyError:
                pass

            # Read providers
            try:
                with zf.open("providers/providers.json") as f:
                    packager._providers = json.load(f)
            except KeyError:
                pass

            # Read models
            try:
                with zf.open("models/models.json") as f:
                    models_data = json.load(f)
                    for mid, mdata in models_data.items():
                        packager._models[mid] = ModelSpec.from_dict(mdata)
            except KeyError:
                pass

            # Read network
            try:
                with zf.open("network/network.json") as f:
                    network_data = json.load(f)
                    packager._network = PersonaNetwork.from_dict(network_data)
            except KeyError:
                pass

            # Read sessions
            try:
                with zf.open("sessions/sessions.json") as f:
                    packager._sessions = json.load(f)
            except KeyError:
                pass

            # Read README
            try:
                with zf.open("README.md") as f:
                    packager._readme = f.read().decode("utf-8")
            except KeyError:
                pass

        logger.info("Loaded package from %s", path)
        return packager

    # ── Validation ─────────────────────────────────────────────────────────

    def _validate(self) -> List[str]:
        """Validate the pack before creation."""
        errors = []

        if not self._manifest.is_complete:
            errors.append("Manifest name is required")

        if not self._personas:
            errors.append("At least one persona is required")

        # Check that all referenced personas exist in network
        if self._network:
            for node in self._network.list_nodes():
                if node.role_id not in self._personas:
                    errors.append(f"Network references persona '{node.role_id}' not in pack")

        return errors

    def validate(self) -> Dict[str, Any]:
        """Validate the pack and return results."""
        errors = self._validate()

        # Validate network if present
        network_errors = []
        if self._network:
            validation = self._network.validate()
            errors.extend(validation.get("errors", []))
            network_errors.extend(validation.get("warnings", []))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": network_errors,
            "persona_count": len(self._personas),
            "provider_count": len(self._providers),
            "model_count": len(self._models),
        }

    # ── Statistics ─────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Get statistics about the pack."""
        return {
            "manifest": self._manifest.to_dict(),
            "persona_count": len(self._personas),
            "provider_count": len(self._providers),
            "model_count": len(self._models),
            "session_count": len(self._sessions),
            "network_nodes": len(self._network.list_nodes()) if self._network else 0,
            "network_relationships": len(self._network._relationships) if self._network else 0,
        }
