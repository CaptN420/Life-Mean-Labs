"""R2 — les deux layouts de packages LM doivent être lus, ou refusés explicitement.

Constat d'audit (RESEARCH_READINESS_AUDIT.md, D1/D3) : `from_package` ne lisait que
`personas/personas.json`. Les deux packs réellement livrés dans `lmpack/` utilisent
`manifest.json` + `agents/<id>.json` (layout Studio) : ils se chargeaient donc
« à zéro persona » et `validate()` les déclarait invalides — en accusant le pack
au lieu du lecteur.

Ces tests figent le comportement correct : les deux layouts sont lus, et un
archive au format inconnu lève `PackageFormatError` au lieu de réussir à vide.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core.packager import LLMPackager, PackageFormatError
from core.personas.schema import PersonaConfig, PersonaType

REPO = Path(__file__).resolve().parents[1]
SHIPPED_PACKS = sorted(p for p in (REPO / "lmpack").glob("*.lmpack"))


def test_shipped_packs_are_discovered():
    """Garde-fou : si les packs disparaissent, le reste des tests mentirait."""
    assert len(SHIPPED_PACKS) >= 2, f"expected the shipped packs, found {SHIPPED_PACKS}"


@pytest.mark.parametrize("pack", SHIPPED_PACKS, ids=lambda p: p.name)
def test_studio_layout_pack_loads_and_validates(pack):
    packager = LLMPackager.from_package(str(pack))
    result = packager.validate()

    assert result["persona_count"] == 11, result
    assert result["valid"] is True, result["errors"]
    assert result["errors"] == []

    personas = packager.list_personas()
    assert len(personas) == 11
    for persona in personas:
        assert persona.system_prompt.strip(), "un agent sans prompt n'est pas utilisable"
        assert persona.role_id.strip()
        assert persona.metadata.get("provider"), "le fournisseur d'origine doit être conservé"


def test_studio_agents_keep_their_raw_persona_value():
    """`persona: "general"` n'existe pas dans PersonaType : on l'enregistre tel quel."""
    packager = LLMPackager.from_package(str(SHIPPED_PACKS[0]))
    persona = packager.list_personas()[0]
    assert persona.metadata["raw_persona_type"] == "general"
    assert persona.persona_type is PersonaType.OTHER


def test_studio_readme_txt_is_loaded():
    packager = LLMPackager.from_package(str(SHIPPED_PACKS[0]))
    assert packager._readme.strip(), "README.txt des packs Studio doit être lu"


def test_unknown_layout_raises_instead_of_loading_empty(tmp_path):
    bogus = tmp_path / "bogus.lmpack"
    with zipfile.ZipFile(bogus, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"name": "bogus", "version": "1.0"}))
        zf.writestr("weird/data.bin", "x")

    with pytest.raises(PackageFormatError) as exc:
        LLMPackager.from_package(str(bogus))
    assert "unrecognised .lmpack layout" in str(exc.value)


def test_agents_without_system_prompt_are_reported_not_ignored(tmp_path):
    pack = tmp_path / "promptless.lmpack"
    with zipfile.ZipFile(pack, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"name": "promptless", "version": "1.0"}))
        zf.writestr("agents/a.json", json.dumps({"id": "a", "name": "A"}))

    with pytest.raises(PackageFormatError) as exc:
        LLMPackager.from_package(str(pack))
    assert "usable system_prompt" in str(exc.value)


def test_canonical_layout_still_round_trips(tmp_path):
    """Le layout historique (personas/personas.json) ne doit pas régresser."""
    packager = LLMPackager("roundtrip", description="canonical layout")
    packager.add_persona(PersonaConfig(
        role_id="skeptic", name="Skeptic", persona_type=PersonaType.SKEPTIC,
        description="doubts", system_prompt="You doubt everything, with reasons.",
    ))
    out = packager.create_package(str(tmp_path / "roundtrip.lmpack"))
    assert Path(out).exists()

    reloaded = LLMPackager.from_package(str(out))
    result = reloaded.validate()
    assert result["valid"] is True, result["errors"]
    assert result["persona_count"] == 1
    assert reloaded.list_personas()[0].role_id == "skeptic"
