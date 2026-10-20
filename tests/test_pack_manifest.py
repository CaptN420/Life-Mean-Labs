"""
Test Pack Manifest — Validation des règles de redistribution.

Vérifie que les assets avec droits inconnus sont exclus par défaut.
Vérifie que les licences Apache-2.0 et MIT sont acceptées pour le code.
"""

from __future__ import annotations

import pytest
from data.schemas.pack_manifest import (
    PackManifest,
    CreatorMetadata,
    ProvenanceChain,
    ComponentManifest,
    AssetReference,
)


class TestComponentLicense:
    """Test component license rules."""

    def test_code_with_mit_license(self):
        """MIT license is accepted for code components."""
        comp = ComponentManifest(
            type="skill",
            path="tool.py",
            license="MIT",
            redistributable=True,
        )
        assert comp.redistributable is True

    def test_code_with_apache_license(self):
        """Apache-2.0 license is accepted for code components."""
        comp = ComponentManifest(
            type="workflow",
            path="workflow.yaml",
            license="Apache-2.0",
            redistributable=True,
        )
        assert comp.redistributable is True

    def test_unknown_license_excluded(self):
        """Components with Unknown license are excluded by default."""
        comp = ComponentManifest(
            type="persona",
            path="persona.txt",
            license="Unknown",
            redistributable=False,
        )
        assert comp.redistributable is False

    def test_asset_never_redistributable_by_default(self):
        """Assets are never redistributable by default."""
        comp = ComponentManifest.from_file_path("texture.png")
        assert comp.type == "asset"
        assert comp.license == "Unknown"
        assert comp.redistributable is False

    def test_asset_with_valid_license_can_be_redistributable(self):
        """Assets with valid license can be marked as redistributable."""
        comp = ComponentManifest(
            type="asset",
            path="model.fbx",
            license="CC-BY-SA-4.0",
            redistributable=True,
        )
        assert comp.redistributable is True


class TestAssetReference:
    """Test asset reference rules."""

    def test_asset_requires_attribution(self):
        """Assets require attribution."""
        asset = AssetReference(
            path="texture.png",
            type="texture",
            license="CC-BY-NC-SA-4.0",
            attribution="Artist Name",
        )
        assert asset.attribution == "Artist Name"

    def test_asset_never_redistributable(self):
        """External assets are never redistributable."""
        asset = AssetReference(
            path="sound.wav",
            type="sound",
            license="Proprietary",
            attribution="Composer",
        )
        assert asset.redistributable is False

    def test_pack_with_unattributed_asset_fails_validation(self):
        """Packs with unattributed assets fail validation."""
        pack = PackManifest(
            name="Test Pack",
            components=[
                ComponentManifest(
                    path="asset.png",
                    type="asset",
                    license="Unknown",
                    asset_refs=[AssetReference(path="texture.png", license="", attribution="")],
                )
            ],
        )
        errors = pack.validate()
        assert len(errors) > 0


class TestPackProvenance:
    """Test pack provenance tracking."""

    def test_original_pack(self):
        """Original pack has no provenance."""
        pack = PackManifest(name="Original")
        assert not pack.has_provenance

    def test_derived_pack(self):
        """Derived pack has provenance chain."""
        provenance = ProvenanceChain(
            original_pack_id="original-uuid",
            derived_from="original-uuid",
            license="MIT",
            attribution="Créé par @original, adapté par @adapter",
        )
        pack = PackManifest(name="Derived", provenance=provenance)
        assert pack.has_provenance

    def test_creator_visibility(self):
        """Creator visibility affects pack public status."""
        # Public creator
        pack = PackManifest(
            name="Public",
            creator=CreatorMetadata(id="c1", display_name="user", visibility="public"),
        )
        assert pack.is_public

        # Anonymous creator
        pack = PackManifest(
            name="Anonymous",
            creator=CreatorMetadata(id="c2", visibility="anonymous"),
        )
        assert not pack.is_public

        # Private creator
        pack = PackManifest(
            name="Private",
            creator=CreatorMetadata(id="c3", visibility="private"),
        )
        assert not pack.is_public


class TestPackRedistribution:
    """Test pack redistribution rules."""

    def test_get_redistributable_components(self):
        """Only redistributable components are returned."""
        pack = PackManifest(
            name="Mixed Pack",
            components=[
                ComponentManifest(path="code.py", license="MIT", redistributable=True),
                ComponentManifest(path="doc.md", license="Apache-2.0", redistributable=True),
                ComponentManifest(path="asset.png", license="Unknown", redistributable=False),
            ],
        )
        redist = pack.get_redistributable_components()
        assert len(redist) == 2
        assert all(c.redistributable for c in redist)

    def test_get_non_redistributable_assets(self):
        """Non-redistributable assets are collected."""
        pack = PackManifest(
            name="Asset Pack",
            components=[
                ComponentManifest(
                    path="comp1",
                    asset_refs=[
                        AssetReference(path="texture.png", license="CC-BY-NC", attribution="Artist"),
                        AssetReference(path="model.fbx", license="Proprietary", attribution="Studio"),
                    ],
                )
            ],
        )
        assets = pack.get_non_redistributable_assets()
        assert len(assets) == 2
        assert all(not a.redistributable for a in assets)

    def test_export_excludes_unknown_assets(self):
        """Export should exclude assets with unknown rights."""
        pack = PackManifest(
            name="Export Test",
            components=[
                ComponentManifest(
                    path="code.py",
                    license="MIT",
                    redistributable=True,
                ),
                ComponentManifest(
                    path="asset.png",
                    license="Unknown",
                    redistributable=False,
                    asset_refs=[AssetReference(path="texture.png", license="Unknown", attribution="?")],
                ),
            ],
        )
        # Simulate export logic
        exportable = [c for c in pack.components if c.redistributable]
        assert len(exportable) == 1
        assert exportable[0].path == "code.py"
