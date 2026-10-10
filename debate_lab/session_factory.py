"""DebateSessionFactory — convert a RoleTemplate + run config into the EXISTING DebateEngine.

This is the thin Debate Lab integration layer (spec §7): it never creates or
replaces an engine. The output is the existing
``philosophical_council.core.debate_engine.DebateEngine`` fully configured from
the template, plus an immutable provenance snapshot.

Responsibilities (spec §7):
1. resolve template
2. validate debate compatibility (controlled error BEFORE engine construction)
3. identify moderator
4. create participant agents from RoleSpecs (persona-layered or generic)
5. layer prompts/personas correctly (ROLE != PERSONA, kept distinguishable)
6. apply configured exact model overrides (role_models)
7. configure dynamic model routing (ModelRouter over the configured pool)
8. configure debate memory
9. configure DebateConfig
10. register participants + moderator
11. return DebateEngine + provenance snapshot

The factory does NOT execute the debate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DebateLabConfig
from .validation import (
    TEMPLATE_INVALID_FOR_DEBATE,
    TemplateInvalidForDebate,
    validate_debate_template,
)


@dataclass
class DebateSession:
    """A fully configured DebateEngine + immutable provenance snapshot."""

    engine: Any
    provenance: Dict[str, Any]
    db_path: str = ""


class DebateSessionFactory:
    """Builds existing DebateEngine sessions from DebateLabConfig + RoleTemplate."""

    def __init__(
        self,
        llm_client: Any = None,
        db_path: Optional[str] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self._llm_client = llm_client   # injected stub (tests) — no network
        self._db_path = db_path         # sqlite location (tests -> tmp_path)
        self._base_dir = base_dir       # debate_lab_runs root for default DB path

    # ── public ───────────────────────────────────────────────────────────
    def build(self, config: DebateLabConfig) -> DebateSession:
        """Build a fully configured existing DebateEngine (no execution)."""
        tpl = self._resolve_template(config.template_id)
        validate_debate_template(tpl)
        self._ensure_debate_executor(tpl)

        from philosophical_council.config import Config, DebateConfig
        from philosophical_council.core.debate_engine import DebateEngine

        llm, llm_available, llm_error, models = self._build_llm(config)

        debate = DebateConfig(
            topic=config.topic,
            temperature=float(config.temperature),
            max_tokens=int(config.participant_max_tokens),
            moderator_max_tokens=int(config.moderator_max_tokens),
            philosopher_max_tokens=int(config.participant_max_tokens),
            max_continuations=int(config.max_continuations),
            short_term_turns=int(config.short_term_turns),
            mid_term_interval=int(config.mid_term_interval),
            long_term_interval=int(config.long_term_interval),
        )
        full_config = Config(debate=debate)

        db_path = self._resolve_db_path(config)
        from philosophical_council.database.database import Database
        db = Database(db_path)

        engine = DebateEngine(full_config, db, llm)

        personas = self._load_personas()
        contract = list(tpl.response_contract or [])
        shared_context = str(tpl.shared_context or "")
        effective_prompts: Dict[str, Dict[str, Any]] = {}
        participant_names: List[str] = []
        for spec in tpl.roles:
            if spec.role_id == "moderator":
                continue
            agent, system_prompt, source = self._build_participant(
                spec, config, personas, contract, shared_context)
            engine.register_agent(agent)
            participant_names.append(agent.name)
            effective_prompts[spec.role_id] = {
                "prompt_hash": _sha256(system_prompt),
                "source": source,
                "persona": spec.default_persona or "",
                "model_slot": spec.model_slot or "",
            }

        moderator_model = config.role_models.get("moderator", "")
        from philosophical_council.agents.moderator import ModeratorAgent
        moderator = ModeratorAgent(model=moderator_model, allowed_speakers=participant_names,
                                   shared_context=shared_context)
        engine.register_moderator(moderator)
        engine.set_valid_speakers(participant_names)
        engine.set_model_routing_method(config.model_routing_method)
        # §78: visible response presentation contract for section parsing.
        engine.set_response_contract(contract)

        engine.short_term_memory = self._make_short_term(config.short_term_turns)
        engine.mid_term_memory = self._make_mid_term()
        engine.long_term_memory = self._make_long_term()
        engine.consolidator = self._make_consolidator(
            engine.mid_term_memory, engine.long_term_memory)

        # Wire the REAL repetition policy from config (no phantom controls).
        engine.argument_state.prevent_repetition = bool(config.prevent_repetition)
        engine.argument_state.max_consecutive_same_speaker = int(
            config.max_consecutive_same_speaker)

        provenance = self._build_provenance(
            config, tpl, personas, effective_prompts,
            llm_available, llm_error, models, db_path,
        )
        return DebateSession(engine=engine, provenance=provenance, db_path=db_path)

    # ── template resolution ──────────────────────────────────────────────
    def _resolve_template(self, template_id: str):
        from role_templates.registry import get_registry
        tpl = get_registry().get_template(template_id)
        if tpl is None:
            raise TemplateInvalidForDebate(
                TEMPLATE_INVALID_FOR_DEBATE,
                f"DEBATE_TEMPLATE_INCOMPATIBLE: unknown role template "
                f"'{template_id}'.",
            )
        return tpl

    def _ensure_debate_executor(self, tpl) -> None:
        et = tpl.executor_type or ""
        if et not in ("debate", "philosophical_debate"):
            raise TemplateInvalidForDebate(
                TEMPLATE_INVALID_FOR_DEBATE,
                f"DEBATE_TEMPLATE_INCOMPATIBLE: template '{tpl.template_id}' is of "
                f"executor type '{et}' — it does not dispatch to the Debate "
                "executor. No fallback agents were used.",
            )

    # ── collaborators ────────────────────────────────────────────────────
    def _build_llm(self, config: DebateLabConfig):
        """Build/obtain the LLM client + wire the dynamic model router."""
        if self._llm_client is not None:
            llm = self._llm_client
            llm_available = True
            llm_error = None
            try:
                models = list(getattr(llm, "get_models", lambda: [])() or [])
            except Exception:  # pragma: no cover
                models = list(getattr(llm, "_models", []) or [])
        else:
            from code_lab.multiagent import probe_llm, resolve_llm_credentials
            from philosophical_council.llm.client import LLMClient
            base_url, api_key = resolve_llm_credentials()
            probe = probe_llm(base_url, api_key)
            llm_available = bool(probe.get("available"))
            llm_error = probe.get("error")
            models = list(probe.get("models", []) or []) if llm_available else []
            llm = LLMClient(
                base_url=base_url or "http://localhost:1234/v1",
                api_key=api_key,
            )

        # Dynamic model routing: ModelRouter over the CONFIGURED pool. An empty
        # pool -> no router -> the client's backend_default fallback (honest).
        pool = [m for m in (config.model_pool or []) if m]
        if pool:
            from philosophical_council.core.router import ModelRouter
            router = ModelRouter(available_models=pool)
            router.set_method(config.model_routing_method)
            llm._router = router
        else:
            llm._router = None

        return llm, llm_available, llm_error, models

    def _load_personas(self) -> Dict[str, Any]:
        try:
            from philosophical_council.config import Config
            return dict(Config.default().personas or {})
        except Exception:  # pragma: no cover
            return {}

    def _build_participant(self, spec, config: DebateLabConfig, personas, contract,
                           shared_context: str = ""):
        """Build one ConfigurableDebateAgent from a RoleSpec.

        Prompt layering (spec §8): if ``default_persona`` points to a configured
        existing Life_mean persona, REUSE that persona's system prompt verbatim
        (never degrade the historical philosophical prompts). Otherwise build
        the generic layered prompt from ROLE + PERSONA + OBJECTIVES +
        CONSTRAINTS + expected_output (+ the template's visible response
        presentation contract, §78). The template's SHARED CONTEXT (global
        scientific rules) is prepended to every participant prompt.
        """
        from philosophical_council.agents.configurable import ConfigurableDebateAgent

        model = config.role_models.get(spec.role_id, "") or ""
        system_prompt = ""
        source = "layered"
        if spec.default_persona:
            persona = personas.get(spec.default_persona)
            if persona is not None and getattr(persona, "system_prompt", "").strip():
                system_prompt = persona.system_prompt
                source = "persona"
        if not system_prompt.strip():
            system_prompt = self._layered_prompt(spec, contract)
        if shared_context and shared_context.strip():
            system_prompt = (f"=== TEMPLATE SHARED CONTEXT ===\n{shared_context.strip()}\n"
                             f"\n--- YOUR ROLE ---\n{system_prompt}")

        name = spec.name or spec.role_id.replace("_", " ").title()
        agent = ConfigurableDebateAgent(
            role_id=spec.role_id,
            name=name,
            system_prompt=system_prompt,
            model=model,
            persona=spec.default_persona or "",
            objectives=list(spec.objectives or []),
            constraints=list(spec.constraints or []),
            expected_output=spec.expected_output or "",
        )
        agent._prompt_source = source
        return agent, system_prompt, source

    @staticmethod
    def _layered_prompt(spec, contract=None) -> str:
        """Generic layered instructions for a non-persona role (spec §8)."""
        lines = [f"ROLE: {spec.name or spec.role_id}"]
        if spec.default_persona:
            lines.append(f"PERSONA: {spec.default_persona}")
        if spec.instructions_template:
            lines.append(f"\n{spec.instructions_template}")
        if spec.objectives:
            lines.append("\nOBJECTIVES:")
            lines += [f"- {o}" for o in spec.objectives]
        if spec.constraints:
            lines.append("\nCONSTRAINTS:")
            lines += [f"- {c}" for c in spec.constraints]
        if spec.expected_output:
            lines.append(f"\nEXPECTED OUTPUT:\n{spec.expected_output}")
        if contract:
            lines.append("\nRESPONSE CONTRACT (visible public communication — never "
                         "hidden chain-of-thought):\n"
                         "Organize your response as labeled sections where it "
                         "serves the science. The team reads these directly.")
            for c in contract:
                lines.append(f"- {c}:")
        return "\n".join(lines)

    # ── memory / persistence ─────────────────────────────────────────────
    def _make_short_term(self, capacity: int):
        from philosophical_council.memory.short_term import ShortTermMemory
        return ShortTermMemory(capacity=max(1, int(capacity)))

    def _make_mid_term(self):
        from philosophical_council.memory.mid_term import MidTermMemory
        return MidTermMemory()

    def _make_long_term(self):
        from philosophical_council.memory.long_term import LongTermMemory
        return LongTermMemory()

    def _make_consolidator(self, mid, long):
        from philosophical_council.memory.consolidation import MemoryConsolidator
        return MemoryConsolidator(mid, long)

    def _resolve_db_path(self, config: DebateLabConfig) -> str:
        if self._db_path:
            return self._db_path
        base = Path(self._base_dir) if self._base_dir else (Path.cwd() / "debate_lab_runs")
        return str(base / config.run_id / "debate.db")

    # ── provenance ───────────────────────────────────────────────────────
    def _build_provenance(self, config, tpl, personas, effective_prompts,
                          llm_available, llm_error, models, db_path) -> Dict[str, Any]:
        settings_snapshot = None
        try:
            from experiments.settings import build_settings_snapshot
            settings_snapshot = build_settings_snapshot()
        except Exception:  # pragma: no cover
            settings_snapshot = None
        return {
            "run_id": config.run_id,
            "created_at": config.created_at,
            "topic": config.topic,
            "run_name": config.run_name,
            "template_id": tpl.template_id,
            "template_version": tpl.version,
            "template_hash": tpl.content_hash(),
            "executor_type": tpl.executor_type,
            "response_contract": list(tpl.response_contract or []),
            "shared_context_hash": _sha256(tpl.shared_context or "") if (tpl.shared_context or "").strip() else None,
            "effective_roles": [
                {"role_id": r.role_id, "name": r.name,
                 "default_persona": r.default_persona or "",
                 "model_slot": r.model_slot or ""}
                for r in tpl.roles
            ],
            "effective_role_prompts": effective_prompts,
            "effective_personas": {
                rid: {"name": p.name, "color": p.color, "role_id": p.role_id}
                for rid, p in personas.items()
            },
            "configured_role_models": dict(config.role_models),
            "configured_model_pool": list(config.model_pool),
            "model_routing_method": config.model_routing_method,
            "speaker_selection_mode": config.speaker_selection_mode,
            "temperature": config.temperature,
            "moderator_max_tokens": config.moderator_max_tokens,
            "participant_max_tokens": config.participant_max_tokens,
            "max_continuations": config.max_continuations,
            "max_turns": config.max_turns,
            "memory_settings": {
                "short_term_turns": config.short_term_turns,
                "mid_term_interval": config.mid_term_interval,
                "long_term_interval": config.long_term_interval,
            },
            "repetition_policy": {
                "prevent_repetition": config.prevent_repetition,
                "max_consecutive_same_speaker": config.max_consecutive_same_speaker,
            },
            "settings_snapshot": settings_snapshot,
            "llm_available": llm_available,
            "llm_error": llm_error,
            "available_models": models,
            "db_path": db_path,
        }


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
