"""Demo: Deterministic Debate Engine with Mixed Providers.

Shows how to:
1. Create personas with the unified manager
2. Configure mixed providers (OpenAI + local)
3. Run a debate with stagnation detection
4. Get deterministic arbiter decisions
"""

import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.personas.manager import PersonaManager
from core.personas.schema import PersonaType, ProviderType
from core.providers.base import (
    MixedProviderRouter,
    MockLLMProvider,
    ProviderConfig,
    ProviderRegistry,
)
from core.debate.engine import DebateEngine, DebateSessionConfig


def demo_personas():
    """Demonstrate persona creation and management."""
    print("\n" + "="*60)
    print("1. PERSONA MANAGEMENT")
    print("="*60)

    manager = PersonaManager()

    # Create personas
    p1 = manager.create_persona(
        role_id="demo_existentialist",
        name="Existentialist",
        persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
        description="Focuses on freedom and meaning creation",
        system_prompt="You are an existentialist philosopher. Reason about freedom and authenticity.",
        color="#9370DB",
    )
    print(f"✓ Created: {p1.role_id} (hash={p1.content_hash()[:8]}...)")

    p2 = manager.create_persona(
        role_id="demo_stoic",
        name="Stoic",
        persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,
        description="Focuses on virtue and acceptance",
        system_prompt="You are a stoic philosopher. Reason about control and virtue.",
        color="#4169E1",
    )
    print(f"✓ Created: {p2.role_id}")

    # Validate
    validation = manager.validate_persona("demo_existentialist")
    print(f"✓ Validation: valid={validation['valid']}, errors={len(validation['errors'])}")

    # List all
    personas = manager.list_personas()
    print(f"✓ Total personas: {len(personas)}")


def demo_providers():
    """Demonstrate mixed provider routing."""
    print("\n" + "="*60)
    print("2. MIXED PROVIDER ROUTING")
    print("="*60)

    registry = ProviderRegistry()

    # Register mock providers (simulating OpenAI and local)
    openai_config = ProviderConfig(
        provider_type=ProviderType.OPENAI,
        model_id="gpt-4",
        api_key_env="OPENAI_API_KEY",
    )
    local_config = ProviderConfig(
        provider_type=ProviderType.LOCAL,
        model_id="llama-7b",
        endpoint="http://localhost:1234/v1",
    )

    registry.register("openai", MockLLMProvider(openai_config), openai_config)
    registry.register("local", MockLLMProvider(local_config), local_config)

    # Configure router
    router = MixedProviderRouter(registry)
    router.add_role_mapping("existentialist", "openai")  # OpenAI for philosopher
    router.add_role_mapping("stoic", "local")            # Local for stoic
    router.set_fallback("local")

    # Route a chat
    result = router.route_chat(
        messages=[{"role": "user", "content": "What is the meaning of life?"}],
        role_id="existentialist",
    )
    print(f"✓ Routed to: {result.model_used} (provider={result.provider.value})")
    print(f"  Response: {result.text[:60]}...")


def demo_debate():
    """Demonstrate a complete debate session."""
    print("\n" + "="*60)
    print("3. DETERMINISTIC DEBATE")
    print("="*60)

    # Configure debate
    config = DebateSessionConfig(
        topic="Does objective moral truth exist?",
        personas=["existentialist", "stoic"],
        model_pool=["gpt-4", "llama-7b"],
        max_turns=6,
        routing_method="context_aware",
    )

    # Create engine with mock providers
    personas = {
        "existentialist": type('P', (), {'role_id': 'existentialist'})(),
        "stoic": type('P', (), {'role_id': 'stoic'})(),
    }
    engine = DebateEngine(config, personas)

    # Start debate
    engine.start()
    print(f"✓ Debate started: {engine.session_id}")
    print(f"  Topic: {config.topic}")
    print(f"  Max turns: {config.max_turns}")

    # Run turns
    responses = [
        "Moral truths are constructed through authentic choice.",
        "Virtue is the only true good, independent of opinion.",
        "But who decides what is authentic?",
        "Reason itself provides the standard.",
    ]

    for i, response in enumerate(responses):
        speaker = "existentialist" if i % 2 == 0 else "stoic"
        engine.step(speaker, response, new_evidence_count=1)
        print(f"  Turn {i+1}: {speaker} — '{response[:40]}...'")

    # Add claims
    engine.add_claim(
        claim_id="c1",
        agent_id="existentialist",
        hypothesis="Moral truths are constructed",
        arguments=["Authentic choice creates value"],
        evidence_refs=["evidence_1"],
    )
    engine.add_claim(
        claim_id="c2",
        agent_id="stoic",
        hypothesis="Virtue is objective",
        arguments=["Reason provides universal standard"],
        evidence_refs=["evidence_2"],
    )

    # Stop and arbitrate
    engine.stop()
    decision = engine.arbitrate()
    print(f"\n✓ Arbiter decision: {decision.value}")
    print(f"  Justification: {engine.get_result().arbiter_justification[:80]}...")

    # Get result
    result = engine.get_result()
    print(f"\n📊 Debate Metrics:")
    print(f"  Turns: {result.turns_committed}/{result.max_turns}")
    print(f"  Claims: {len(result.claims)}")
    print(f"  Trace ID: {result.trace_id}")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("LIFE_MEAN — Deterministic Debate Engine Demo")
    print("="*60)

    demo_personas()
    demo_providers()
    demo_debate()

    print("\n" + "="*60)
    print("✅ Demo completed successfully!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
