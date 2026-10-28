#!/usr/bin/env python3
"""Smoke test: run a real debate with a local LLM via LM Studio.

Usage:
    python scripts/smoke_test_debate.py --question "Is free will compatible with determinism?"
    python scripts/smoke_test_debate.py --condition shared --rounds 3
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from life_mean_lab.orchestrator import (
    DebateExperimentRunner,
    DebateConfig,
    DebateCondition,
    RealLLMExecutor,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real debate smoke test")
    parser.add_argument("--question", default="Is free will compatible with determinism?", help="Question to debate")
    parser.add_argument("--condition", choices=["independent", "shared", "adaptive"], default="shared")
    parser.add_argument("--rounds", type=int, default=3, help="Max rounds")
    parser.add_argument("--agents", type=int, default=3, help="Number of agents")
    parser.add_argument("--base-url", default="http://localhost:1234/v1", help="LM Studio endpoint")
    parser.add_argument("--api-key", default="", help="LM Studio API key (or leave empty to use env)")
    parser.add_argument("--model", default="llama-3.2-1b", help="Model name")
    parser.add_argument("--output", default="/tmp/debate_result.json", help="Output path")
    args = parser.parse_args()

    # Resolve API key: CLI > env > .env file
    api_key = args.api_key or os.environ.get("LIFE_MEAN_LLM_API_KEY", "")
    if not api_key:
        from pathlib import Path as P
        env_path = P(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("LIFE_MEAN_LLM_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        print("WARNING: No API key provided. Set LIFE_MEAN_LLM_API_KEY or pass --api-key")

    # Initialize real LLM executor.
    executor = RealLLMExecutor(
        base_url=args.base_url,
        api_key=api_key,
        default_model=args.model,
    )

    if not executor.is_available:
        print(f"ERROR: Cannot connect to LLM at {args.base_url}")
        print("Ensure LM Studio is running with a model loaded.")
        sys.exit(1)

    print(f"Connected to {args.base_url} (model: {args.model})")

    # Map condition string to enum.
    condition_map = {
        "independent": DebateCondition.INDEPENDENT_AGENTS,
        "shared": DebateCondition.SHARED_MEMORY,
        "adaptive": DebateCondition.ADAPTIVE_RULES,
    }
    condition = condition_map[args.condition]

    # Run debate using the executor's execute method directly.
    config = DebateConfig(
        question=args.question,
        num_agents=args.agents,
        max_rounds=args.rounds,
        condition=condition,
    )

    # Create a wrapper that matches the expected interface.
    def llm_wrapper(model: str, prompt: str, system_prompt: str, max_tokens: int, temperature: float) -> dict:
        return executor._call_llm(prompt, max_tokens, temperature)

    runner = DebateExperimentRunner(llm_executor=llm_wrapper)
    result = runner.run(config)

    # Export results.
    output_path = Path(args.output)
    report = {
        "experiment_id": result.experiment_id,
        "condition": result.condition.value,
        "question": args.question,
        "summary": result.ledger.get_summary(),
        "emergence_measures": result.emergence_measures.to_dict(),
        "tokens_total": result.tokens_total,
        "duration_seconds": result.duration_seconds,
    }

    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResult exported to {output_path}")
    print(f"Total events: {report['summary']['total_events']}")
    print(f"Tokens used: {report['tokens_total']}")
    print(f"Duration: {report['duration_seconds']:.1f}s")

    # Print argument diversity.
    args_list = [e for e in result.ledger._events if e.event_type.value == "argument"]
    print(f"Arguments recorded: {len(args_list)}")


if __name__ == "__main__":
    main()
