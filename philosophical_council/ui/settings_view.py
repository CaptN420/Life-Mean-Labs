"""Settings view for the GUI."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from typing import Any, Optional

import ttkbootstrap as tb
from ttkbootstrap.constants import *

from ..config import Config, ModelInfo, PersonaConfig, save_config

logger = logging.getLogger(__name__)


class SettingsView(tb.Frame):
    """Settings panel for configuring the application."""

    def __init__(self, parent: tb.Frame, config: Config, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.config = config
        self._models: dict[str, ModelInfo] = {}  # model_id -> ModelInfo
        self._build_ui()
        # Fetch models in background
        threading.Thread(target=self._fetch_models, daemon=True).start()

    def _fetch_models(self) -> None:
        """Fetch available models from LM Studio."""
        try:
            from ..llm.client import LLMClient
            client = LLMClient(
                base_url=self.config.lm_studio.base_url,
                api_key=self.config.lm_studio.api_key or "lm-studio",
            )
            model_ids = client.get_models()
            # Build ModelInfo from raw data (no architecture info available via API)
            self._models = {mid: ModelInfo(id=mid, vram_estimate_gb=0.0) for mid in model_ids}
            logger.info("Fetched %d models from LM Studio", len(model_ids))
        except Exception as exc:
            logger.warning("Failed to fetch models: %s", exc)
            self._models = {}

    def _build_ui(self) -> None:
        """Build the settings UI with scrollable area."""
        # Create canvas for scrolling
        self.canvas = tb.Canvas(self)
        scrollbar = tb.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = tb.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor=NW)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Bind mouse wheel to scroll
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(-1, "units"))

        self.canvas.pack(side=tk.LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=Y)

        # LM Studio settings
        lm_frame = tb.LabelFrame(self.scrollable_frame, text="LM Studio", padding=10)
        lm_frame.pack(fill=X, pady=(0, 10))

        tb.Label(lm_frame, text="Base URL:").grid(row=0, column=0, sticky=W, pady=5)
        self.url_entry = tb.Entry(lm_frame, width=50)
        self.url_entry.insert(0, self.config.lm_studio.base_url)
        self.url_entry.grid(row=0, column=1, padx=5)

        tb.Label(lm_frame, text="API Key:").grid(row=1, column=0, sticky=W, pady=5)
        self.api_key_entry = tb.Entry(lm_frame, width=50)
        self.api_key_entry.insert(0, self.config.lm_studio.api_key)
        self.api_key_entry.grid(row=1, column=1, padx=5)

        # Refresh models button
        refresh_btn = tb.Button(lm_frame, text="Refresh Models", command=self._refresh_models)
        refresh_btn.grid(row=2, column=0, columnspan=2, pady=10)

        # Debate settings
        debate_frame = tb.LabelFrame(self.scrollable_frame, text="Debate", padding=10)
        debate_frame.pack(fill=X, pady=(0, 10))

        tb.Label(debate_frame, text="Topic:").grid(row=0, column=0, sticky=W, pady=5)
        self.topic_entry = tb.Entry(debate_frame, width=50)
        self.topic_entry.insert(0, self.config.debate.topic)
        self.topic_entry.grid(row=0, column=1, padx=5)

        tb.Label(debate_frame, text="Temperature:").grid(row=1, column=0, sticky=W, pady=5)
        temp_values = [f"{i/10:.1f}" for i in range(0, 21)]
        self.temp_combo = tb.Combobox(debate_frame, width=10, values=temp_values, state="readonly")
        self.temp_combo.set(f"{self.config.debate.temperature:.1f}")
        self.temp_combo.grid(row=1, column=1, sticky=W, padx=5)

        tb.Label(debate_frame, text="Max Tokens:").grid(row=2, column=0, sticky=W, pady=5)
        self.tokens_combo = tb.Combobox(debate_frame, width=10,
            values=["256", "512", "700", "1000", "1500", "2000", "3000", "4000"], state="readonly")
        self.tokens_combo.set(str(self.config.debate.max_tokens))
        self.tokens_combo.grid(row=2, column=1, sticky=W, padx=5)

        tb.Label(debate_frame, text="Moderator Max Tokens:").grid(row=3, column=0, sticky=W, pady=5)
        self.mod_tokens_combo = tb.Combobox(debate_frame, width=10,
            values=["500", "700", "1000", "1500", "2000"], state="readonly")
        self.mod_tokens_combo.set(str(self.config.debate.moderator_max_tokens))
        self.mod_tokens_combo.grid(row=3, column=1, sticky=W, padx=5)

        # MODEL POOL SECTION (clean separate section)
        self.pool_frame = tb.LabelFrame(self.scrollable_frame, text="Model Pool", padding=10)
        self.pool_frame.pack(fill=X, pady=(0, 10))

        # VRAM info label
        self.vram_info_label = tb.Label(self.pool_frame, text="VRAM estimates will appear here after loading models")
        self.vram_info_label.grid(row=0, column=0, columnspan=2, sticky=W, pady=5)

        # Model pool checkboxes (for dynamic routing)
        tb.Label(self.pool_frame, text="Models available for dynamic routing (check to include):").grid(
            row=1, column=0, columnspan=2, sticky=W, pady=5
        )
        self.model_pool_checkboxes: dict[str, tk.BooleanVar] = {}
        self._build_model_pool_checkboxes()

        # AGENT MODELS SECTION (separate from pool)
        self.agent_frame = tb.LabelFrame(self.scrollable_frame, text="Agent Model Selection", padding=10)
        self.agent_frame.pack(fill=X, pady=(0, 10))

        tb.Label(self.agent_frame, text="Select a fixed model or 'dynamic' for each agent/persona:").grid(
            row=0, column=0, columnspan=2, sticky=W, pady=5
        )

        # Per-agent model selectors - dynamic based on personas
        self.agent_combos: dict[str, tb.Combobox] = {}
        self._build_agent_combos()

        # Add moderator model selector
        mod_row = len(self.config.personas) + 1
        tb.Label(self.agent_frame, text="Moderator:").grid(
            row=mod_row, column=0, sticky=W, pady=5
        )
        self.moderator_combo = tb.Combobox(self.agent_frame, width=40, state="readonly")
        self.moderator_combo.grid(row=mod_row, column=1, padx=5, pady=5)
        current_mod_model = getattr(self.config.models, 'moderator', "")
        self.moderator_combo.set("dynamic" if not current_mod_model else current_mod_model)

        # Populate with models after a short delay (models may already be fetched)
        self.after(500, self._update_model_combos)

        # Router configuration
        router_frame = tb.LabelFrame(self.scrollable_frame, text="Router / Moderator", padding=10)
        router_frame.pack(fill=X, pady=(0, 10))

        tb.Label(router_frame, text="Routing Method:").grid(row=0, column=0, sticky=W, pady=5)
        self.router_method_combo = tb.Combobox(
            router_frame, width=40,
            values=["context_aware", "round_robin", "weighted", "random"],
            state="readonly"
        )
        self.router_method_combo.set(self.config.router.method)
        self.router_method_combo.grid(row=0, column=1, padx=5, pady=5)

        # Router status label
        self.router_status_label = tb.Label(router_frame, text="Router: Not initialized")
        self.router_status_label.grid(row=1, column=0, columnspan=2, sticky=W, pady=5)

        tb.Label(router_frame, text="Last Selected Model:").grid(row=2, column=0, sticky=W, pady=5)
        self.last_model_label = tb.Label(router_frame, text="N/A")
        self.last_model_label.grid(row=2, column=1, padx=5, pady=5)

        self.prevent_repetition_var = tk.BooleanVar(value=self.config.router.prevent_repetition)
        self.prevent_repetition_check = tb.Checkbutton(
            router_frame,
            text="Prevent Repetition",
            variable=self.prevent_repetition_var
        )
        self.prevent_repetition_check.grid(row=3, column=0, columnspan=2, sticky=W, pady=5)

        tb.Label(router_frame, text="Max Consecutive Same Speaker:").grid(row=4, column=0, sticky=W, pady=5)
        self.max_consecutive_spinbox = tb.Spinbox(
            router_frame, width=10, from_=1, to=5,
            state="readonly",
            values=[str(i) for i in range(1, 6)]
        )
        self.max_consecutive_spinbox.set(self.config.router.max_consecutive_same_speaker)
        self.max_consecutive_spinbox.grid(row=4, column=1, padx=5, pady=5)

        # Persona management
        self.personas_frame = tb.LabelFrame(self.scrollable_frame, text="Personas", padding=10)
        self.personas_frame.pack(fill=X, pady=(0, 10))

        # Buttons for adding/removing personas
        btn_row = tb.Frame(self.personas_frame)
        btn_row.grid(row=0, column=0, columnspan=2, sticky=W, pady=5)

        add_btn = tb.Button(btn_row, text="+ Add Persona", command=self._add_persona_dialog)
        add_btn.pack(side=LEFT, padx=5)

        # Persona editors - dynamic based on config
        self.persona_editors: dict[str, dict[str, Any]] = {}
        self._build_persona_editors()

        # Memory settings
        memory_frame = tb.LabelFrame(self.scrollable_frame, text="Memory", padding=10)
        memory_frame.pack(fill=X, pady=(0, 10))

        tb.Label(memory_frame, text="Short-term turns:").grid(row=0, column=0, sticky=W, pady=5)
        self.short_term_combo = tb.Combobox(memory_frame, width=10,
            values=["10", "20", "30", "50", "100"], state="readonly")
        self.short_term_combo.set(str(self.config.debate.short_term_turns))
        self.short_term_combo.grid(row=0, column=1, sticky=W, padx=5)

        tb.Label(memory_frame, text="Mid-term interval:").grid(row=1, column=0, sticky=W, pady=5)
        self.mid_term_interval_combo = tb.Combobox(memory_frame, width=10,
            values=["5", "10", "15", "20", "30"], state="readonly")
        self.mid_term_interval_combo.set(str(self.config.debate.mid_term_interval))
        self.mid_term_interval_combo.grid(row=1, column=1, sticky=W, padx=5)

        tb.Label(memory_frame, text="Long-term interval:").grid(row=2, column=0, sticky=W, pady=5)
        self.long_term_combo = tb.Combobox(memory_frame, width=10,
            values=["25", "50", "75", "100"], state="readonly")
        self.long_term_combo.set(str(self.config.debate.long_term_interval))
        self.long_term_combo.grid(row=2, column=1, sticky=W, padx=5)

        # Buttons frame
        btn_frame = tb.Frame(self.scrollable_frame)
        btn_frame.pack(pady=(10, 0))

        # Save button
        save_btn = tb.Button(btn_frame, text="Save Settings", command=self._save_settings)
        save_btn.pack(side=LEFT, padx=5)

        # Run button
        run_btn = tb.Button(btn_frame, text="Run Debate", command=self._run_debate, bootstyle=SUCCESS)
        run_btn.pack(side=LEFT, padx=5)

    def _build_model_pool_checkboxes(self) -> None:
        """Build checkboxes for model pool selection."""
        # Clear existing checkboxes
        for widget in list(self.model_pool_checkboxes.values()):
            try:
                widget.destroy()
            except Exception:
                pass
        self.model_pool_checkboxes.clear()

        # Get model IDs and create checkboxes
        model_ids = list(self._models.keys()) if self._models else []
        row = 2
        for i, model_id in enumerate(model_ids):
            col = (i % 3) * 2  # 3 columns
            var = tk.BooleanVar(value=True)  # Default to checked
            self.model_pool_checkboxes[model_id] = var

            cb = tb.Checkbutton(
                self.pool_frame,
                text=model_id[:40] + ("..." if len(model_id) > 40 else ""),
                variable=var
            )
            cb.grid(row=row, column=col, sticky=W, pady=2)
            row += 1

    def _build_agent_combos(self) -> None:
        """Build comboboxes for agent model selection based on current personas."""
        # Clear existing combos
        for widget in list(self.agent_combos.values()):
            try:
                widget.destroy()
            except Exception:
                pass
        self.agent_combos.clear()

        row = 1
        for role in self.config.personas.keys():
            persona = self.config.personas[role]
            # Label
            tb.Label(self.agent_frame, text=f"{persona.name} ({role}):").grid(
                row=row, column=0, sticky=W, pady=2
            )
            # Combobox - include "dynamic" option for automatic model selection
            combo = tb.Combobox(self.agent_frame, width=40, state="readonly")
            combo.grid(row=row, column=1, padx=5, pady=2)
            # Set current model or "dynamic" if no model selected
            current_model = getattr(self.config.models, role, "")
            combo.set("dynamic" if not current_model else current_model)
            self.agent_combos[role] = combo
            row += 1

        # Populate with models after a short delay (models may already be fetched)
        self.after(500, self._update_model_combos)

    def _build_persona_editors(self) -> None:
        """Build editors for each persona based on current config."""
        # Clear existing editors
        for editors in list(self.persona_editors.values()):
            try:
                for w in editors.values():
                    w.destroy()
            except Exception:
                pass
        self.persona_editors.clear()

        roles = list(self.config.personas.keys())
        for i, role in enumerate(roles):
            row = i * 3 + 1
            persona = self.config.personas[role]
            # Role label
            tb.Label(self.personas_frame, text=f"{persona.name} ({role}):").grid(
                row=row, column=0, sticky=W, pady=2
            )
            # Name entry
            name_entry = tb.Entry(self.personas_frame, width=40)
            name_entry.insert(0, persona.name)
            name_entry.grid(row=row, column=1, padx=5, pady=2)
            # System prompt entry (multiline)
            prompt_text = tb.Text(self.personas_frame, width=60, height=4)
            prompt_text.insert("1.0", persona.system_prompt)
            prompt_text.grid(row=row + 1, column=0, columnspan=2, pady=2)

            self.persona_editors[role] = {
                "name_entry": name_entry,
                "prompt_text": prompt_text,
            }

    def _refresh_models(self) -> None:
        """Refresh the model list from LM Studio."""
        threading.Thread(target=self._fetch_models, daemon=True).start()
        # Update UI after fetch
        self.after(1000, self._update_model_combos)

    def _update_model_combos(self) -> None:
        """Update comboboxes with fetched models and show VRAM info."""
        # Always include "dynamic" option
        model_ids = list(self._models.keys()) if self._models else []

        # Update VRAM info label
        total_vram = sum(m.vram_estimate_gb for m in self._models.values())
        self.vram_info_label.config(
            text=f"Available models: {len(model_ids)} | Total VRAM capacity: {total_vram:.1f} GB"
        )

        # Update agent comboboxes with "dynamic" + model list
        for role, combo in self.agent_combos.items():
            current_model = getattr(self.config.models, role, "")
            if not current_model:
                combo['values'] = ["dynamic"] + model_ids
                combo.set("dynamic")
            else:
                combo['values'] = [current_model] + ["dynamic"] + [m for m in model_ids if m != current_model]
                # Ensure current selection is valid
                if current_model not in combo['values']:
                    combo.set("dynamic")

        # Update model pool checkboxes
        self._build_model_pool_checkboxes()

        # Update moderator combobox
        current_mod_model = getattr(self.config.models, 'moderator', "")
        if not current_mod_model:
            self.moderator_combo['values'] = ["dynamic"] + model_ids
            self.moderator_combo.set("dynamic")
        else:
            self.moderator_combo['values'] = [current_mod_model] + ["dynamic"] + [m for m in model_ids if m != current_mod_model]
            if current_mod_model not in self.moderator_combo['values']:
                self.moderator_combo.set("dynamic")

    def _add_persona_dialog(self) -> None:
        """Show dialog to add a new persona."""
        dialog = tb.Toplevel(self)
        dialog.title("Add Persona")
        dialog.geometry("400x300")

        tb.Label(dialog, text="Persona Name:").pack(anchor=W, pady=5)
        name_entry = tb.Entry(dialog, width=40)
        name_entry.pack(pady=5)

        tb.Label(dialog, text="System Prompt:").pack(anchor=W, pady=5)
        prompt_text = tb.Text(dialog, width=50, height=8)
        prompt_text.pack(pady=5)

        def save():
            name = name_entry.get().strip()
            prompt = prompt_text.get("1.0", tk.END).strip()
            if not name or not prompt:
                tb.messagebox.showerror("Error", "Name and prompt are required")
                return
            # Create new persona with unique role_id
            role_id = f"persona_{len(self.config.personas)}"
            self.config.personas[role_id] = PersonaConfig(
                name=name,
                color="#888888",
                system_prompt=prompt,
                role_id=role_id,
            )
            # Rebuild UI
            self._build_agent_combos()
            self._build_persona_editors()
            dialog.destroy()

        save_btn = tb.Button(dialog, text="Save", command=save)
        save_btn.pack(pady=10)

    def _save_settings(self) -> None:
        """Save settings to config."""
        self.config.lm_studio.base_url = self.url_entry.get()
        self.config.lm_studio.api_key = self.api_key_entry.get()
        self.config.debate.topic = self.topic_entry.get()
        self.config.debate.temperature = float(self.temp_combo.get())
        self.config.debate.max_tokens = int(self.tokens_combo.get())
        self.config.debate.moderator_max_tokens = int(self.mod_tokens_combo.get())
        self.config.debate.short_term_turns = int(self.short_term_combo.get())
        self.config.debate.mid_term_interval = int(self.mid_term_interval_combo.get())
        self.config.debate.long_term_interval = int(self.long_term_combo.get())

        # Save per-agent model selections (empty string means "dynamic")
        for role, combo in self.agent_combos.items():
            selected = combo.get().strip()
            if selected and selected != "dynamic":
                setattr(self.config.models, role, selected)
                logger.info("Saved model for %s: %s", role, selected)
            else:
                # Clear model selection - will use dynamic routing
                setattr(self.config.models, role, "")
                logger.info("Cleared model for %s (dynamic)", role)

        # Save moderator model selection
        mod_selected = self.moderator_combo.get().strip()
        if mod_selected and mod_selected != "dynamic":
            self.config.models.moderator = mod_selected
            logger.info("Saved model for moderator: %s", mod_selected)
        else:
            self.config.models.moderator = ""
            logger.info("Cleared model for moderator (dynamic)")

        # Save router settings
        self.config.router.method = self.router_method_combo.get()
        self.config.router.prevent_repetition = self.prevent_repetition_var.get()
        self.config.router.max_consecutive_same_speaker = int(self.max_consecutive_spinbox.get())

        # Save persona settings
        for role, editors in self.persona_editors.items():
            name = editors["name_entry"].get()
            prompt = editors["prompt_text"].get("1.0", tk.END).strip()
            if role not in self.config.personas:
                self.config.personas[role] = PersonaConfig(
                    name=name, color="#888888", system_prompt=prompt, role_id=role
                )
            else:
                self.config.personas[role].name = name
                self.config.personas[role].system_prompt = prompt

        save_config(self.config)
        logger.info("Settings saved")

        # Reload agents with new model selections
        self._reload_agents()

    def _reload_agents(self) -> None:
        """Reload agents with new config - delegates to parent app."""
        # Find parent window and call reload
        parent = self.master
        while parent and not hasattr(parent, '_reload_agents_from_config'):
            parent = parent.master if hasattr(parent, 'master') else None
        if parent and hasattr(parent, '_reload_agents_from_config'):
            parent._reload_agents_from_config()

    def _run_debate(self) -> None:
        """Trigger debate start from settings."""
        # Save settings first
        self._save_settings()
        # Emit event to parent window
        self.master.event_generate('<<RunDebate>>')
