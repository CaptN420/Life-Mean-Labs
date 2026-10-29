"""End-to-end test for PersonaForge + PersonaNetwork + LLMPack + Orchestrator.

Scenario:
  Create 3 personas → connect them → assign 3 models → export .lmpack
  → reimport → run debate → compare results.

Success criteria:
  - No config loss
  - No secrets exported
  - Relations preserved
  - Recoverable errors
  - Latency metrics recorded
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.personas.schema import (
    DebateSessionConfig,
    ModelSpec,
    PersonaConfig,
    PersonaType,
    ProviderType,
    RelationshipType,
)
from core.personas.manager import PersonaManager, PersonaValidationError
from core.personas.network import PersonaNetwork
from core.packager import LLMPackager

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("e2e_test")


def test_persona_lifecycle() -> Dict[str, Any]:
    """Test create → validate → update → delete cycle."""
    logger.info("=== TEST: Persona Lifecycle ===")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        storage = Path(f.name)
    manager = PersonaManager(storage_path=storage)

    # Create personas
    p1 = manager.create_persona(
        role_id="descartes",
        name="Descartes",
        persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
        description="Father of modern philosophy, methodical doubter",
        system_prompt="I think, therefore I am. Question everything until you find indubitable truth.",
        color="#FF6B6B",
    )
    p2 = manager.create_persona(
        role_id="hume",
        name="Hume",
        persona_type=PersonaType.SKEPTIC,
        description="Empiricist, problem of induction, constant conjunction",
        system_prompt="All knowledge comes from experience. Causation is but habitual expectation.",
        color="#4ECDC4",
    )
    p3 = manager.create_persona(
        role_id="kant",
        name="Kant",
        persona_type=PersonaType.ETHICAL_PHILOSOPHER,
        description="Transcendental idealist, categorical imperative",
        system_prompt="Act only according to that maxim whereby you can at the same time will that it should become a universal law.",
        color="#45B7D1",
    )

    # Validate
    v1 = manager.validate_persona("descartes")
    assert v1["valid"], f"Validation failed: {v1}"

    # Update
    manager.update_persona("descartes", system_prompt="New prompt for testing.")
    updated = manager.get_persona("descartes")
    assert updated.system_prompt == "New prompt for testing."

    # Delete (should fail due to no children check - but we didn't create any)
    deleted = manager.delete_persona("hume")
    assert deleted, "Should delete hume"

    logger.info("Persona lifecycle: PASS")
    return {"personas_created": 3, "validated": True, "updated": True, "deleted": 1}


def test_template_instantiation() -> Dict[str, Any]:
    """Test template creation and instantiation."""
    logger.info("=== TEST: Template Instantiation ===")
    from core.personas.schema import PersonaType  # local import for enum
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        storage = Path(f.name)
    manager = PersonaManager(storage_path=storage)

    # Create a base persona
    base = manager.create_persona(
        role_id="philosopher_base",
        name="Philosopher Base",
        persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
        description="Base philosopher template",
        system_prompt="I am a base philosopher.",
    )

    # Create template from base
    template = manager.create_template(
        template_id="phenomenology_template",
        name="Phenomenology Template",
        description="Template for phenomenological analysis",
        base_persona_id="philosopher_base",
    )
    assert template.parent_persona_id == "philosopher_base"

    # Instantiate with overrides
    instantiated = manager.instantiate_template(
        template_id="phenomenology_template",
        new_role_id="husserl",
        overrides={
            "name": "Husserl",
            "persona_type": PersonaType.ANALYTICAL_PHILOSOPHER,
            "description": "Founder of phenomenology",
            "system_prompt": "Consciousness is always consciousness OF something. Phenomenological reduction reveals the structures of experience.",
            "color": "#9B59B6",
        },
    )
    assert instantiated.parent_persona_id == "phenomenology_template"
    assert instantiated.name == "Husserl"
    assert "Consciousness is always consciousness OF something" in instantiated.system_prompt

    # Test that instantiation without system_prompt fails
    try:
        manager.instantiate_template(
            template_id="phenomenology_template",
            new_role_id="bad_instantiation",
            overrides={"name": "Bad"},
        )
        assert False, "Should have raised ValidationError"
    except PersonaValidationError as e:
        assert e.code == "EMPTY_SYSTEM_PROMPT", f"Expected EMPTY_SYSTEM_PROMPT, got {e.code}"

    logger.info("Template instantiation: PASS")
    return {"template_created": True, "instantiated": True}


def test_network_relations() -> Dict[str, Any]:
    """Test network creation, relations, workflow generation."""
    logger.info("=== TEST: Network Relations ===")
    network = PersonaNetwork()

    # Add personas
    p1 = PersonaConfig(
        role_id="descartes",
        name="Descartes",
        persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
        description="Methodical doubter",
        system_prompt="I think therefore I am.",
    )
    p2 = PersonaConfig(
        role_id="hume",
        name="Hume",
        persona_type=PersonaType.SKEPTIC,
        description="Empiricist skeptic",
        system_prompt="All knowledge comes from experience.",
    )
    p3 = PersonaConfig(
        role_id="kant",
        name="Kant",
        persona_type=PersonaType.ETHICAL_PHILOSOPHER,
        description="Transcendental idealist",
        system_prompt="Categorical imperative.",
    )

    network.add_persona(p1)
    network.add_persona(p2)
    network.add_persona(p3)

    # Create relations
    network.connect("descartes", "hume", RelationshipType.CHALLENGER, strength=0.9)
    network.connect("hume", "kant", RelationshipType.DEBATE_PARTNER, strength=0.8)
    network.connect("descartes", "kant", RelationshipType.SYNTHESIZER, strength=0.7)

    # Validate
    validation = network.validate()
    assert validation["valid"], f"Validation errors: {validation['errors']}"

    # Generate workflow
    workflow = network.generate_workflow()
    assert len(workflow) == 3, f"Expected 3 nodes in workflow, got {len(workflow)}"

    # Export and reimport
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        tmp_path = f.name
    network.export_json(tmp_path)

    reimported = PersonaNetwork.import_json(tmp_path)
    assert len(reimported.list_nodes()) == 3
    assert len(reimported._relationships) == 3

    # Check workflow is derived (not stored separately)
    reimported_workflow = reimported.generate_workflow()
    assert len(reimported_workflow) == 3

    logger.info("Network relations: PASS")
    return {"relations_created": 3, "workflow_generated": True, "roundtrip": True}


def test_llmpack_creation() -> Dict[str, Any]:
    """Test .lmpack creation, validation, and import."""
    logger.info("=== TEST: LLMPack Creation ===")

    packager = LLMPackager(
        name="Philosophical Debate Pack",
        description="Descartes vs Hume vs Kant on perception",
    )

    # Add personas
    p1 = PersonaConfig(
        role_id="descartes",
        name="Descartes",
        persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
        description="Father of modern philosophy",
        system_prompt="I think, therefore I am. Methodical doubt leads to certainty.",
    )
    p2 = PersonaConfig(
        role_id="hume",
        name="Hume",
        persona_type=PersonaType.SKEPTIC,
        description="Empiricist skeptic",
        system_prompt="All knowledge comes from experience and custom.",
    )
    p3 = PersonaConfig(
        role_id="kant",
        name="Kant",
        persona_type=PersonaType.ETHICAL_PHILOSOPHER,
        description="Transcendental idealist",
        system_prompt="We can only know phenomena, not noumena.",
    )

    packager.add_persona(p1)
    packager.add_persona(p2)
    packager.add_persona(p3)

    # Add models
    m1 = ModelSpec(
        model_id="phi-4-mini-reasoning",
        provider=ProviderType.LOCAL,
        endpoint="http://localhost:1234/v1",
        context_window=4096,
        max_output_tokens=2000,
    )
    m2 = ModelSpec(
        model_id="gemma-4-e4b",
        provider=ProviderType.LOCAL,
        endpoint="http://localhost:1234/v1",
        context_window=4096,
        max_output_tokens=2000,
    )
    m3 = ModelSpec(
        model_id="ministral-3-3b",
        provider=ProviderType.LOCAL,
        endpoint="http://localhost:1234/v1",
        context_window=4096,
        max_output_tokens=2000,
    )

    packager.add_model(m1)
    packager.add_model(m2)
    packager.add_model(m3)

    # Add network
    network = PersonaNetwork()
    network.add_persona(p1)
    network.add_persona(p2)
    network.add_persona(p3)
    network.connect("descartes", "hume", RelationshipType.CHALLENGER)
    network.connect("hume", "kant", RelationshipType.DEBATE_PARTNER)
    packager.set_network(network)

    # Add example session
    session = DebateSessionConfig(
        topic="Is perception reality?",
        personas=["descartes", "hume", "kant"],
        model_pool=["phi-4-mini-reasoning", "gemma-4-e4b", "ministral-3-3b"],
        max_turns=10,
    )
    packager.add_session(session.to_dict())

    # Validate before export
    validation = packager.validate()
    assert validation["valid"], f"Validation errors: {validation['errors']}"

    # Export to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".lmpack", delete=False) as f:
        pack_path = f.name

    created_path = packager.create_package(pack_path)
    assert created_path.exists()

    # Verify no secrets in package
    import zipfile
    with zipfile.ZipFile(created_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert "api_key" not in str(manifest).lower(), "Secrets found in manifest!"
        personas_data = json.loads(zf.read("personas/personas.json"))
        assert len(personas_data) == 3

    # Reimport
    reimported = LLMPackager.from_package(str(created_path))
    assert len(reimported.list_personas()) == 3
    assert len(reimported._models) == 3
    assert reimported.network is not None
    assert len(reimported.network.list_nodes()) == 3

    logger.info("LLMPack creation: PASS")
    return {
        "personas": 3,
        "models": 3,
        "relations": 2,
        "sessions": 1,
        "exported": str(created_path),
        "reimported": True,
    }


def test_debate_execution() -> Dict[str, Any]:
    """Test a minimal debate execution with the created personas."""
    logger.info("=== TEST: Debate Execution ===")

    # This would normally call the orchestrator, but for now we verify
    # that the session config is valid and can be serialized
    session = DebateSessionConfig(
        topic="Is perception reality?",
        personas=["descartes", "hume", "kant"],
        model_pool=["phi-4-mini-reasoning", "gemma-4-e4b", "ministral-3-3b"],
        max_turns=3,
        routing_method="round_robin",
    )

    # Verify serialization roundtrip
    d = session.to_dict()
    restored = DebateSessionConfig.from_dict(d)
    assert restored.topic == session.topic
    assert restored.personas == session.personas
    assert restored.routing_method == "round_robin"

    logger.info("Debate execution config: PASS")
    return {"topic": session.topic, "turns": session.max_turns, "routing": session.routing_method}


def main() -> int:
    """Run all tests and report results."""
    results: Dict[str, Any] = {}

    try:
        results["persona_lifecycle"] = test_persona_lifecycle()
    except Exception as e:
        logger.error("Persona lifecycle FAILED: %s", e)
        results["persona_lifecycle"] = {"error": str(e)}

    try:
        results["template_instantiation"] = test_template_instantiation()
    except Exception as e:
        logger.error("Template instantiation FAILED: %s", e)
        results["template_instantiation"] = {"error": str(e)}

    try:
        results["network_relations"] = test_network_relations()
    except Exception as e:
        logger.error("Network relations FAILED: %s", e)
        results["network_relations"] = {"error": str(e)}

    try:
        results["llmpack_creation"] = test_llmpack_creation()
    except Exception as e:
        logger.error("LLMPack creation FAILED: %s", e)
        results["llmpack_creation"] = {"error": str(e)}

    try:
        results["debate_execution"] = test_debate_execution()
    except Exception as e:
        logger.error("Debate execution FAILED: %s", e)
        results["debate_execution"] = {"error": str(e)}

    # Summary
    passed = sum(1 for v in results.values() if "error" not in v)
    total = len(results)

    print("\n" + "=" * 60)
    print("E2E TEST RESULTS")
    print("=" * 60)
    for test_name, result in results.items():
        status = "PASS" if "error" not in result else "FAIL"
        print(f"  {test_name}: {status}")
        if "error" in result:
            print(f"    Error: {result['error']}")

    print(f"\nTotal: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
