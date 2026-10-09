"""Main entry point for Philosophical Council."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path so imports work from any directory
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

# Also add parent as fallback (for running from within the package dir)
if str(project_root.parent) not in sys.path:
    sys.path.insert(0, str(project_root.parent))

try:
    from philosophical_council.config import Config, load_config
    from philosophical_council.database.database import Database
    from philosophical_council.llm.client import LLMClient
    from philosophical_council.memory.consolidation import MemoryConsolidator
    from philosophical_council.memory.long_term import LongTermMemory
    from philosophical_council.memory.mid_term import MidTermMemory
    from philosophical_council.memory.short_term import ShortTermMemory
    from philosophical_council.agents.existentialist import ExistentialistAgent
    from philosophical_council.agents.stoic import StoicAgent
    from philosophical_council.agents.nihilist import NihilistAgent
    from philosophical_council.agents.spiritual import SpiritualAgent
    from philosophical_council.agents.skeptic import SkepticAgent
    from philosophical_council.agents.pragmatist import PragmatistAgent
    from philosophical_council.agents.moderator import ModeratorAgent
    from philosophical_council.core.debate_engine import DebateEngine
    from philosophical_council.ui.app import PhilosophicalCouncilApp
except ImportError as exc:
    print(f"Import error: {exc}")
    print(f"Project root: {project_root}")
    print(f"sys.path: {sys.path[:3]}")
    raise


def main() -> None:
    """Main entry point."""
    # Load config
    config = load_config()

    # Setup logging
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "application.log"),
            logging.StreamHandler(),
        ],
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting Philosophical Council")

    # Initialize components
    db = Database(config.db_path)

    llm = LLMClient(
        base_url=config.lm_studio.base_url,
        api_key=config.lm_studio.api_key,
    )

    # Memory
    short_term = ShortTermMemory(capacity=config.debate.short_term_turns)
    mid_term = MidTermMemory()
    long_term = LongTermMemory()
    consolidator = MemoryConsolidator(mid_term, long_term)

    # Agents
    agents = {
        "existentialist": ExistentialistAgent(model=config.models.existentialist),
        "stoic": StoicAgent(model=config.models.stoic),
        "nihilist": NihilistAgent(model=config.models.nihilist),
        "spiritual": SpiritualAgent(model=config.models.spiritual),
        "skeptic": SkepticAgent(model=config.models.skeptic),
        "pragmatist": PragmatistAgent(model=config.models.pragmatist),
    }
    moderator = ModeratorAgent(model=config.models.moderator)

    # Engine
    engine = DebateEngine(config, db, llm)
    engine.short_term_memory = short_term
    engine.mid_term_memory = mid_term
    engine.long_term_memory = long_term
    engine.consolidator = consolidator

    for agent in agents.values():
        engine.register_agent(agent)
    engine.register_moderator(moderator)

    # Create and run app
    app = PhilosophicalCouncilApp(config=config)
    app.mainloop()


if __name__ == "__main__":
    main()
