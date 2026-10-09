"""
Main CLI entry point for Hermes.
"""

import argparse
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hermes_debate.config import load_config
from hermes_debate.orchestrator.hermes import HermesOrchestrator


def setup_logging(debug: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


async def run_debate(user_input: str, config_path: str = None, dry_run: bool = False) -> None:
    """Run a debate on the given topic."""
    # Load configuration
    config = load_config()
    
    # Override simulation mode if requested
    if dry_run:
        config.simulation = True
    
    # Setup logging
    setup_logging(debug=True)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting Hermes Orchestrator v{__import__('hermes_debate').__version__}")
    logger.info(f"Mode: {'SIMULATION' if config.simulation else 'PRODUCTION'}")
    logger.info(f"Topic: {user_input}")
    
    # Create orchestrator
    orchestrator = HermesOrchestrator(config)
    
    # Run debate
    result = await orchestrator.run(user_input)
    
    # Print results
    print("\n" + "="*60)
    print("DEBATE RESULTS")
    print("="*60)
    print(f"\nQuestion: {result.debate_state.request}")
    print(f"\nAnswer:\n{result.answer}")
    print(f"\nMetrics:")
    for key, value in result.metrics.items():
        print(f"  {key}: {value}")
    print("\n" + "="*60)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Hermes Multi-Agent Debate Orchestrator'
    )
    parser.add_argument(
        'topic',
        help='The philosophical topic to debate'
    )
    parser.add_argument(
        '--config', '-c',
        help='Path to config.yaml',
        default=None
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Run in simulation mode (no real models)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Run the debate
    asyncio.run(run_debate(args.topic, args.config, args.dry_run))


if __name__ == '__main__':
    main()
