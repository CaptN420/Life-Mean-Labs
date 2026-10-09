"""Main application window."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import *

from ..config import Config, load_config, save_config
from ..core.debate_engine import DebateEngine
from ..core.debate_saver import DebateSaver
from ..database.database import Database
from ..llm.client import LLMClient
from ..core.router import ModelRouter, RoutingContext
from ..memory.consolidation import MemoryConsolidator
from ..memory.long_term import LongTermMemory
from ..memory.mid_term import MidTermMemory
from ..memory.short_term import ShortTermMemory
from ..agents.existentialist import ExistentialistAgent
from ..agents.stoic import StoicAgent
from ..agents.nihilist import NihilistAgent
from ..agents.spiritual import SpiritualAgent
from ..agents.skeptic import SkepticAgent
from ..agents.pragmatist import PragmatistAgent
from ..agents.moderator import ModeratorAgent
from ..ui.settings_view import SettingsView

logger = logging.getLogger(__name__)


class PhilosophicalCouncilApp(tb.Window):
    """Main application window for Philosophical Council."""

    def __init__(self, config: Optional[Config] = None) -> None:
        super().__init__(theme="cosmo", title="Philosophical Council")
        self.geometry("1200x800")
        self.minsize(1000, 700)

        self.config = config or load_config()
        self._setup_logging()
        self._setup_components()
        self._build_ui()
        self._update_agent_labels()  # Update labels after UI is built
        self._load_models()

        # Bind close event
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Bind run debate event from settings
        self.bind('<<RunDebate>>', lambda e: self._start_debate())

    def _setup_logging(self) -> None:
        """Configure logging."""
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_dir / "application.log"),
                logging.StreamHandler(),
            ],
        )

    def _setup_components(self) -> None:
        """Initialize all components."""
        try:
            # Database
            db_path = self.config.db_path or str(Path(__file__).parent.parent / "debate.db")
            logger.info("Initializing database at: %s", db_path)
            self.db = Database(db_path)

            # LLM Client
            logger.info("Initializing LLM client at: %s", self.config.lm_studio.base_url)
            self.llm = LLMClient(
                base_url=self.config.lm_studio.base_url,
                api_key=self.config.lm_studio.api_key,
            )

            # Model Router - for dynamic model selection
            self.router = ModelRouter()
            self.router.set_method(self.config.router.method)
            logger.info("Model router initialized with method: %s", self.config.router.method)

            # Memory
            self.short_term = ShortTermMemory(capacity=self.config.debate.short_term_turns)
            self.mid_term = MidTermMemory()
            self.long_term = LongTermMemory()
            self.consolidator = MemoryConsolidator(self.mid_term, self.long_term)

            # Agents - use persona configs if available
            self.agents = {}
            for role in ["existentialist", "stoic", "nihilist", "spiritual", "skeptic", "pragmatist"]:
                agent_class_map = {
                    "existentialist": ExistentialistAgent,
                    "stoic": StoicAgent,
                    "nihilist": NihilistAgent,
                    "spiritual": SpiritualAgent,
                    "skeptic": SkepticAgent,
                    "pragmatist": PragmatistAgent,
                }
                agent_class = agent_class_map.get(role)
                if agent_class:
                    # Get persona config if available
                    persona_config = self.config.personas.get(role)
                    model = getattr(self.config.models, role, "")
                    if persona_config and persona_config.system_prompt:
                        # Create agent with custom persona
                        from ..agents.base_agent import AgentConfig
                        config = AgentConfig(
                            role=role,
                            name=persona_config.name or role.capitalize(),
                            system_prompt=persona_config.system_prompt,
                            model=model,
                            color=persona_config.color,
                        )
                        agent = agent_class.__new__(agent_class)
                        agent.config = config
                        agent._response_history = []
                        agent._arguments_expressed = []
                        self.agents[role] = agent
                    else:
                        # Use default agent
                        self.agents[role] = agent_class(model)

            self.moderator = ModeratorAgent(model=self.config.models.moderator)

            # Debate Engine
            self.engine = DebateEngine(self.config, self.db, self.llm)
            self.engine.short_term_memory = self.short_term
            self.engine.mid_term_memory = self.mid_term
            self.engine.long_term_memory = self.long_term
            self.engine.consolidator = self.consolidator

            for agent in self.agents.values():
                self.engine.register_agent(agent)
            self.engine.register_moderator(self.moderator)

            # Wire up callbacks to update the UI
            self.engine.add_callback(self._on_debate_update)

            # UI state
            self._current_debate_id: Optional[int] = None

            # Debate saver
            storage_dir = Path(__file__).parent.parent / "storage" / "debates"
            self.debate_saver = DebateSaver(str(storage_dir))

            logger.info("All components initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize components: %s", exc, exc_info=True)
            raise

    def _build_ui(self) -> None:
        """Build the user interface."""
        # Main container with tabs
        main_frame = tb.Frame(self, padding=10)
        main_frame.pack(fill=BOTH, expand=True)

        # Tab notebook
        self.tabs = tb.Notebook(main_frame)
        self.tabs.pack(fill=BOTH, expand=True)

        # Debate tab
        debate_tab = tb.Frame(self.tabs)
        self.tabs.add(debate_tab, text="Debate")
        self._build_debate_tab(debate_tab)

        # Settings tab
        settings_tab = tb.Frame(self.tabs)
        self.tabs.add(settings_tab, text="Settings")
        self.settings_view = SettingsView(settings_tab, self.config)
        self.settings_view.pack(fill=BOTH, expand=True, padx=10, pady=10)

    def _build_debate_tab(self, parent: tb.Frame) -> None:
        """Build the debate tab with controls and view."""
        # Top controls
        ctrl_frame = tb.Frame(parent)
        ctrl_frame.pack(fill=X)

        # Status label
        self.status_label = tb.Label(ctrl_frame, text="Status: Idle", font=("Consolas", 10))
        self.status_label.pack(side=LEFT)

        # Turn counter
        self.turn_label = tb.Label(ctrl_frame, text="Turns: 0", font=("Consolas", 10))
        self.turn_label.pack(side=LEFT, padx=(20, 0))

        # Control buttons
        btn_frame = tb.Frame(ctrl_frame)
        btn_frame.pack(side=RIGHT)

        self.start_btn = tb.Button(btn_frame, text="Start", command=self._start_debate, width=10)
        self.start_btn.pack(side=LEFT, padx=2)

        self.pause_btn = tb.Button(btn_frame, text="Pause", command=self._pause_debate, width=10)
        self.pause_btn.pack(side=LEFT, padx=2)

        self.stop_btn = tb.Button(btn_frame, text="Stop", command=self._stop_debate, width=10)
        self.stop_btn.pack(side=LEFT, padx=2)

        # Main content area
        content_frame = tb.Frame(parent)
        content_frame.pack(fill=BOTH, expand=True, pady=(10, 0))

        # Debate view (left)
        debate_frame = tb.LabelFrame(content_frame, text="Debate", padding=10)
        debate_frame.pack(side=LEFT, fill=BOTH, expand=True)

        self.debate_text = tb.Text(debate_frame, wrap=tk.WORD, state=tk.DISABLED)
        scrollbar = tb.Scrollbar(debate_frame, orient=tk.VERTICAL, command=self.debate_text.yview)
        self.debate_text.configure(yscrollcommand=scrollbar.set)
        self.debate_text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Right panel (memory + agents)
        right_frame = tb.Frame(content_frame, width=300)
        right_frame.pack(side=RIGHT, fill=BOTH, padx=(10, 0))

        # Agent panel
        agent_frame = tb.LabelFrame(right_frame, text="Agents", padding=5)
        agent_frame.pack(fill=X, pady=(0, 5))

        self.agent_labels: dict[str, tb.Label] = {}
        for role, agent in self.agents.items():
            label = tb.Label(agent_frame, text=f"{agent.color} ● {agent.name}",
                           font=("Consolas", 10), foreground=agent.color)
            label.pack(anchor=W, pady=2)
            self.agent_labels[role] = label

        # Memory tabs
        memory_frame = tb.LabelFrame(right_frame, text="Memory", padding=5)
        memory_frame.pack(fill=BOTH, expand=True)

        self.memory_tabs = tb.Notebook(memory_frame)
        self.memory_tabs.pack(fill=BOTH, expand=True)

        self.short_term_text = tb.Text(self.memory_tabs, wrap=tk.WORD, state=tk.DISABLED, height=8)
        self.mid_term_text = tb.Text(self.memory_tabs, wrap=tk.WORD, state=tk.DISABLED, height=8)
        self.long_term_text = tb.Text(self.memory_tabs, wrap=tk.WORD, state=tk.DISABLED, height=8)

        self.memory_tabs.add(self.short_term_text, text="Short-Term")
        self.memory_tabs.add(self.mid_term_text, text="Mid-Term")
        self.memory_tabs.add(self.long_term_text, text="Long-Term")

    def _load_models(self) -> None:
        """Load available models from LM Studio."""
        try:
            models = self.llm.get_models()
            if models:
                # Update router with available models
                self.router.clear_pool()
                for model_id in models:
                    self.router.add_model(model_id)

                # Connect router to LLM client
                self.llm._router = self.router

                # Update settings view with models
                if hasattr(self, 'settings_view'):
                    self.settings_view._update_model_combos()

                logger.info("Router initialized with %d models", len(models))
        except Exception as exc:
            logger.warning("Could not load models: %s", exc)

    def _reload_agents_from_config(self) -> None:
        """Reload agents based on current config (called after settings save)."""
        try:
            # Update router with current method and model pool
            self.router.set_method(self.config.router.method)

            # Update router pool based on checkboxes
            if hasattr(self, 'settings_view') and hasattr(self.settings_view, 'model_pool_checkboxes'):
                self.router.clear_pool()
                for model_id, var in self.settings_view.model_pool_checkboxes.items():
                    if var.get():
                        self.router.add_model(model_id)

            # Re-initialize agents with updated config
            self.agents = {}
            for role in ["existentialist", "stoic", "nihilist", "spiritual", "skeptic", "pragmatist"]:
                agent_class_map = {
                    "existentialist": ExistentialistAgent,
                    "stoic": StoicAgent,
                    "nihilist": NihilistAgent,
                    "spiritual": SpiritualAgent,
                    "skeptic": SkepticAgent,
                    "pragmatist": PragmatistAgent,
                }
                agent_class = agent_class_map.get(role)
                if agent_class:
                    persona_config = self.config.personas.get(role)
                    model = getattr(self.config.models, role, "")
                    if persona_config and persona_config.system_prompt:
                        from ..agents.base_agent import AgentConfig
                        config = AgentConfig(
                            role=role,
                            name=persona_config.name or role.capitalize(),
                            system_prompt=persona_config.system_prompt,
                            model=model,
                            color=persona_config.color,
                        )
                        agent = agent_class.__new__(agent_class)
                        agent.config = config
                        agent._response_history = []
                        agent._arguments_expressed = []
                        self.agents[role] = agent
                    else:
                        self.agents[role] = agent_class(model)

            self.moderator = ModeratorAgent(model=self.config.models.moderator)

            # Re-register with engine
            for agent in self.agents.values():
                self.engine.register_agent(agent)
            self.engine.register_moderator(self.moderator)

            logger.info("Agents reloaded from config")
            # Update labels to reflect new models
            self._update_agent_labels()
            # Update router status display
            self._update_router_status()
        except Exception as exc:
            logger.error("Error reloading agents: %s", exc)

    def _update_agent_labels(self) -> None:
        """Update agent labels to show current model names."""
        for role, agent in self.agents.items():
            if role in self.agent_labels:
                model_info = agent.config.model or "(no model)"
                label_text = f"{agent.color} ● {agent.name} [{model_info[:20]}...]"
                self.agent_labels[role].config(text=label_text)

    def _update_router_status(self) -> None:
        """Update router status labels in the UI."""
        if hasattr(self, 'settings_view') and hasattr(self.settings_view, 'router_status_label'):
            summary = self.router.get_pool_summary()
            method = summary.get("method", "unknown")
            model_count = len(summary.get("models", {}))
            self.settings_view.router_status_label.config(
                text=f"Router: {method} ({model_count} models)"
            )

            # Update last selected model label if available
            # This would need to be updated during debate

    def _start_debate(self) -> None:
        """Start the debate."""
        try:
            # Update config from UI (settings are saved via SettingsView)
            logger.info("Starting debate with config: URL=%s, temp=%.2f, tokens=%d",
                       self.config.lm_studio.base_url,
                       self.config.debate.temperature,
                       self.config.debate.max_tokens)

            success = self.engine.start_debate()
            if success:
                self._update_status("Running")
                logger.info("Debate started successfully")
            else:
                self._update_status("Failed to start")
                logger.error("start_debate() returned False")
        except Exception as exc:
            logger.error("Error starting debate: %s", exc, exc_info=True)
            self._update_status(f"Error: {str(exc)[:50]}")

    def _pause_debate(self) -> None:
        """Pause the debate."""
        try:
            self.engine.pause_debate()
            self._update_status("Paused")
        except Exception as exc:
            logger.error("Error pausing debate: %s", exc)
            self._update_status(f"Error: {str(exc)[:50]}")

    def _stop_debate(self) -> None:
        """Stop the debate and save transcript."""
        try:
            self.engine.stop_debate()
            self._save_current_debate()
            self._update_status("Stopped")
        except Exception as exc:
            logger.error("Error stopping debate: %s", exc)
            self._update_status(f"Error: {str(exc)[:50]}")

    def _save_current_debate(self) -> None:
        """Save the current debate transcript to storage."""
        if not hasattr(self, 'engine') or not self.engine or not hasattr(self.engine, '_debate_id'):
            return

        debate_id = self.engine._debate_id
        turns = self.engine.db.turn_repo.get_turns(debate_id)

        if not turns:
            logger.info("No turns to save for debate %d", debate_id)
            return

        try:
            filepath = self.debate_saver.save_debate(
                topic=self.config.debate.topic,
                turns=turns,
                debate_id=debate_id,
                status="finished"
            )
            logger.info("Debate saved to: %s", filepath)
            self._update_status(f"Saved: {Path(filepath).name}")
        except Exception as exc:
            logger.error("Error saving debate: %s", exc)

    def _on_debate_update(self, update) -> None:
        """Handle debate engine updates and refresh UI."""
        # Update status label
        state = update.state
        if hasattr(state, 'value'):
            status_map = {
                "idle": "Idle",
                "running": "Running",
                "paused": "Paused",
                "stopped": "Stopped",
                "error": "Error",
            }
            self._update_status(status_map.get(state.value, str(state)))
        else:
            self._update_status(str(update.state))

        # Update turn counter
        if update.stats and 'turn_id' in update.stats:
            self.turn_label.config(text=f"Turns: {update.stats['turn_id']}")

        # Update debate transcript
        if update.turn:
            self.debate_text.config(state=tk.NORMAL)
            self.debate_text.insert(tk.END, "\n" + "=" * 60 + "\n")
            # Use turn_id for display (1-based), not round_num
            turn_num = update.turn.turn_id
            self.debate_text.insert(tk.END, f"\nTURN {turn_num}\n\n")
            if update.turn.moderator_question:
                self.debate_text.insert(tk.END, "MODERATOR\n\n")
                self.debate_text.insert(tk.END, f"Challenge: {update.turn.moderator_question}\n\n")
                if update.turn.moderator_reason:
                    self.debate_text.insert(tk.END, f"Reason: {update.turn.moderator_reason}\n\n")
                self.debate_text.insert(tk.END, "-" * 60 + "\n\n")
            self.debate_text.insert(tk.END, f"{update.turn.speaker}\n\n")
            self.debate_text.insert(tk.END, update.turn.response)
            self.debate_text.insert(tk.END, "\n" + "=" * 60)
            self.debate_text.config(state=tk.DISABLED)
            self.debate_text.see(tk.END)

        # Update memory views
        if update.memory:
            try:
                if update.memory.event_type == "short_term":
                    self.short_term_text.config(state=tk.NORMAL)
                    self.short_term_text.delete(1.0, tk.END)
                    self.short_term_text.insert(tk.END, update.memory.details)
                    self.short_term_text.config(state=tk.DISABLED)
                elif update.memory.event_type == "mid_term":
                    self.mid_term_text.config(state=tk.NORMAL)
                    self.mid_term_text.delete(1.0, tk.END)
                    self.mid_term_text.insert(tk.END, update.memory.details)
                    self.mid_term_text.config(state=tk.DISABLED)
                elif update.memory.event_type == "long_term":
                    self.long_term_text.config(state=tk.NORMAL)
                    self.long_term_text.delete(1.0, tk.END)
                    self.long_term_text.insert(tk.END, update.memory.details)
                    self.long_term_text.config(state=tk.DISABLED)
            except Exception as exc:
                logger.error("Memory update error: %s", exc)

    def _update_status(self, status: str) -> None:
        """Update the status label."""
        self.status_label.config(text=f"Status: {status}")

    def _on_closing(self) -> None:
        """Handle window close."""
        self.engine.stop_debate()
        self.destroy()
