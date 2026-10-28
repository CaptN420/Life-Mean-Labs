"""DebateExperimentRunner — engine for multi-agent debate experiments.

Configures and runs debates with configurable:
  - Number of agents
  - Debated question
  - Max rounds
  - Memory type (individual/shared)
  - Roles (imposed/free)
  - Model parameters
  - Global budget
  - Stopping criteria

Compares experimental conditions A/B/C using identical questions and models.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .debate_ledger import ArgumentLedger, DebateEvent, DebateEventType
from .models import Task

logger = logging.getLogger("Life_mean.Orchestrator.DebateExperiment")


# ── Experimental conditions ───────────────────────────────────────────────────


class DebateCondition(str, enum.Enum):
    """Experimental conditions for debate comparison."""
    INDEPENDENT_AGENTS = "independent_agents"       # A: No shared memory
    SHARED_MEMORY = "shared_memory"                  # B: Shared memory
    ADAPTIVE_RULES = "adaptive_rules"                # C: Shared memory + adaptive rules


# ── Experiment config ─────────────────────────────────────────────────────────


@dataclass
class DebateConfig:
    """Configuration for a debate experiment."""
    question: str
    num_agents: int = 3
    max_rounds: int = 5
    condition: DebateCondition = DebateCondition.INDEPENDENT_AGENTS
    memory_type: str = "individual"  # individual | shared
    roles_imposed: bool = True
    temperature: float = 0.3
    max_tokens: int = 1024
    token_budget: int = 8192
    timeout_seconds: float = 60.0
    stop_on_stagnation: bool = True
    stagnation_threshold: int = 2  # consecutive rounds with no progress

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question[:100],
            "num_agents": self.num_agents,
            "max_rounds": self.max_rounds,
            "condition": self.condition.value,
            "memory_type": self.memory_type,
            "roles_imposed": self.roles_imposed,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "token_budget": self.token_budget,
            "timeout_seconds": self.timeout_seconds,
            "stop_on_stagnation": self.stop_on_stagnation,
            "stagnation_threshold": self.stagnation_threshold,
        }


# ── Agent state ───────────────────────────────────────────────────────────────


@dataclass
class AgentState:
    """State for a single debate agent."""
    agent_id: str
    role: str = ""
    position: str = ""
    memory: List[str] = field(default_factory=list)
    tokens_consumed: int = 0
    arguments_count: int = 0


# ── Emergence measures ────────────────────────────────────────────────────────


@dataclass
class EmergenceMeasures:
    """Exploratory indicators of emergent behavior in a debate."""
    argument_diversity: float = 0.0          # Unique argument types / total
    novelty_score: float = 0.0               # New concepts per round
    position_stability: float = 0.0          # Ratio of stable positions
    specialization_index: float = 0.0        # Degree of role specialization
    convention_count: int = 0                # Spontaneous conventions observed
    disagreements_resolved: int = 0
    stagnation_rounds: int = 0
    total_rounds: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "argument_diversity": round(self.argument_diversity, 4),
            "novelty_score": round(self.novelty_score, 4),
            "position_stability": round(self.position_stability, 4),
            "specialization_index": round(self.specialization_index, 4),
            "convention_count": self.convention_count,
            "disagreements_resolved": self.disagreements_resolved,
            "stagnation_rounds": self.stagnation_rounds,
            "total_rounds": self.total_rounds,
        }


# ── Debate result ─────────────────────────────────────────────────────────────


@dataclass
class DebateResult:
    """Complete result of a debate experiment."""
    experiment_id: str
    condition: DebateCondition
    config: DebateConfig
    ledger: ArgumentLedger
    emergence_measures: EmergenceMeasures
    tokens_total: int = 0
    duration_seconds: float = 0.0
    success: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "condition": self.condition.value,
            "config": self.config.to_dict(),
            "ledger_summary": self.ledger.get_summary(),
            "emergence_measures": self.emergence_measures.to_dict(),
            "tokens_total": self.tokens_total,
            "duration_seconds": round(self.duration_seconds, 2),
            "success": self.success,
            "error": self.error,
        }


# ── DebateExperimentRunner ────────────────────────────────────────────────────


class DebateExperimentRunner:
    """Runs multi-agent debate experiments with emergence measurement.

    Supports conditions A (independent), B (shared memory), C (adaptive rules).
    Uses RealLLMExecutor for real model inference or injected stubs for testing.
    """

    # Role prompts for different agent types.
    ROLE_PROMPTS = {
        "advocate": "You are an ADVOCATE. Argue in favor of the proposition.",
        "skeptic": "You are a SKEPTIC. Challenge assumptions and raise objections.",
        "synthesizer": "You are a SYNTHESIZER. Find common ground and propose integrations.",
        "neutral_facilitator": "You are a NEUTRAL FACILITATOR. Ensure balanced discussion.",
    }

    def __init__(self, llm_executor: Optional[Callable] = None) -> None:
        self._llm_executor = llm_executor
        self._results: List[DebateResult] = []

    def run(
        self,
        config: DebateConfig,
        task: Optional[Task] = None,
    ) -> DebateResult:
        """Run a single debate experiment.

        Args:
            config: Debate configuration.
            task: Optional task context (for logging).

        Returns:
            DebateResult with full ledger and emergence measures.
        """
        experiment_id = f"debate_{int(time.time())}_{hash(config.question) % 0xFFFF:04x}"
        ledger = ArgumentLedger(debate_id=experiment_id)
        emergence = EmergenceMeasures()
        start_time = time.time()

        # Initialize agents.
        agents = self._init_agents(config)
        positions = {a.agent_id: "" for a in agents}

        # Run rounds.
        for round_num in range(1, config.max_rounds + 1):
            # Check stopping criteria.
            if config.stop_on_stagnation and self._is_stagnating(ledger, config.stagnation_threshold):
                logger.info("Stagnation detected at round %d; stopping", round_num)
                emergence.stagnation_rounds = config.max_rounds - round_num + 1
                break

            # Check budget.
            if self._check_budget(agents):
                logger.info("Budget exhausted at round %d; stopping")
                break

            # Execute round.
            round_result = self._execute_round(config, agents, ledger, round_num)
            if not round_result:
                break

            emergence.total_rounds = round_num

            # Update positions.
            for agent in agents:
                agent_args = [e for e in ledger.get_events_by_agent(agent.agent_id)
                              if e.event_type == DebateEventType.ARGUMENT]
                if agent_args:
                    positions[agent.agent_id] = agent_args[-1].content[:100]

            # Detect position changes.
            self._detect_position_changes(ledger, positions, agents)

        # Compute emergence measures.
        emergence = self._compute_emergence(ledger, emergence)

        # Calculate totals.
        tokens_total = sum(a.tokens_consumed for a in agents)
        duration = time.time() - start_time

        result = DebateResult(
            experiment_id=experiment_id,
            condition=config.condition,
            config=config,
            ledger=ledger,
            emergence_measures=emergence,
            tokens_total=tokens_total,
            duration_seconds=duration,
            success=True,
        )
        self._results.append(result)
        return result

    def run_condition(
        self,
        condition: DebateCondition,
        question: str,
        num_agents: int = 3,
        max_rounds: int = 5,
    ) -> DebateResult:
        """Run a debate under a specific experimental condition."""
        config = DebateConfig(
            question=question,
            num_agents=num_agents,
            max_rounds=max_rounds,
            condition=condition,
            memory_type="shared" if condition in (DebateCondition.SHARED_MEMORY, DebateCondition.ADAPTIVE_RULES) else "individual",
        )
        return self.run(config)

    def _init_agents(self, config: DebateConfig) -> List[AgentState]:
        """Initialize agents with roles."""
        agents = []
        role_keys = list(self.ROLE_PROMPTS.keys())[:config.num_agents]
        for i in range(config.num_agents):
            role = role_keys[i % len(role_keys)] if config.roles_imposed else ""
            agents.append(AgentState(
                agent_id=f"agent_{i+1}",
                role=role,
            ))
        return agents

    def _execute_round(
        self,
        config: DebateConfig,
        agents: List[AgentState],
        ledger: ArgumentLedger,
        round_num: int,
    ) -> bool:
        """Execute one round of debate."""
        for agent in agents:
            # Build prompt.
            prompt = self._build_prompt(config, agent, ledger, round_num)

            # Call LLM or use stub.
            if self._llm_executor:
                response = self._call_llm(prompt, config)
            else:
                response = self._stub_response(agent, config)

            if not response or not response.strip():
                ledger.record(
                    DebateEventType.ARGUMENT,
                    agent.agent_id,
                    "[EMPTY RESPONSE]",
                    round_num,
                )
                continue

            # Record argument.
            event = ledger.record(
                DebateEventType.ARGUMENT,
                agent.agent_id,
                response,
                round_num,
            )
            agent.arguments_count += 1
            agent.tokens_consumed += len(response.split()) * 2  # Rough estimate

        return True

    def _call_llm(self, prompt: str, config: DebateConfig) -> Optional[str]:
        """Call the LLM executor."""
        try:
            result = self._llm_executor(
                model="default",
                prompt=prompt,
                system_prompt="",
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            return result.get("response") if isinstance(result, dict) else None
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
            return None

    def _stub_response(self, agent: AgentState, config: DebateConfig) -> str:
        """Generate a stub response for testing."""
        return f"[{agent.agent_id}/{agent.role}] This is a test argument about {config.question[:50]}..."

    def _build_prompt(
        self,
        config: DebateConfig,
        agent: AgentState,
        ledger: ArgumentLedger,
        round_num: int,
    ) -> str:
        """Build the prompt for an agent."""
        role_prompt = self.ROLE_PROMPTS.get(agent.role, "You are a debate participant.")

        # Get recent history.
        history = ""
        if config.memory_type == "shared":
            recent = ledger.get_events_by_type(DebateEventType.ARGUMENT)[-5:]
            history = "\n".join(f"{e.agent_id}: {e.content[:100]}" for e in recent)

        return f"""{role_prompt}

Question: {config.question}

Round: {round_num}/{config.max_rounds}

Recent arguments:
{history if history else "(No previous arguments)"}

Provide your response (max 200 words):"""

    def _is_stagnating(self, ledger: ArgumentLedger, threshold: int) -> bool:
        """Check if the debate is stagnating."""
        args = ledger.get_events_by_type(DebateEventType.ARGUMENT)
        if len(args) < threshold * 2:
            return False

        # Check if last N rounds had no new unique content.
        recent = args[-threshold*3:]
        unique_contents = set(e.content.lower()[:50] for e in recent)
        return len(unique_contents) <= len(recent) / 2

    def _check_budget(self, agents: List[AgentState]) -> bool:
        """Check if token budget is exhausted."""
        total = sum(a.tokens_consumed for a in agents)
        return total > 8192  # Default budget

    def _detect_position_changes(
        self,
        ledger: ArgumentLedger,
        positions: Dict[str, str],
        agents: List[AgentState],
    ) -> None:
        """Detect and record position changes."""
        for agent in agents:
            current = positions.get(agent.agent_id, "")
            if current and agent.position and current != agent.position:
                ledger.record(
                    DebateEventType.POSITION_CHANGE,
                    agent.agent_id,
                    f"Moved from '{agent.position[:50]}' to '{current[:50]}'",
                )
            agent.position = current

    def _compute_emergence(self, ledger: ArgumentLedger, measures: EmergenceMeasures) -> EmergenceMeasures:
        """Compute emergence measures from the ledger."""
        args = ledger.get_events_by_type(DebateEventType.ARGUMENT)
        if not args:
            return measures

        # Argument diversity: unique argument types / total.
        type_counts: Dict[str, int] = {}
        for e in ledger.get_events_by_type(DebateEventType.ARGUMENT):
            # Simple heuristic: classify by first few words.
            key = e.content[:20].lower().replace(" ", "_")
            type_counts[key] = type_counts.get(key, 0) + 1

        unique_types = len(type_counts)
        measures.argument_diversity = unique_types / max(len(args), 1)

        # Position stability: ratio of agents who didn't change position.
        changes = ledger.get_position_changes()
        measures.position_stability = 1.0 - (len(changes) / max(len(changes) + 1, 1))

        # Specialization: measure role consistency.
        agent_roles = {}
        for e in args:
            if e.agent_id not in agent_roles:
                agent_roles[e.agent_id] = set()
            agent_roles[e.agent_id].add(e.event_type.value)

        total_unique = sum(len(roles) for roles in agent_roles.values())
        measures.specialization_index = total_unique / max(len(agent_roles), 1)

        # Novelty: new concepts per round (count PROPOSED_CONCEPT events).
        concepts = ledger.get_events_by_type(DebateEventType.PROPOSED_CONCEPT)
        measures.novelty_score = len(concepts) / max(measures.total_rounds, 1)

        return measures

    def export_results(self, path: str) -> str:
        """Export all experiment results to JSON."""
        import json
        data = {
            "experiments": [r.to_dict() for r in self._results],
            "summary": {
                "total_experiments": len(self._results),
                "by_condition": {
                    c.value: sum(1 for r in self._results if r.condition == c)
                    for c in DebateCondition
                },
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path
