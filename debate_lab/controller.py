"""Debate Lab controller — run registry, lifecycle, events, stop/delete.

Parallel to ``code_lab.controller.CodeLabController``: ONE controller owns the
run registry, the worker thread, the engine instance, the stop flag, status,
events, timeline and provenance for every Debate Lab run.

Lifecycle::

    PENDING -> RUNNING -> STOPPING -> STOPPED
                       -> COMPLETED
                       -> FAILED

Stop is REAL (spec §20): the worker checks the stop flag BEFORE every turn, so
after stop is observed no new moderator/participant/memory cycle begins. Delete
requests stop first, joins the worker with a bounded timeout and refuses
(``DELETE_BLOCKED_ACTIVE_RUN``) if the worker cannot be terminated (spec §21).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import DebateLabConfig, DebateLabConfigError
from .run_store import DebateLabRunStore
from .session_factory import DebateSessionFactory

logger = logging.getLogger("DebateLab.Controller")

DELETE_JOIN_TIMEOUT = 12.0  # seconds to wait for a live worker before refusing delete


class DebateLabRunView:
    """Mutable snapshot of a run's public state (thread-safe via controller lock)."""

    def __init__(self, run_id: str, status: str, config: Dict[str, Any]) -> None:
        self.run_id = run_id
        self.status = status
        self.config = config
        self.created_at = config.get("created_at", "")
        self.started_at: Optional[str] = None
        self.ended_at: Optional[str] = None
        self.events: List[Dict[str, Any]] = []
        self.result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "config": self.config,
            "events": self.events,
            "result": self.result,
            "topic": self.config.get("topic", ""),
            "run_name": self.config.get("run_name", ""),
            "template_id": self.config.get("template_id", ""),
            "max_turns": self.config.get("max_turns", 0),
            "llm_calls": sum(1 for e in self.events
                             if e.get("type") in ("MODERATOR_COMPLETED", "AGENT_RESPONSE")
                             and e.get("selection_mode") != "deterministic_fallback"),
        }


class DebateLabController:
    """Owns all Debate Lab runs in a session; thread-safe."""

    TIMELINE_LIMIT = 500
    # Fields too large to ride on the lab-wide timeline (diagnostic surface).
    _TIMELINE_STRIP = ("response", "challenge", "context", "reason", "result")

    def __init__(
        self,
        factory: Optional[DebateSessionFactory] = None,
        store: Optional[DebateLabRunStore] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self._factory = factory or DebateSessionFactory(base_dir=base_dir)
        self._store = store or DebateLabRunStore(base_dir=base_dir)
        self._runs: Dict[str, DebateLabRunView] = {}
        self._engines: Dict[str, Any] = {}
        self._stop_flags: Dict[str, threading.Event] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._timeline: List[Dict[str, Any]] = []

    # ── run management ─────────────────────────────────────────────────────
    def create_run(self, config: DebateLabConfig) -> DebateLabRunView:
        """Validate + register a new (idle) run. Raises DebateLabConfigError /
        TemplateInvalidForDebate on a controlled config/template error."""
        # Early template-compatibility guard (spec §31): refuse a non-Debate
        # template BEFORE any engine is constructed.
        tpl = self._factory._resolve_template(config.template_id)
        self._factory._ensure_debate_executor(tpl)
        from .validation import validate_debate_template
        validate_debate_template(tpl)

        view = DebateLabRunView(config.run_id, "pending", config.to_dict())
        with self._lock:
            self._runs[config.run_id] = view
        return view

    def start_run(
        self,
        run_id: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        wait: bool = False,
    ) -> bool:
        """Start a run (spawns the owner worker). Returns False if not found or
        already running."""
        with self._lock:
            view = self._runs.get(run_id)
        if view is None:
            return False
        if view.status in ("running", "stopping"):
            return False
        config = DebateLabConfig.from_dict(view.config)
        stop_ev = self._stop_flags.setdefault(run_id, threading.Event())

        def handler(ev: Dict[str, Any]) -> None:
            with self._lock:
                view.events.append(ev)
                self._timeline.append(ev)
                if len(self._timeline) > self.TIMELINE_LIMIT:
                    self._timeline = self._timeline[-self.TIMELINE_LIMIT:]
            if on_event is not None:
                try:
                    on_event(ev)
                except Exception as e:  # pragma: no cover
                    logger.warning("on_event failed: %s", e)

        if wait:
            return self._run_once(run_id, view, config, stop_ev, handler) is not None

        t = threading.Thread(
            target=self._worker, args=(run_id, view, config, stop_ev, handler), daemon=True)
        with self._lock:
            self._threads[run_id] = t
            view.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            view.status = "running"
        t.start()
        return True

    def stop_run(self, run_id: str) -> bool:
        """Request cooperative stop. The worker finalizes current in-flight call
        then refuses any NEW turn."""
        with self._lock:
            view = self._runs.get(run_id)
            stop_ev = self._stop_flags.get(run_id)
        if view is None:
            return False
        if stop_ev is None:
            return False  # not started
        stop_ev.set()
        if view.status == "running":
            view.status = "stopping"
        return True

    def delete_run(self, run_id: str) -> bool:
        """Stop (if running), bounded-join the worker, verify inactive, clean up.

        Returns False (and never removes the run) if the worker cannot be
        terminated — ``DELETE_BLOCKED_ACTIVE_RUN`` (spec §21)."""
        with self._lock:
            view = self._runs.get(run_id)
            stop_ev = self._stop_flags.get(run_id)
            thread = self._threads.get(run_id)
        if view is None:
            return False
        if stop_ev is not None:
            stop_ev.set()
        if thread is not None and thread.is_alive():
            thread.join(DELETE_JOIN_TIMEOUT)
            if thread.is_alive():
                logger.warning("DELETE_BLOCKED_ACTIVE_RUN: %s", run_id)
                return False
        # Worker verified inactive -> safe to clean up + unregister.
        self._store.cleanup(run_id)
        with self._lock:
            self._runs.pop(run_id, None)
            self._engines.pop(run_id, None)
            self._stop_flags.pop(run_id, None)
            self._threads.pop(run_id, None)
        return True

    # ── inspection ─────────────────────────────────────────────────────────
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        view = self._runs.get(run_id)
        if view is None:
            return None
        d = view.to_dict()
        engine = self._engines.get(run_id)
        if engine is not None:
            d["transcript"] = [
                t.to_dict() for t in engine.turn_manager.get_all_turns()
                if (t.response or "").strip()
            ]
        # §63/§83: the CANONICAL conversation, built ONLY from real backend
        # events/results — never reconstructed from a template or workflow.
        provenance = (view.result or {}).get("provenance", {}) if view.result else {}
        d["conversation"] = self._build_conversation(view.events, provenance)
        return d

    # §77: the researcher is a participant — their intervention is a real
    # canonical event and, while the run is active, feeds the live debate
    # context (never silently a fact; always labeled).
    def researcher_message(self, run_id: str, content: str) -> bool:
        with self._lock:
            view = self._runs.get(run_id)
        if view is None or not (content or "").strip():
            return False
        ev = {
            "type": "RESEARCHER_INTERVENTION",
            "time": time.time(),
            "run_id": run_id,
            "author": "researcher",
            "content": content.strip(),
        }
        with self._lock:
            view.events.append(ev)
            self._timeline.append(ev)
            if len(self._timeline) > self.TIMELINE_LIMIT:
                self._timeline = self._timeline[-self.TIMELINE_LIMIT:]
        self._store.append_event(run_id, ev)
        # Feed the live debate: append the note to the engine's short-term
        # context so subsequent moderator/agent calls actually see it.
        engine = self._engines.get(run_id)
        if engine is not None and engine.short_term_memory is not None:
            try:
                engine.short_term_memory.add(
                    turn_id=-1, round_num=0, speaker="Researcher",
                    moderator_question="", response=content.strip())
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("researcher note not fed to context: %s", e)
        return True

    @staticmethod
    def _build_conversation(events, provenance) -> List[Dict[str, Any]]:
        """Derive the ordered conversational transcript from canonical events.

        Entry types (§68): MODERATOR, AGENT_* (argument/hypothesis/critique/
        revision), RESEARCHER_INTERVENTION, MEMORY_CHECKPOINT, SYSTEM_ERROR.
        """
        # role_id -> persona id -> persona display name for identity headers.
        role_persona = {r.get("role_id"): (r.get("default_persona") or "")
                        for r in (provenance.get("effective_roles") or [])}
        personas = provenance.get("effective_personas") or {}
        persona_name = lambda pid: (personas.get(pid) or {}).get("name") or ""

        conv: List[Dict[str, Any]] = []
        for idx, ev in enumerate(events):
            et = ev.get("type", "")
            if et == "MODERATOR_COMPLETED":
                conv.append({
                    "type": "MODERATOR",
                    "speaker": ev.get("actual_speaker") or ev.get("requested_speaker") or "Moderator",
                    "role": "moderator",
                    "persona": "",
                    "model": ev.get("actual_model"),
                    "configured_model": ev.get("configured_model"),
                    "selection_mode": ev.get("selection_mode"),
                    "parse_mode": ev.get("parse_mode"),
                    "challenge": ev.get("challenge") or ev.get("override_reason"),
                    "reason": ev.get("reason"),
                    "requested_speaker": ev.get("requested_speaker"),
                    "time": ev.get("time"),
                    "event_index": idx,
                })
            elif et == "TURN_COMMITTED":
                rid = ev.get("role", "")
                conv.append({
                    "type": ev.get("message_type") or "AGENT_ARGUMENT",
                    "speaker": ev.get("speaker") or "",
                    "role": rid,
                    "persona": persona_name(role_persona.get(rid, "")),
                    "model": ev.get("actual_model"),
                    "configured_model": ev.get("configured_model"),
                    "selection_mode": ev.get("selection_mode"),
                    "turn": ev.get("turn"),
                    "response": ev.get("response") or "",
                    "sections": ev.get("sections") or {},
                    "moderator_challenge": ev.get("moderator_challenge"),
                    "moderator_reason": ev.get("moderator_reason"),
                    "duration": ev.get("duration"),
                    "time": ev.get("time"),
                    "event_index": idx,
                })
            elif et == "RESEARCHER_INTERVENTION":
                conv.append({
                    "type": "RESEARCHER_INTERVENTION",
                    "speaker": "Researcher",
                    "role": "researcher",
                    "persona": "",
                    "content": ev.get("content") or "",
                    "time": ev.get("time"),
                })
            elif et in ("MEMORY_CONSOLIDATION_STARTED", "MEMORY_CONSOLIDATION_COMPLETED",
                        "MEMORY_CONSOLIDATION_FAILED"):
                conv.append({
                    "type": "MEMORY_CHECKPOINT",
                    "speaker": "Memory",
                    "role": "memory",
                    "persona": "",
                    "status": et.replace("MEMORY_CONSOLIDATION_", "").lower(),
                    "memory": ev.get("memory"),
                    "period": ev.get("period"),
                    "time": ev.get("time"),
                })
            elif et == "RUN_FAILED":
                conv.append({
                    "type": "SYSTEM_ERROR",
                    "speaker": "System",
                    "role": "system",
                    "persona": "",
                    "error": ev.get("error") or ev.get("error_type"),
                    "time": ev.get("time"),
                })
        return conv

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._runs[r].to_dict() for r in sorted(self._runs)]

    def get_dashboard_data(self) -> Dict[str, Any]:
        runs = self.list_runs()
        running = sum(1 for r in runs if r["status"] in ("running", "pending", "stopping"))
        return {"total_runs": len(runs), "running_count": running, "runs": runs}

    def get_timeline(self, limit: int = 200) -> Dict[str, Any]:
        with self._lock:
            total = len(self._timeline)
            trimmed = []
            for ev in self._timeline[-limit:]:
                trimmed.append({k: v for k, v in ev.items()
                                if k not in self._TIMELINE_STRIP})
            runs_count = len({ev["run_id"] for ev in self._timeline if "run_id" in ev})
        return {"events": trimmed, "count": total, "total_events": total,
                "runs_count": runs_count}

    # ── worker ─────────────────────────────────────────────────────────────
    def _worker(self, run_id, view, config, stop_ev, handler) -> None:
        try:
            self._run_once(run_id, view, config, stop_ev, handler)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Debate Lab worker crashed for %s", run_id)
            self._emit(handler, view, "RUN_FAILED", run_id=run_id, error=str(exc)[:300],
                       error_type="worker_crash")
            with self._lock:
                view.status = "failed"
                view.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                view.result = {"run_id": run_id, "status": "failed", "error": str(exc)[:300]}
        finally:
            with self._lock:
                self._threads.pop(run_id, None)

    def _run_once(self, run_id, view, config, stop_ev, handler) -> Optional[Dict[str, Any]]:
        """Build the engine and drive the controlled turn loop (spec §18)."""
        session = self._factory.build(config)
        engine = session.engine
        engine.set_lab_event_handler(lambda ev: handler(ev))
        engine.set_model_routing_method(config.model_routing_method)
        with self._lock:
            self._engines[run_id] = engine
            view.status = "running"

        self._emit(handler, view, "RUN_STARTED", run_id=run_id,
                   topic=config.topic, template_id=config.template_id,
                   llm_available=session.provenance.get("llm_available"),
                   model_routing_method=config.model_routing_method,
                   speaker_selection_mode=config.speaker_selection_mode)

        if not engine.start_debate(background=False):
            raise RuntimeError("start_debate refused — engine already running")

        committed = 0
        terminal = None
        stop_requested_at = None
        try:
            while committed < config.max_turns:
                if stop_ev.is_set():
                    stop_requested_at = time.time()
                    self._emit(handler, view, "STOP_REQUESTED", run_id=run_id,
                               requested_at=stop_requested_at,
                               last_committed_turn=committed)
                    terminal = "stopped"
                    break
                success = engine.step_once()
                if success:
                    committed += 1
            if terminal is None:
                terminal = "completed"
        finally:
            engine.stop_debate()

        result = self._build_result(config, session, engine, view, terminal,
                                    committed, stop_requested_at)
        self._store.save_snapshot(run_id, result)
        for ev in list(view.events):
            self._store.append_event(run_id, ev)

        if terminal == "stopped":
            self._emit(handler, view, "RUN_STOPPED", run_id=run_id,
                       last_committed_turn=committed)
        else:
            self._emit(handler, view, "RUN_COMPLETED", run_id=run_id,
                       turns_committed=committed, max_turns=config.max_turns)

        with self._lock:
            view.status = "stopped" if terminal == "stopped" else "completed"
            view.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            view.result = result
        return result

    def _build_result(self, config, session, engine, view, terminal, committed,
                      stop_requested_at) -> Dict[str, Any]:
        transcript = [
            t.to_dict() for t in engine.turn_manager.get_all_turns()
            if (t.response or "").strip()
        ]
        mod_inferences = [e for e in view.events
                          if e.get("type") == "MODERATOR_COMPLETED"
                          and e.get("selection_mode") != "deterministic_fallback"]
        part_inferences = [e for e in view.events if e.get("type") == "AGENT_RESPONSE"]
        errors = [e for e in view.events if e.get("type") == "RUN_FAILED"]
        started_at = view.started_at or ""
        ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        duration = None
        if started_at:
            try:
                import datetime as _dt
                s = _dt.datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%S")
                e = _dt.datetime.strptime(ended_at, "%Y-%m-%dT%H:%M:%S")
                duration = round((e - s).total_seconds(), 2)
            except Exception:  # pragma: no cover
                duration = None
        return {
            "run_id": config.run_id,
            "status": "completed" if terminal == "completed" else "stopped",
            "execution_status": "COMPLETED" if terminal == "completed" else "STOPPED",
            # An ordinary open debate has NO scientific validator: PASS/FAIL are
            # only shown when a real configured validator produced them (§36).
            "validation_status": "NOT_CONFIGURED",
            "topic": config.topic,
            "run_name": config.run_name,
            "template_id": config.template_id,
            "turns_committed": committed,
            "max_turns": config.max_turns,
            "terminal_reason": ("max_turns_reached" if terminal == "completed"
                                else "user_stop"),
            "stop_requested_at": stop_requested_at,
            "last_committed_turn": committed,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration,
            "llm_calls": len(mod_inferences) + len(part_inferences),
            "provenance": session.provenance,
            "transcript": transcript,
            "moderator_inferences": mod_inferences,
            "participant_inferences": part_inferences,
            "errors": [e.get("error") for e in errors][:20],
        }

    @staticmethod
    def _emit(handler, view, event_type: str, **payload) -> None:
        handler({"type": event_type, "time": time.time(), **payload})
