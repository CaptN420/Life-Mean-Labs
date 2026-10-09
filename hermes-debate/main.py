#!/usr/bin/env python3
"""
CLI for Hermes Multi-Agent Debate Orchestrator.
Usage: python -m hermes_debate --topic "What is the meaning of life?"
"""

import argparse
import asyncio
import json
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hermes_debate.config import load_config, HermesConfig
from hermes_debate.orchestrator.hermes import HermesOrchestrator
from hermes_debate.observability.logging import get_logger, HermesLogger


def parse_args():
    parser = argparse.ArgumentParser(
        description='Hermes Multi-Agent Debate Orchestrator'
    )
    parser.add_argument(
        '--topic',
        type=str,
        required=True,
        help='The debate topic'
    )
    parser.add_argument(
        '--max-turns',
        type=int,
        default=20,
        help='Maximum number of debate turns'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run simulation without loading models'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file for results (JSON)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    return parser.parse_args()


async def run_debate(topic: str, max_turns: int, simulation: bool = False) -> dict:
    """Run a debate on the given topic."""
    # Load config
    config = load_config()
    config.simulation = simulation
    
    # Setup logging
    log_level = logging.DEBUG if simulation else logging.INFO
    logger = get_logger("hermes")
    logger.logger.setLevel(log_level)
    
    # Create orchestrator
    orchestrator = HermesOrchestrator(config)
    
    # Run debate
    result = await orchestrator.run_debate(topic, max_turns)
    
    # Convert HermesResult to dict if needed
    if hasattr(result, 'to_dict'):
        return result.to_dict()
    return result


def print_result(result):
    """Print debate result."""
    # Handle HermesResult object
    if hasattr(result, 'to_dict'):
        result = result.to_dict()
    
    print("\n" + "=" * 60)
    print("HERMES DEBATE RESULT")
    print("=" * 60)
    print(f"\nTopic: {result.get('topic', 'N/A')}")
    print(f"Debate ID: {result.get('debate_id', 'N/A')}")
    print(f"Turns completed: {len(result.get('turns', []))}")
    
    # Print turns
    print("\n--- DEBATE TURNS ---")
    for turn in result.get('turns', []):
        print(f"\n[Turn {turn.get('turn_number', 'N/A')}]")
        print(f"Agent: {turn.get('agent', 'N/A')}")
        content = turn.get('content', '')
        # Truncate long content
        if len(content) > 500:
            content = content[:500] + "..."
        print(f"Content: {content}")
    
    # Print final state
    print("\n--- FINAL STATE ---")
    final_state = result.get('final_state', {})
    print(f"Progress: {final_state.get('progress_score', 0):.2f}")
    print(f"Consensus: {final_state.get('consensus_reached', False)}")
    print(f"Loop detected: {final_state.get('loop_detected', False)}")
    
    # Print metrics
    metrics = result.get('metrics', {})
    if metrics:
        print("\n--- METRICS ---")
        for key, value in metrics.items():
            print(f"{key}: {value}")


def save_result(result: dict, output_path: str):
    """Save result to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"Result saved to: {output_path}")


async def main():
    args = parse_args()
    
    print(f"\nStarting Hermes Debate Orchestrator")
    print(f"Topic: {args.topic}")
    print(f"Max turns: {args.max_turns}")
    print(f"Simulation mode: {args.dry_run}\n")
    
    try:
        result = await run_debate(
            topic=args.topic,
            max_turns=args.max_turns,
            simulation=args.dry_run
        )
        
        # Print or save result
        if args.output:
            save_result(result, args.output)
        else:
            print_result(result)
            
    except Exception as e:
        logging.error(f"Debate failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
