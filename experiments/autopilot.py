"""AutoPilot - Connects experiments to the existing multi-agent debate engine.

This module bridges the synthetic data generation pipeline with the
philosophical_council DebateEngine, reusing the existing:
- TurnManager for turn sequencing
- Agent registry (existentialist, stoic, nihilist, spiritual, skeptic, pragmatist)
- ModeratorAgent for speaker selection
- LLMClient for response generation
- Database for persistence
- RawDebateRecorder for RAW experiment data

Trace path: experiment_id -> task_id -> run_id -> debate_id
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from experiments.generation.schemas import GeneratedTask

logger = logging.getLogger("AutoPilot")


@dataclass
class DebateRunResult:
    """Result of running a task through the debate engine."""

    experiment_id: str
    task_id: str
    run_id: str
    debate_id: int
    turn_count: int = 0
    final_response: str = ""
    is_valid: bool = False
    validation_score: float = 0.0
    validation_reasons: List[str] = field(default_factory=list)
    raw_experiment_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "debate_id": self.debate_id,
            "turn_count": self.turn_count,
            "final_response": self.final_response[:500] if self.final_response else "",
            "is_valid": self.is_valid,
            "validation_score": self.validation_score,
            "validation_reasons": list(self.validation_reasons),
            "raw_experiment_id": self.raw_experiment_id,
            "timestamp": self.timestamp,
        }


class AutoPilot:
    """Connects experiments to the existing DebateEngine.

    Reuses the multi-agent pipeline without creating a parallel system.
    Each experiment creates debates through the existing engine.
    """

    def __init__(self):
        """Initialize the AutoPilot."""
        self._engines: Dict[str, Any] = {}  # experiment_id -> DebateEngine
        self._results: Dict[str, List[DebateRunResult]] = {}  # experiment_id -> results
        self._lock = threading.Lock()

    def run_experiment(
        self,
        experiment_id: str,
        tasks: List[GeneratedTask],
        config: Optional[Dict[str, Any]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> List[DebateRunResult]:
        """Run an experiment through the debate engine.

        Args:
            experiment_id: Unique experiment identifier
            tasks: Generated tasks to process
            config: Experiment configuration
            should_stop: Optional callable returning True when a Stop/Delete has
                been requested. When set, NO new task starts after it fires
                (the current task's debate session is still finalized cleanly).

        Returns:
            List of DebateRunResults (may be shorter than ``tasks`` if a stop
            was requested between tasks)
        """
        results = []
        with self._lock:
            self._results[experiment_id] = []

        # Initialize debate engine for THIS experiment: reuse an injected engine
        # (tests stub the LLM via _create_debate_engine(..., llm_client=stub)); a
        # second _create_debate_engine would build a fresh REAL engine and clobber
        # the injected one (losing the stub / touching the network).
        engine = self._engines.get(experiment_id)
        if engine is None:
            engine = self._create_debate_engine(experiment_id, config)

        # Process each task
        for task in tasks:
            if should_stop is not None and should_stop():
                logger.info(
                    f"Experiment {experiment_id}: stop requested — no further tasks"
                )
                break
            result = self._run_task_through_debate(
                experiment_id=experiment_id,
                task=task,
                engine=engine,
            )
            results.append(result)

            with self._lock:
                if experiment_id not in self._results:
                    self._results[experiment_id] = []
                self._results[experiment_id].append(result)

        logger.info(
            f"Experiment {experiment_id} completed: {len(results)} tasks processed "
            f"(stop_requested={bool(should_stop and should_stop())})"
        )
        return results

    def get_results(self, experiment_id: str) -> List[DebateRunResult]:
        """Get results for an experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            List of DebateRunResults
        """
        with self._lock:
            return list(self._results.get(experiment_id, []))

    def _create_debate_engine(
        self,
        experiment_id: str,
        config: Optional[Dict[str, Any]],
        llm_client: Any = None,
        db_path: Optional[str] = None,
    ) -> Any:
        """Create and initialize a DebateEngine for an experiment.

        Args:
            experiment_id: Experiment identifier
            config: Experiment configuration
            llm_client: Optional injected LLM client (dependency injection).
                When provided, no real LLMClient is constructed and NO network
                is touched — used by tests to supply a deterministic stub.
            db_path: Optional override for the sqlite database location. When
                provided, no workspace `experiments/<id>/debate.db` is created
                (tests keep their DB in tmp_path).

        Returns:
            Initialized DebateEngine

        Security: the default LLM credentials are resolved via the environment
        (LIFE_MEAN_LLM_BASE_URL / LIFE_MEAN_LLM_API_KEY) / existing config —
        never hardcoded in this file.
        """
        from code_lab.multiagent import resolve_llm_credentials
        from philosophical_council.config import Config, DebateConfig
        from philosophical_council.database.database import Database
        from philosophical_council.llm.client import LLMClient
        from philosophical_council.core.debate_engine import DebateEngine
        from philosophical_council.agents.existentialist import ExistentialistAgent
        from philosophical_council.agents.stoic import StoicAgent
        from philosophical_council.agents.nihilist import NihilistAgent
        from philosophical_council.agents.spiritual import SpiritualAgent
        from philosophical_council.agents.skeptic import SkepticAgent
        from philosophical_council.agents.pragmatist import PragmatistAgent
        from philosophical_council.agents.moderator import ModeratorAgent
        from philosophical_council.memory.short_term import ShortTermMemory
        from philosophical_council.memory.mid_term import MidTermMemory
        from philosophical_council.memory.long_term import LongTermMemory
        from philosophical_council.memory.consolidation import MemoryConsolidator

        # Create config
        debate_config = DebateConfig(
            topic="Synthetic task debate",
            temperature=config.get("temperature", 0.8) if config else 0.8,
            max_tokens=config.get("max_tokens", 700) if config else 700,
        )

        full_config = Config(debate=debate_config)

        # Initialize database (test can override the location to tmp_path).
        if db_path is None:
            db_path = f"experiments/{experiment_id}/debate.db"
        db = Database(db_path)

        # Initialize LLM client (injectable for tests; never a hardcoded key).
        if llm_client is not None:
            llm = llm_client
        else:
            _base, _key = resolve_llm_credentials()
            llm = LLMClient(base_url=_base or "http://localhost:1234/v1", api_key=_key)

        # Create engine
        engine = DebateEngine(full_config, db, llm)

        # Register agents
        for agent_class in [
            ExistentialistAgent,
            StoicAgent,
            NihilistAgent,
            SpiritualAgent,
            SkepticAgent,
            PragmatistAgent,
        ]:
            agent = agent_class()
            engine.register_agent(agent)

        # Register moderator
        moderator = ModeratorAgent()
        engine.register_moderator(moderator)

        # Setup memory
        engine.short_term_memory = ShortTermMemory()
        engine.mid_term_memory = MidTermMemory()
        engine.long_term_memory = LongTermMemory()
        engine.consolidator = MemoryConsolidator(
            engine.mid_term_memory, engine.long_term_memory
        )

        with self._lock:
            self._engines[experiment_id] = engine

        logger.info(f"Created DebateEngine for experiment {experiment_id}")
        return engine

    def _run_task_through_debate(
        self,
        experiment_id: str,
        task: GeneratedTask,
        engine: Any,
    ) -> DebateRunResult:
        """Run a single task through the debate engine.

        Args:
            experiment_id: Experiment identifier
            task: Task to process
            engine: DebateEngine instance

        Returns:
            DebateRunResult
        """
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        reasons: List[str] = []

        # Create/start this task's OWN debate session. A session is created
        # ONLY if start_debate returns True (session started, isolated). If the
        # engine is already running (or start fails), the task must NOT be
        # treated as created — no phantom "Created debate", no shared session.
        debate_id, started = self._create_debate(experiment_id, task, engine)
        if not started or debate_id is None:
            self._finalize_engine_session(engine)
            reasons.append("DEBATE_STILL_RUNNING")
            return DebateRunResult(
                experiment_id=experiment_id,
                task_id=task.task_id,
                run_id=run_id,
                debate_id=0,
                turn_count=0,
                is_valid=False,
                validation_score=0.0,
                validation_reasons=reasons,
                raw_experiment_id=getattr(engine, '_raw_experiment_id', None),
            )

        # Run this task's debate synchronously and ONLY this task's debate.
        # background=False means NO engine thread is running: this loop is the
        # single authoritative driver, so turns are ordered and counted once.
        try:
            turn_count = self._execute_debate_turns(engine, max_turns=5)
        finally:
            self._finalize_engine_session(engine)

        # Get final response — the LAST turn that actually carries content.
        # A real debate may end with a reserved/rejected turn (moderator
        # repetition guard) whose `.response` is empty; validating that would
        # be validating a phantom, not evidence (GOAL 3). So we skip empty
        # trailing turns and use the last completed content turn.
        all_turns = engine.turn_manager.get_all_turns()
        final_response = ""
        for t in reversed(all_turns):
            if (t.response or "").strip():
                final_response = t.response
                break

        # Validate result
        is_valid, score = self._validate_response(task, final_response)
        if not final_response:
            reasons.append("NO_ANSWER")
        if turn_count == 0:
            reasons.append("MIN_TURNS_NOT_REACHED" if not final_response else "DEBATE_STILL_RUNNING")
        if not is_valid and final_response and turn_count > 0:
            reasons.append("VALIDATOR_FAILURE")
        if is_valid:
            reasons = []

        # Get RAW experiment ID from engine (finalize may set/keep it).
        raw_experiment_id = getattr(engine, '_raw_experiment_id', None)

        result = DebateRunResult(
            experiment_id=experiment_id,
            task_id=task.task_id,
            run_id=run_id,
            debate_id=debate_id,
            turn_count=turn_count,
            final_response=final_response,
            is_valid=is_valid,
            validation_score=score,
            validation_reasons=reasons,
            raw_experiment_id=raw_experiment_id,
        )

        logger.info(
            f"Task {task.task_id} -> run {run_id} -> debate {debate_id}: "
            f"{turn_count} turns, valid={is_valid}"
            + (f", reasons={reasons}" if reasons else "")
        )

        return result

    def _create_debate(
        self, experiment_id: str, task: GeneratedTask, engine: Any
    ) -> int:
        """Create a debate for a task.

        Args:
            experiment_id: Experiment identifier
            task: Task to debate
            engine: DebateEngine instance

        Returns:
            Debate ID
        """
        # Use task description as debate topic
        topic = f"Task: {task.description[:100]}"

        # Start THIS task's dedicated, isolated session. background=False means
        # no engine thread runs; AutoPilot owns the single turn loop. Honor the
        # return value: False => engine already running/start failed, so the
        # session MUST NOT be treated as created (no fake lifecycle state).
        ok = engine.start_debate(background=False)
        if not ok:
            logger.error(
                f"start_debate refused for task {task.task_id} "
                f"(engine {id(engine)} likely already running). No debate created."
            )
            return None, False

        # Get the debate ID from engine
        debate_id = engine._get_debate_id()
        if debate_id is None:
            logger.error(f"No debate id after start for task {task.task_id}")
            return None, False
        # Record topic on the created debate for traceability (best effort).
        logger.info(f"Created debate {debate_id} for task {task.task_id}")
        return debate_id, True

    def _execute_debate_turns(self, engine: Any, max_turns: int = 5) -> int:
        """Execute debate turns.

        Args:
            engine: DebateEngine instance
            max_turns: Maximum number of turns to execute

        Returns:
            Number of turns executed
        """
        turn_count = 0
        for _ in range(max_turns):
            success = engine.step_once()
            if not success:
                logger.warning("Debate step failed")
                break
            turn_count += 1

        return turn_count

    def _finalize_engine_session(self, engine: Any) -> None:
        """Terminate a controlled (background=False) debate session cleanly.

        stop_debate joins any live thread and flips the session to its terminal
        STOPPED state, so the next task starts from a fully reset engine
        (see DebateEngine.start_debate). Guarantees no orphan loop outlives its
        owning task.
        """
        try:
            engine.stop_debate()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not finalize debate session: %s", exc)

    def _validate_response(
        self, task: GeneratedTask, response: str
    ) -> tuple[bool, float]:
        """Validate a debate response against ground truth.

        Args:
            task: Original task
            response: Generated response

        Returns:
            Tuple of (is_valid, score)
        """
        if not response:
            return False, 0.0

        # Try to extract numeric answer from response
        ground_truth = task.ground_truth
        if ground_truth is None:
            return False, 0.0

        # Simple validation: check if response contains the ground truth
        if isinstance(ground_truth, (int, float)):
            # Try to find number in response
            import re
            numbers = re.findall(r'-?\d+\.?\d*', response)
            if numbers:
                try:
                    answer = float(numbers[-1])
                    return abs(answer - ground_truth) < 1e-6, 1.0 if abs(answer - ground_truth) < 1e-6 else 0.5
                except ValueError:
                    pass

        return False, 0.0

    def stop_experiment(self, experiment_id: str) -> None:
        """Stop an experiment.

        Args:
            experiment_id: Experiment identifier
        """
        with self._lock:
            if experiment_id in self._engines:
                engine = self._engines[experiment_id]
                engine.stop_debate()
                del self._engines[experiment_id]

    def get_statistics(self, experiment_id: str) -> Dict[str, Any]:
        """Get statistics for an experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Statistics dictionary
        """
        results = self.get_results(experiment_id)
        if not results:
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "validation_pass_rate": 0.0,
                "avg_turns": 0.0,
            }

        successful = sum(1 for r in results if r.is_valid)
        avg_turns = sum(r.turn_count for r in results) / len(results)

        return {
            "total_runs": len(results),
            "successful_runs": successful,
            "validation_pass_rate": successful / len(results),
            "avg_turns": avg_turns,
        }
