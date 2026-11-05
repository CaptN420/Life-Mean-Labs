"""Experiment UI controller for synthetic data generation.

Provides a web-based dashboard for experiment configuration,
monitoring, and control via HTTP API.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("ExperimentUI")


@dataclass
class ExperimentState:
    """Current state of an experiment."""

    experiment_id: str
    is_running: bool = False
    start_time: Optional[float] = None
    tasks_generated: int = 0
    tasks_completed: int = 0
    tasks_valid: int = 0
    tasks_invalid: int = 0
    current_pass_rate: float = 0.0
    avg_novelty_score: float = 0.0
    errors: List[str] = field(default_factory=list)
    mode: str = "deterministic"
    # True when the entry was rebuilt from a persisted run summary after a
    # restart (the run itself is over; nothing is executing).
    rehydrated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        # Lifecycle status is DERIVED from real state (GOAL 5/8) so the UI
        # never invents it: STARTING while running+just spawned, RUNNING while
        # running with progress, COMPLETED when not running and finished,
        # FAILED when not running with errors, STOPPED otherwise.
        if self.is_running:
            status = "RUNNING" if self.tasks_generated > 0 else "STARTING"
        elif self.errors:
            status = "FAILED"
        elif self.tasks_completed > 0 or self.tasks_generated > 0:
            status = "COMPLETED"
        else:
            status = "CREATED"
        return {
            "experiment_id": self.experiment_id,
            "is_running": self.is_running,
            "status": status,
            "mode": self.mode,
            "start_time": self.start_time,
            "elapsed_seconds": time.time() - self.start_time if self.start_time else 0,
            "tasks_generated": self.tasks_generated,
            "tasks_completed": self.tasks_completed,
            "tasks_valid": self.tasks_valid,
            "tasks_invalid": self.tasks_invalid,
            "pass_rate": self.current_pass_rate,
            "avg_novelty_score": self.avg_novelty_score,
            "errors": self.errors[-10:],  # Last 10 errors
            "rehydrated": self.rehydrated,
        }


class ExperimentUIController:
    """Controls experiment UI state and metrics."""

    def __init__(self):
        """Initialize the UI controller."""
        self._experiments: Dict[str, ExperimentState] = {}
        self._configurations: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        # Live AutoPilot per experiment so Stop/Delete can reach the actual
        # runtime (engine threads, task loop), not just flip ExperimentState.
        self._autopilots: Dict[str, Any] = {}
        self._stop_requested: Dict[str, bool] = {}
        self._worker_threads: Dict[str, threading.Thread] = {}
        # Observability tracker per experiment (live debate transcript, traces).
        # Retained after completion so /observability and /manifest remain
        # readable AFTER a run — a manifest that only exists mid-run cannot
        # serve reproducibility. Bounded to `_obs_retention` finished runs.
        self._observability: Dict[str, Any] = {}
        self._obs_completion_order: List[str] = []
        self._obs_retention = 20

    def register_experiment(
        self,
        experiment_id: str,
        config: Dict[str, Any],
    ) -> ExperimentState:
        """Register a new experiment.

        Args:
            experiment_id: Unique experiment identifier
            config: Experiment configuration

        Returns:
            ExperimentState
        """
        with self._lock:
            state = ExperimentState(experiment_id=experiment_id)
            state.mode = "debate" if config.get("debate") else "deterministic"
            self._experiments[experiment_id] = state
            self._configurations[experiment_id] = config
            logger.info(f"Registered experiment {experiment_id}")
            return state

    def set_mode(self, experiment_id: str, mode: str) -> bool:
        """Set the execution mode for an experiment (deterministic|debate).

        Args:
            experiment_id: Experiment identifier
            mode: 'deterministic' or 'debate'

        Returns:
            True if mode was set successfully
        """
        with self._lock:
            if experiment_id not in self._experiments:
                logger.error(f"Experiment {experiment_id} not found for mode switch")
                return False
            # Validate mode
            if mode not in ("deterministic", "debate"):
                logger.error(f"Invalid mode '{mode}' for experiment {experiment_id}")
                return False
            state = self._experiments[experiment_id]
            config = self._configurations.get(experiment_id, {})
            if mode == "debate":
                state.mode = "debate"
                config["debate"] = True
                config["deterministic"] = False
            else:
                state.mode = "deterministic"
                config["debate"] = False
                config["deterministic"] = True
            self._configurations[experiment_id] = config
            logger.info(f"Experiment {experiment_id} mode set to {mode}")
            return True

    def restart_experiment(self, experiment_id: str) -> bool:
        """Restart an experiment from the beginning with current configuration.

        Args:
            experiment_id: Experiment identifier

        Returns:
            True if restart was initiated successfully
        """
        with self._lock:
            if experiment_id not in self._experiments:
                logger.error(f"Experiment {experiment_id} not found for restart")
                return False
            state = self._experiments[experiment_id]
            if state.is_running:
                logger.warning(f"Cannot restart experiment {experiment_id} while running")
                return False
            # Reset state for fresh run
            state.tasks_generated = 0
            state.tasks_completed = 0
            state.tasks_valid = 0
            state.tasks_invalid = 0
            state.current_pass_rate = 0.0
            state.avg_novelty_score = 0.0
            state.errors = []
            logger.info(f"Experiment {experiment_id} reset for restart")
        # Start the experiment with reset state
        return self.start_experiment(experiment_id)

    # ── Reprise réelle : progression persistée tâche par tâche ─────────────
    def _progress_dir(self) -> Path:
        """Checkpoints live next to the run summaries (same mounted volume)."""
        return self._runs_dir().parent / "progress"

    def _progress_path(self, experiment_id: str) -> Path:
        safe = experiment_id.replace("/", "_").replace("\\", "_")
        return self._progress_dir() / f"{safe}.jsonl"

    @staticmethod
    def _task_fingerprint(task: Any) -> str:
        """Content identity of a generated task.

        Task ids are random UUIDs, so they cannot identify a task across
        processes. What IS stable for a given seed is the task's content:
        domain, difficulty, description and ground truth.
        """
        import hashlib as _hashlib

        material = "|".join([
            str(getattr(task, "domain", "")),
            str(getattr(task, "difficulty", "")),
            str(getattr(task, "description", "")),
            str(getattr(task, "ground_truth", "")),
        ])
        return _hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def _start_progress(self, experiment_id: str, tasks: List[Any],
                        config: Dict[str, Any]) -> None:
        """Open a checkpoint file for a fresh run (previous one is archived)."""
        import json as _json
        import time as _time

        path = self._progress_path(experiment_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                # NO DELETE: the previous checkpoint is preserved under a new name.
                archive = path.with_name(f"{path.stem}.{int(_time.time())}.jsonl.bak")
                path.replace(archive)
            meta = {
                "type": "meta",
                "experiment_id": experiment_id,
                "total": len(tasks),
                "seed": config.get("seed", 42),
                "domain": config.get("domain", "math"),
                "mode": "deterministic",
                "created_at": _time.time(),
            }
            path.write_text(_json.dumps(meta) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.error("could not open checkpoint for %s: %s", experiment_id, exc)

    def _append_progress(self, experiment_id: str, index: int, task: Any,
                         is_valid: bool) -> None:
        """Record one finished task. Appended AFTER its RAW evidence exists."""
        import json as _json
        import time as _time

        entry = {
            "type": "task",
            "index": index,
            "task_id": getattr(task, "task_id", ""),
            "fingerprint": self._task_fingerprint(task),
            "is_valid": bool(is_valid),
            "ts": _time.time(),
        }
        try:
            with open(self._progress_path(experiment_id), "a", encoding="utf-8") as fh:
                fh.write(_json.dumps(entry) + "\n")
        except OSError as exc:
            logger.error("could not append progress for %s: %s", experiment_id, exc)

    def _load_progress(self, experiment_id: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Read a checkpoint. Corrupt lines are skipped and logged, never guessed."""
        import json as _json

        path = self._progress_path(experiment_id)
        if not path.exists():
            return None, []
        meta: Optional[Dict[str, Any]] = None
        entries: List[Dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = _json.loads(line)
                except ValueError:
                    logger.warning("skipping corrupt checkpoint line in %s", path.name)
                    continue
                if record.get("type") == "meta":
                    meta = record
                elif record.get("type") == "task":
                    entries.append(record)
        except OSError as exc:
            logger.error("could not read checkpoint for %s: %s", experiment_id, exc)
            return None, []
        return meta, entries

    def continue_experiment(self, experiment_id: str) -> bool:
        """Resume an interrupted run from its last recorded task.

        This used to call ``start_experiment`` (a fresh run from task 0) and, for
        a finished run, silently restart it — a "continue" that continued
        nothing. Now it resumes only what has a checkpoint, refuses a finished
        run, and refuses a checkpoint that no longer matches the configuration.
        """
        with self._lock:
            state = self._experiments.get(experiment_id)
            if state is None:
                logger.error(f"Experiment {experiment_id} not found for continue")
                return False
            if state.is_running:
                logger.warning(f"Cannot continue experiment {experiment_id} while already running")
                return False
            config = dict(self._configurations.get(experiment_id, {}))

        meta, entries = self._load_progress(experiment_id)
        if not meta or not entries:
            self.add_error(
                experiment_id,
                "Continue refusé : aucune progression enregistrée pour cette expérience. "
                "Utilisez Démarrer (ou Redémarrer) — rien ne serait repris.",
            )
            return False

        total = int(meta.get("total", 0) or 0)
        if len(entries) >= total:
            self.add_error(
                experiment_id,
                f"Continue refusé : l'expérience est déjà terminée ({len(entries)}/{total} tâches). "
                "Utilisez Redémarrer pour une nouvelle exécution complète.",
            )
            return False

        if (meta.get("seed") != config.get("seed", 42)
                or meta.get("domain") != config.get("domain", "math")):
            self.add_error(
                experiment_id,
                "Continue refusé : la configuration (seed/domaine) diffère de celle de "
                "l'exécution interrompue ; reprendre mélangerait deux expériences.",
            )
            return False

        with self._lock:
            state = self._experiments.get(experiment_id)
            if state is None:
                return False
            state.is_running = True
            self._stop_requested[experiment_id] = False
            thread = threading.Thread(
                target=self._run_experiment_loop,
                args=(experiment_id, config, True),
                daemon=True,
                name=f"exp-{experiment_id}-resume",
            )
            self._worker_threads[experiment_id] = thread
            thread.start()

        logger.info(
            "Resuming experiment %s: %d/%d tasks already recorded",
            experiment_id, len(entries), total,
        )
        self._notify_callbacks(experiment_id, "started")
        return True

    def start_experiment(self, experiment_id: str) -> bool:
        """Start an experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            True if started successfully
        """
        with self._lock:
            if experiment_id not in self._experiments:
                logger.error(f"Experiment {experiment_id} not found")
                return False

            state = self._experiments[experiment_id]
            config = self._configurations.get(experiment_id, {})

            # Mutate lifecycle state BEFORE spawning the worker (GOAL 5): the
            # worker may complete extremely fast and flip `is_running` False in
            # its `finally`. If we set is_running after thread.start(), a fast
            # worker could either reset it behind us or transiently report a
            # completed run as RUNNING. All state writes happen under the lock
            # so no snapshot straddles the boundary and `running_count` never
            # lies after a fresh completion.
            state.is_running = True
            state.start_time = time.time()
            state.tasks_generated = 0
            state.tasks_completed = 0
            state.tasks_valid = 0
            state.tasks_invalid = 0
            state.errors = []

            thread = threading.Thread(
                target=self._run_experiment_loop,
                args=(experiment_id, config, False),
                daemon=True,
                name=f"exp-{experiment_id}",
            )
            self._worker_threads[experiment_id] = thread
            self._stop_requested[experiment_id] = False
            thread.start()

            logger.info(f"Started experiment {experiment_id}")
        # Notify outside lock to avoid deadlock
        self._notify_callbacks(experiment_id, "started")
        return True

    def stop_experiment(self, experiment_id: str) -> bool:
        """Stop an experiment (real cancellation).

        Sets the stop flag (the task loop checks it) AND propagates the stop to
        the live AutoPilot, which stops the engine's debate session and joins
        its thread. No NEW task / LLM call may begin after cancellation.
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return False

            self._stop_requested[experiment_id] = True
            state = self._experiments[experiment_id]
            state.is_running = False  # derived UI status becomes STOPPED
            autopilot = self._autopilots.get(experiment_id)
            logger.info(f"Stopped experiment {experiment_id}")

        # Outside the lock: actually cancel the engine if the loop started one.
        if autopilot is not None:
            try:
                autopilot.stop_experiment(experiment_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"AutoPilot stop failed for {experiment_id}: {exc}")
        # Notify outside lock to avoid deadlock
        self._notify_callbacks(experiment_id, "stopped")
        return True

    def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment from the dashboard.

        Never removes an experiment whose execution still runs (a P0 lifecycle
        violation). If the experiment is active, request cancellation, wait a
        bounded time for the worker thread to finish, and only then remove it.
        If cancellation cannot finish in time, refuse the delete truthfully
        (returns False) rather than log a success while execution continues.
        """
        with self._lock:
            if experiment_id not in self._experiments:
                logger.warning(f"Experiment {experiment_id} not found for deletion")
                return False
            state = self._experiments[experiment_id]
            if state.is_running:
                # Request cancellation first; join outside the lock.
                self._stop_requested[experiment_id] = True
                autopilot = self._autopilots.get(experiment_id)
                thread = self._worker_threads.get(experiment_id)
            else:
                autopilot = None
                thread = None

        if autopilot is not None:
            try:
                autopilot.stop_experiment(experiment_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"AutoPilot stop failed during delete {experiment_id}: {exc}")
        if thread is not None:
            thread.join(timeout=8.0)
            if thread.is_alive():
                logger.warning(
                    f"DELETE_BLOCKED_ACTIVE_EXECUTION: {experiment_id} worker still "
                    f"alive after join timeout; refusing delete to keep execution managed"
                )
                with self._lock:
                    self._stop_requested[experiment_id] = True
                    st = self._experiments.get(experiment_id)
                    if st is not None:
                        st.is_running = True  # keep visible; it IS still running
                return False

        with self._lock:
            self._experiments.pop(experiment_id, None)
            self._configurations.pop(experiment_id, None)
            self._callbacks.pop(experiment_id, None)
            self._autopilots.pop(experiment_id, None)
            self._stop_requested.pop(experiment_id, None)
            self._worker_threads.pop(experiment_id, None)
            logger.info(f"Deleted experiment {experiment_id}")
        return True

    def update_metrics(
        self,
        experiment_id: str,
        metrics: Dict[str, Any],
    ) -> None:
        """Update experiment metrics.

        Args:
            experiment_id: Experiment identifier
            metrics: New metrics data
        """
        with self._lock:
            if experiment_id not in self._experiments:
                return

            state = self._experiments[experiment_id]

            # Update counters
            if "tasks_generated" in metrics:
                state.tasks_generated = metrics["tasks_generated"]
            if "tasks_completed" in metrics:
                state.tasks_completed = metrics["tasks_completed"]
            if "tasks_valid" in metrics:
                state.tasks_valid = metrics["tasks_valid"]
            if "tasks_invalid" in metrics:
                state.tasks_invalid = metrics["tasks_invalid"]

            # Update rates
            if "pass_rate" in metrics:
                state.current_pass_rate = metrics["pass_rate"]
            if "novelty_score" in metrics:
                state.avg_novelty_score = metrics["novelty_score"]

            # Track errors
            if "error" in metrics:
                state.errors.append(metrics["error"])

            logger.debug(f"Updated metrics for experiment {experiment_id}")

    def add_error(self, experiment_id: str, error: str) -> None:
        """Add an error to an experiment.

        Args:
            experiment_id: Experiment identifier
            error: Error message
        """
        with self._lock:
            if experiment_id in self._experiments:
                state = self._experiments[experiment_id]
                state.errors.append(error)
                logger.error(f"Experiment {experiment_id} error: {error}")

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentState]:
        """Get experiment state.

        Args:
            experiment_id: Experiment identifier

        Returns:
            ExperimentState or None if not found
        """
        with self._lock:
            return self._experiments.get(experiment_id)

    def get_all_experiments(self) -> Dict[str, ExperimentState]:
        """Get all experiments.

        Returns:
            Dictionary of experiment_id to ExperimentState
        """
        with self._lock:
            return dict(self._experiments)

    def subscribe(
        self,
        experiment_id: str,
        event: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to experiment events.

        Args:
            experiment_id: Experiment identifier
            event: Event name (started, stopped, metrics)
            callback: Callback function
        """
        with self._lock:
            if experiment_id not in self._callbacks:
                self._callbacks[experiment_id] = {}
            if event not in self._callbacks[experiment_id]:
                self._callbacks[experiment_id][event] = []
            self._callbacks[experiment_id][event].append(callback)

    def unsubscribe(
        self,
        experiment_id: str,
        event: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Unsubscribe from experiment events.

        Args:
            experiment_id: Experiment identifier
            event: Event name
            callback: Callback function to remove
        """
        with self._lock:
            if experiment_id in self._callbacks:
                if event in self._callbacks[experiment_id]:
                    callbacks = self._callbacks[experiment_id][event]
                    if callback in callbacks:
                        callbacks.remove(callback)

    def _notify_callbacks(self, experiment_id: str, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Notify callbacks of an event.

        Args:
            experiment_id: Experiment identifier
            event: Event name
            data: Optional event data
        """
        with self._lock:
            if experiment_id in self._callbacks:
                for callback in self._callbacks[experiment_id].get(event, []):
                    try:
                        callback(data or {})
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

    def _run_experiment_loop(self, experiment_id: str, config: Dict[str, Any],
                             resume: bool = False) -> None:
        """Run the experiment loop in a background thread.

        Uses ExperimentRunner to connect generated tasks with the existing
        multi-agent pipeline (SmartRouter + ToolWorker). When `debate` mode is
        enabled, routes through the EXISTING AutoPilot → DebateEngine path
        (NO new orchestrator — rule 3).

        Trace path: experiment_id -> task_id -> run_id [-> debate_id]
        """
        try:
            from experiments.generation.task_generator import TaskGenerator

            # Generate tasks
            generator = TaskGenerator(seed=config.get("seed", 42))
            domain = config.get("domain", "math")
            difficulty_range = tuple(config.get("difficulty_range", [1, 5]))
            num_tasks = config.get("num_tasks", 10)  # Smaller for testing
            tasks = generator.generate_batch(
                domain=domain,
                difficulty_range=difficulty_range,
                count=num_tasks,
            )

            with self._lock:
                state = self._experiments[experiment_id]
                state.tasks_generated = len(tasks)

            logger.info(f"Generated {len(tasks)} tasks for experiment {experiment_id}")

            # Observability exists for EVERY mode, not only debates: the
            # reproducibility manifest must be exportable for deterministic
            # runs too (they are the reproducible ones).
            self._ensure_observability(experiment_id, config)

            # BEHAVIOR SELECTION — reuse the existing stable core (rule 1/3).
            #   debate=True  → AutoPilot → DebateEngine (real multi-agent path)
            #   else         → ExperimentRunner → SmartRouter + ToolWorker (deterministic)
            debate_mode = bool(config.get("debate", False))

            if debate_mode:
                # GOAL 13: if the user explicitly chose Debate/Multi-Agent mode,
                # do NOT silently fall back to deterministic. Probe the LLM
                # first; if unavailable, fail the experiment with an explicit
                # error so the UI tells the truth.
                from code_lab.multiagent import probe_llm, resolve_llm_credentials
                _bu, _k = resolve_llm_credentials()
                _probe = probe_llm(_bu, _k)
                if not _probe.get("available"):
                    msg = ("Debate/Multi-Agent mode requested but the LLM backend is "
                           f"unavailable ({_probe.get('error','unknown')}). "
                           "No silent deterministic fallback — choose Deterministic mode "
                           "or fix the backend.")
                    logger.error(f"Experiment {experiment_id}: {msg}")
                    self.add_error(experiment_id, msg)
                    raise RuntimeError(msg)
                from experiments.autopilot import AutoPilot
                autopilot = AutoPilot()
                # Observability is created BEFORE taking the lock (the helper
                # acquires the same non-reentrant lock -> would deadlock here).
                self._ensure_observability(experiment_id, config)
                with self._lock:
                    self._autopilots[experiment_id] = autopilot
                # Deterministic validator is the authority; AutoPilot reuses it
                # via _validate_response AFTER the debate.
                debate_results = autopilot.run_experiment(
                    experiment_id, tasks, config,
                    should_stop=lambda: self._is_stop_requested(experiment_id),
                )

                valid_count = sum(1 for r in debate_results if r.is_valid)
                invalid_count = len(debate_results) - valid_count
                pass_rate = (valid_count / len(debate_results)) if debate_results else 0.0
                self.update_metrics(experiment_id, {
                    "tasks_completed": len(debate_results),
                    "tasks_valid": valid_count,
                    "tasks_invalid": invalid_count,
                    "pass_rate": pass_rate,
                    "mode": "debate",
                })
                # Persist debate results as RAW (append-only).
                self._persist_results_to_raw(experiment_id, debate_results, mode="debate")
                logger.info(
                    f"Experiment {experiment_id} via AutoPilot/DebateEngine: "
                    f"{len(debate_results)} tasks, {valid_count} valid, pass rate {pass_rate:.1%}"
                )
                return

            from experiments.runner import ExperimentRunner, ExperimentContext

            # Run through ExperimentRunner (reuses SmartRouter + ToolWorker)
            runner = ExperimentRunner(config=config)

            # Create experiment context
            context = ExperimentContext(
                experiment_id=experiment_id,
                generation_id=f"gen_{experiment_id}",
                domain=domain,
                difficulty=difficulty_range[0],
            )

            # A resumed run must prove it is the SAME run: same seed, same
            # domain, same task content at every already-recorded index.
            done_indices: set = set()
            prior_valid = 0
            if resume:
                meta, entries = self._load_progress(experiment_id)
                if not meta:
                    raise RuntimeError(
                        "Resume impossible : aucune progression enregistrée pour cette expérience."
                    )
                if (int(meta.get("total", -1)) != len(tasks)
                        or meta.get("seed") != config.get("seed", 42)
                        or meta.get("domain") != domain):
                    raise RuntimeError(
                        "Resume refusé : la configuration a changé depuis l'interruption "
                        f"(checkpoint: {meta.get('total')} tâches, seed {meta.get('seed')}, "
                        f"domaine {meta.get('domain')} ; maintenant : {len(tasks)} tâches, "
                        f"seed {config.get('seed', 42)}, domaine {domain})."
                    )
                fingerprints = [self._task_fingerprint(t) for t in tasks]
                for entry in entries:
                    index = int(entry.get("index", -1))
                    if index < 0 or index >= len(tasks):
                        raise RuntimeError(
                            f"Resume refusé : le checkpoint référence une tâche {index} inexistante."
                        )
                    if entry.get("fingerprint") != fingerprints[index]:
                        raise RuntimeError(
                            f"Resume refusé : la tâche régénérée à l'index {index} ne correspond "
                            "plus à celle qui avait été exécutée (contenu différent)."
                        )
                    done_indices.add(index)
                prior_valid = sum(1 for e in entries if e.get("is_valid"))
                logger.info(
                    "Resume %s: %d/%d tasks already recorded, %d valid",
                    experiment_id, len(done_indices), len(tasks), prior_valid,
                )
            else:
                self._start_progress(experiment_id, tasks, config)

            # Task-by-task: each finished task writes its RAW evidence first,
            # then its checkpoint line. Order matters — a task may only be
            # skipped on resume if it already left evidence.
            total_tasks = len(tasks)
            new_results: List[Any] = []
            stopped_early = False
            for index, task in enumerate(tasks):
                if index in done_indices:
                    continue
                if self._is_stop_requested(experiment_id):
                    stopped_early = True
                    logger.info(
                        "Stop requested for %s before task %d/%d",
                        experiment_id, index + 1, total_tasks,
                    )
                    break

                result = runner.run_task(task, context)
                new_results.append(result)
                self._persist_results_to_raw(experiment_id, [result], mode="deterministic")
                self._append_progress(experiment_id, index, task, bool(result.is_valid))

                completed = len(done_indices) + len(new_results)
                valid = prior_valid + sum(1 for r in new_results if r.is_valid)
                self.update_metrics(experiment_id, {
                    "tasks_completed": completed,
                    "tasks_valid": valid,
                    "tasks_invalid": completed - valid,
                    "pass_rate": (valid / completed) if completed else 0.0,
                    "mode": "deterministic",
                })

            completed = len(done_indices) + len(new_results)
            valid = prior_valid + sum(1 for r in new_results if r.is_valid)
            pass_rate = (valid / completed) if completed else 0.0
            self.update_metrics(experiment_id, {
                "tasks_completed": completed,
                "tasks_valid": valid,
                "tasks_invalid": completed - valid,
                "pass_rate": pass_rate,
                "mode": "deterministic",
            })

            logger.info(
                "Experiment %s %s: %d/%d tasks done, %d valid, pass rate %.1f%%%s",
                experiment_id,
                "paused" if stopped_early else "completed",
                completed, total_tasks, valid, pass_rate * 100,
                " (resume possible)" if stopped_early else "",
            )

        except Exception as e:
            logger.error(f"Experiment {experiment_id} failed: {e}")
            self.add_error(experiment_id, str(e))
            # Record error in observability
            with self._lock:
                obs = self._observability.get(experiment_id)
                if obs:
                    obs.record_error(str(e))
                    obs.complete_experiment(status="FAILED")
        finally:
            # Mark as complete
            with self._lock:
                if experiment_id in self._experiments:
                    state = self._experiments[experiment_id]
                    state.is_running = False
                self._stop_requested.pop(experiment_id, None)
                self._worker_threads.pop(experiment_id, None)
                self._autopilots.pop(experiment_id, None)
                # Complete observability tracking but KEEP it readable: the
                # manifest is only useful after the run, so it must survive it.
                obs = self._observability.get(experiment_id)
                if obs:
                    obs.complete_experiment(status="COMPLETED")
                    if experiment_id not in self._obs_completion_order:
                        self._obs_completion_order.append(experiment_id)
                    while len(self._obs_completion_order) > self._obs_retention:
                        oldest = self._obs_completion_order.pop(0)
                        if oldest != experiment_id:
                            self._observability.pop(oldest, None)
            # Persist a run summary so the experiment survives a restart: RAW
            # holds the evidence, this holds the state that makes it listable.
            self._write_run_summary(experiment_id)
            self._notify_callbacks(experiment_id, "stopped")

    def _runs_dir(self) -> Path:
        """Directory holding one run summary per finished experiment.

        ``LIFE_MEAN_RUNS_DIR`` overrides; default is ``<repo>/data/experiments/
        runs`` (inside the dashboard's mounted ``/app/data`` volume).
        """
        import os as _os

        env = _os.environ.get("LIFE_MEAN_RUNS_DIR")
        if env:
            return Path(env).expanduser()
        return Path(__file__).resolve().parent.parent / "data" / "experiments" / "runs"

    def _write_run_summary(self, experiment_id: str) -> None:
        """Persist the finished run's state so a restart can list it again.

        Never raises into the caller: a summary failure must not turn a
        completed run into a failed one, but it IS logged (no silent loss).
        """
        import json as _json
        import os as _os

        with self._lock:
            state = self._experiments.get(experiment_id)
            config = dict(self._configurations.get(experiment_id, {}))
            if state is None:
                return
            payload = {
                "schema": "experiment-run/1",
                "experiment_id": experiment_id,
                "state": state.to_dict(),
                "config": config,
                "finished_at": time.time(),
            }
        try:
            directory = self._runs_dir()
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{experiment_id}.json"
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(_json.dumps(payload, indent=2, sort_keys=True, default=str),
                           encoding="utf-8")
            _os.replace(tmp, target)
        except OSError as exc:
            logger.error("could not persist run summary for %s: %s", experiment_id, exc)

    def rehydrate_from_summaries(self) -> int:
        """Rebuild the in-memory registry from persisted run summaries.

        Called at server start: without it a restart shows an empty dashboard
        while RAW evidence sits on disk. Rehydrated entries are marked
        ``rehydrated=True`` and are never reported as running. Returns the
        number of runs restored.
        """
        import json as _json

        directory = self._runs_dir()
        if not directory.exists():
            return 0
        restored = 0
        for path in sorted(directory.glob("*.json")):
            try:
                raw = _json.loads(path.read_text(encoding="utf-8"))
                if raw.get("schema") != "experiment-run/1":
                    logger.warning("skipping run summary %s: unknown schema", path.name)
                    continue
                exp_id = str(raw["experiment_id"])
                saved = raw.get("state", {}) or {}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logger.warning("skipping unreadable run summary %s: %s", path.name, exc)
                continue
            with self._lock:
                if exp_id in self._experiments:
                    continue
                state = ExperimentState(
                    experiment_id=exp_id,
                    is_running=False,
                    start_time=saved.get("start_time"),
                    tasks_generated=int(saved.get("tasks_generated", 0) or 0),
                    tasks_completed=int(saved.get("tasks_completed", 0) or 0),
                    tasks_valid=int(saved.get("tasks_valid", 0) or 0),
                    tasks_invalid=int(saved.get("tasks_invalid", 0) or 0),
                    current_pass_rate=float(saved.get("pass_rate", 0.0) or 0.0),
                    avg_novelty_score=float(saved.get("avg_novelty_score", 0.0) or 0.0),
                    errors=list(saved.get("errors", []) or []),
                    mode=str(saved.get("mode", "deterministic")),
                    rehydrated=True,
                )
                self._experiments[exp_id] = state
                self._configurations[exp_id] = dict(raw.get("config", {}) or {})
            restored += 1
        if restored:
            logger.info("rehydrated %d experiment(s) from %s", restored, directory)
        return restored

    def _ensure_observability(self, experiment_id: str, config: Dict[str, Any]) -> Any:
        """Create (once) the observability tracker for an experiment.

        Called before the run so the tracker captures the whole execution, and
        kept after completion so `/observability` and `/manifest` stay readable
        (bounded by `_obs_retention`). Safe to call twice: returns the existing
        tracker. Acquires `_lock` -> never call it while already holding it.
        """
        with self._lock:
            existing = self._observability.get(experiment_id)
            if existing is not None:
                return existing
            from experiments.observability import AutopilotObservability
            obs = AutopilotObservability()
            agents_cfg = config.get("agents", [
                {"agent_id": "agent_1", "persona": "existentialist", "role": "advocate"},
                {"agent_id": "agent_2", "persona": "stoic", "role": "skeptic"},
                {"agent_id": "agent_3", "persona": "nihilist", "role": "synthesizer"},
            ])
            obs.start_experiment(
                experiment_id, config,
                prompt=config.get("prompt", ""), agents=agents_cfg,
            )
            self._observability[experiment_id] = obs
            return obs

    def _is_stop_requested(self, experiment_id: str) -> bool:
        """True if a Stop/Delete was requested for this experiment."""
        with self._lock:
            return bool(self._stop_requested.get(experiment_id, False))

    def _persist_results_to_raw(self, experiment_id: str, results: List[Any],
                                mode: str = "deterministic",
                                raw_root: Optional[Path] = None) -> None:
        """Append-only RAW persistence of experiment results.

        Used by BOTH execution modes (deterministic ExperimentRunner and
        AutoPilot/DebateEngine) so every UI-created experiment leaves evidence.

        Stay inside the workspace; expose strictly the deterministic-provenance
        fields (never secrets). This records evidence without mutating the
        deterministic pipeline.

        On a persistence failure the experiment state is marked FAILED (via
        ``add_error``) so the UI can never show a COMPLETED experiment that has
        no RAW evidence -- a P0 integrity rule: an experiment is only COMPLETED
        when its required finalization actually succeeded. ``raw_root`` is
        injectable for tests.
        """
        try:
            from pathlib import Path
            # RAW is written relative to the current working directory so it is
            # portable across source checkout AND wheel install (in a wheel,
            # `__file__` points into site-packages which may be read-only).
            # For the canonical flow the app is started from a writable cwd.
            base = Path(raw_root) if raw_root else (Path.cwd() / "data" / "raw_debates")
            raw_path = base / f"{experiment_id.replace('/', '_')}.jsonl"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            import json as _json
            with open(raw_path, "a", encoding="utf-8") as f:
                # Capture the resolved Settings once per persist call and freeze
                # it into EVERY record (Settings -> experiment -> snapshot -> RAW).
                settings_snapshot = None
                try:
                    from experiments.settings import build_settings_snapshot
                    settings_snapshot = build_settings_snapshot()
                except Exception:  # pragma: no cover
                    settings_snapshot = None
                for r in results:
                    rec = r.to_dict()
                    # Record the runtime execution mode explicitly so RAW proves
                    # which mode actually ran -- no silent fallback.
                    if isinstance(rec, dict):
                        rec.setdefault("metadata", {})
                        rec["metadata"]["execution_mode"] = mode
                        rec["settings_snapshot"] = settings_snapshot
                    f.write(_json.dumps(rec) + "\n")
            logger.info("Persisted %d results to RAW: %s", len(results), raw_path)
        except Exception as exc:
            # P0: NEVER swallow a RAW persistence failure while still reporting
            # the experiment as COMPLETED. Surface it as a visible failure so
            # the derived lifecycle status becomes FAILED, not COMPLETED-without-evidence.
            logger.error("RAW persistence FAILED for %s: %s", experiment_id, exc)
            try:
                self.add_error(experiment_id,
                               f"finalization_failure: RAW persistence failed ({exc})")
            except Exception:  # pragma: no cover - never mask the original
                pass

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get dashboard data for all experiments."""
        with self._lock:
            experiments = {}
            for exp_id, state in self._experiments.items():
                experiments[exp_id] = state.to_dict()

            return {
                "experiments": experiments,
                "total_experiments": len(experiments),
                "running_count": sum(1 for e in experiments.values() if e["is_running"]),
                "timestamp": time.time(),
            }

    def get_observability(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get observability data for an experiment."""
        with self._lock:
            obs = self._observability.get(experiment_id)
            if obs is None:
                return None
            return {
                "config": obs.get_config(),
                "prompt": obs.get_prompt(),
                "agents": {aid: arec.to_dict() for aid, arec in obs.get_agents().items()},
                "events": obs.get_events(limit=200),
                "traces": obs.get_traces(limit=100),
                "progress": obs.get_progress(),
            }

    def export_experiment_manifest(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Export complete experiment manifest for reproducibility.

        After a restart the live observability tracker is gone (events/traces are
        not persisted), but the run summary holds the config and final state. In
        that case we return a manifest that says so explicitly instead of a
        misleading 404 or a manifest that pretends to carry traces.
        """
        with self._lock:
            obs = self._observability.get(experiment_id)
            if obs is not None:
                return obs.export_manifest()

            state = self._experiments.get(experiment_id)
            config = dict(self._configurations.get(experiment_id, {}) or {})
            if state is None:
                return None
            progress = state.to_dict()

        from experiments.reproducibility import (
            build_reproducibility_block,
            manifest_fingerprint,
        )

        reproducibility = build_reproducibility_block(config=config)
        return {
            "experiment_id": experiment_id,
            "prompt": config.get("prompt", ""),
            "config": config,
            "agents": {},
            "events": [],
            "traces": [],
            "progress": progress,
            "reproducibility": reproducibility,
            "reproducibility_fingerprint": manifest_fingerprint(reproducibility),
            "rehydrated": True,
            "note": (
                "Rebuilt from the persisted run summary after a restart: config, "
                "seed and final state are exact; events/traces are not persisted "
                "(the RAW jsonl under data/raw_debates holds the evidence)."
            ),
            "exported_at": time.time(),
        }
