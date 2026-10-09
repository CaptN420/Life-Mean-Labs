"""Core debate engine that orchestrates the philosophical discussion."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Optional

from .constants import SPEAKER_TO_ROLE, VALID_SPEAKERS
from .debate_state import DebateState as StateDataclass
from .events import (
    DebateState,
    DebateUpdate,
    ErrorEvent,
    MemoryEvent,
    ModeratorEvent,
    TurnEvent,
)
from .turn_manager import TurnManager

# Lazy import to avoid circular imports
_raw_recorder = None


def _get_raw_recorder():
    """Get or create the RAW recorder."""
    global _raw_recorder
    if _raw_recorder is None:
        try:
            from philosophical_council.raw_protocol import RawDebateRecorder
            _raw_recorder = RawDebateRecorder()
        except Exception:
            pass
    return _raw_recorder

logger = logging.getLogger(__name__)


class DebateEngine:
    """Main engine that orchestrates the philosophical debate."""

    def __init__(self, config: Any, database: Any, llm_client: Any) -> None:
        self.config = config
        self.db = database
        self.llm = llm_client
        self.turn_manager = TurnManager()
        self._state = StateDataclass(topic=config.debate.topic)

        # Agent registry - maps role to agent
        self._agents: dict[str, Any] = {}
        # Maps speaker name to agent (for direct lookup)
        self._speaker_map: dict[str, Any] = {}
        self._moderator: Optional[Any] = None

        # Callbacks for GUI updates
        self._callbacks: list[Callable[[DebateUpdate], None]] = []

        # Background thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Memory references (set by UI or elsewhere)
        self.short_term_memory: Any = None
        self.mid_term_memory: Any = None
        self.long_term_memory: Any = None
        self.consolidator: Any = None
        
        # NEW: Enhanced debate state for intelligent moderation
        from philosophical_council.memory.debate_state import DebateState as ArgumentDebateState
        self.argument_state = ArgumentDebateState(topic=config.debate.topic)

        # Speaker history for repetition detection
        self._recent_speakers: list[str] = []
        self._conceptual_level: int = 1

        # RAW experiment ID (initialized to None, set in start_debate)
        self._raw_experiment_id = None

        logger.info("Debate engine initialized")

    def register_agent(self, agent: Any) -> None:
        """Register a philosophical agent."""
        self._agents[agent.role] = agent
        # Also map by speaker name if available
        speaker_name = agent.config.name
        if speaker_name:
            self._speaker_map[speaker_name] = agent
        logger.info("Registered agent: %s (role: %s)", agent.name, agent.role)

    def register_moderator(self, moderator: Any) -> None:
        """Register the moderator agent."""
        self._moderator = moderator
        logger.info("Registered moderator")

    def add_callback(self, callback: Callable[[DebateUpdate], None]) -> None:
        """Add a callback for debate updates."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[DebateUpdate], None]) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify(self, update: DebateUpdate) -> None:
        """Notify all callbacks of an update."""
        for cb in self._callbacks:
            try:
                cb(update)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    def _log_turn_failure(self, turn, speaker: str, message: str, duration: float) -> None:
        """Append-only record of a failed/empty turn (AGENT RULE 7).

        Kept separate from the debate's success-turn state so a phantom turn
        is observable (log evidence) without ever polluting real debate data.
        Writes to the RAW debate log/experiment when available; never mutates
        turn_manager, agent memory, argument state, or the DB.
        """
        failure_line = {
            "event": "turn_failed",
            "reason": "empty_response" if "empty response" in message.lower() else "turn_error",
            "turn_id": getattr(turn, "turn_id", None),
            "round_num": getattr(turn, "round_num", None),
            "speaker": speaker,
            "message": message,
            "duration_seconds": round(duration, 3),
        }
        # Route into the debate's own logger (observable, append-only).
        logger.error("TURN FAILED %s", failure_line)
        # Best-effort RAW persistence: if a raw debate exporter is wired,
        # record the failure trajectory there too.
        try:
            raw_recorder = _get_raw_recorder()
            if raw_recorder is not None and hasattr(raw_recorder, "append_turn_failure"):
                raw_recorder.append_turn_failure(
                    experiment_id=self._raw_experiment_id,
                    failure=failure_line,
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("RAW failure log unavailable: %s", exc)

    def start_debate(self) -> bool:
        """Start the debate."""
        if self._state.status == "running":
            logger.warning("Debate already running")
            return False

        # Create new debate in database
        debate_id = self.db.debate_repo.create_debate(self.config.debate.topic)
        self.set_debate_id(debate_id)
        self._state = StateDataclass(topic=self.config.debate.topic)

        # Initialize RAW recorder for this experiment
        self._raw_experiment_id = None
        raw_recorder = _get_raw_recorder()
        if raw_recorder:
            self._raw_experiment_id = raw_recorder.start_experiment(
                task_id=f"debate_{debate_id}",
                dataset_source="philosophical_council",
            ).experiment_id
            # Record input
            raw_recorder.record_input(
                self._raw_experiment_id,
                raw_prompt=self.config.debate.topic,
                language="en",
                constraints=["philosophical"],
            )

        # Reset argument state
        from philosophical_council.memory.debate_state import DebateState as ArgumentDebateState
        self.argument_state = ArgumentDebateState(topic=self.config.debate.topic)

        # Register agents in database
        for role, agent in self._agents.items():
            self.db.debate_repo.__class__(self.db.db_path).insert_agent(
                debate_id, role, agent.name, agent.system_prompt[:200],
                agent.config.model or "", agent.color
            )

        self._running = True
        self._state.start()
        self._notify(DebateUpdate(state=DebateState.RUNNING))

        # Start background thread
        self._thread = threading.Thread(target=self._debate_loop, daemon=True)
        self._thread.start()
        logger.info("Debate started in background thread")
        return True

    def pause_debate(self) -> None:
        """Pause the debate."""
        self._state.pause()
        self._notify(DebateUpdate(state=DebateState.PAUSED))

    def resume_debate(self) -> None:
        """Resume the debate."""
        self._state.resume()
        self._notify(DebateUpdate(state=DebateState.RUNNING))

    def stop_debate(self) -> None:
        """Stop the debate."""
        self._state.stop()
        self._running = False
        self.db.debate_repo.finish_debate(self._get_debate_id())

        # Save RAW data if available
        raw_recorder = _get_raw_recorder()
        if raw_recorder and self._raw_experiment_id:
            try:
                raw_recorder.end_experiment(self._raw_experiment_id)
                raw_recorder.save_experiment(self._raw_experiment_id)
                logger.info("RAW debate data saved for experiment %s", self._raw_experiment_id)
            except Exception as exc:
                logger.warning("Failed to save RAW data: %s", exc)

        self._notify(DebateUpdate(state="stopped"))

    def step_once(self) -> bool:
        """Execute a single turn."""
        if self._state.status != "running":
            logger.warning("Cannot step: debate not running")
            return False

        try:
            # Get moderator decision
            decision = self._get_moderator_decision()
            if not decision:
                return False

            # Validate and resolve speaker
            selected_name = decision.get("selected_speaker", "")
            agent = self._resolve_agent(selected_name)
            if agent is None:
                logger.error("Failed to resolve agent for: %s", selected_name)
                return False

            # Update recent speakers and argument state
            self._recent_speakers.append(selected_name)
            if len(self._recent_speakers) > 10:
                self._recent_speakers = self._recent_speakers[-10:]

            # Track consecutive turns
            if self.argument_state.consecutive_speaker == selected_name:
                self.argument_state.consecutive_count += 1
            else:
                self.argument_state.consecutive_speaker = selected_name
                self.argument_state.consecutive_count = 1

            # Track this turn in argument state
            self.argument_state.add_turn(
                turn_id=self.turn_manager.current_turn_id,
                speaker=selected_name,
                response="",  # Will be filled after response generated
                argument_type="claim",
            )

            # Execute the turn
            turn = self.turn_manager.next_turn(
                speaker=selected_name,
                speaker_role=agent.role,
                moderator_question=decision.get("challenge"),
                moderator_reason=decision.get("reason"),
            )

            # Save moderator decision
            self.db.moderator_repo.insert(
                debate_id=self._get_debate_id(),
                turn_id=turn.turn_id,
                round_num=turn.round_num,
                selected_speaker=selected_name,
                challenge=decision.get("challenge"),
                reason=decision.get("reason"),
                question=decision.get("question"),
                detected_issues=decision.get("detected_issues"),
            )

            # Get agent response with continuation support
            context = self._build_context(turn)
            
            # Pass additional context about previous speaker and arguments
            last_speaker = self._recent_speakers[-2] if len(self._recent_speakers) >= 2 else None
            prompt = agent.format_response(
                decision["challenge"], 
                context,
                previous_speaker=last_speaker,
            )
            model = agent.config.model or ""
            max_tokens = getattr(self.config.debate, 'philosopher_max_tokens', 1500)
            start_time = time.time()

            response, finish_reason, continuation_count = self._generate_with_continuation(
                messages=[
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=self.config.debate.temperature,
                max_tokens=max_tokens,
            )
            duration = time.time() - start_time

            # ── EMPTY-RESPONSE GUARD (AGENT RULE 7) ────────────────────────
            # Never treat an empty/whitespace model response as a successful
            # turn. This guard runs BEFORE complete_turn(), agent history
            # mutation, argument-state mutation, DB persistence and memory
            # persistence, so a phantom turn never pollutes debate state.
            if not response or not response.strip():
                error_msg = (
                    f"Agent '{selected_name}' returned an empty response on "
                    f"turn {turn.turn_id} (round {turn.round_num}). Turn marked "
                    f"FAILED; no history/argument/db/memory mutation applied. "
                    f"model={model!r} finish={finish_reason!r}"
                )
                logger.error("PHANTOM TURN PREVENTED: %s", error_msg)
                # Log the failure (rule 7: log_failure) — observable, append-only.
                try:
                    self._log_turn_failure(turn, selected_name, error_msg, duration)
                except Exception as exc:  # pragma: no cover
                    logger.warning("Could not record turn failure: %s", exc)
                # Notify listeners that the turn failed (never a success).
                self._notify(DebateUpdate(
                    state=DebateState.RUNNING,
                    error=ErrorEvent(
                        error_type="empty_response",
                        message=error_msg,
                        turn_id=turn.turn_id,
                    ),
                ))
                # recover_or_retry: skip this turn, keep debate running. Do NOT
                # call complete_turn / add_to_history / argument_state / db /
                # memory — prevent the phantom turn entirely (kernel-failure
                # turns must not corrupt debate turns or inject phantom
                # claims into the argument state). Roll back the optimistic
                # reservation so turn_count/speaker/recent are unchanged.
                self.argument_state.rollback_reserved_turn(selected_name)
                self._recent_speakers.append(selected_name)  # don't re-select repeatedly
                return False

            # Complete the turn
            self.turn_manager.complete_turn(turn.turn_id, response, duration)
            agent.add_to_history(response)
            
            # Update argument state with actual response
            self.argument_state.add_turn(
                turn_id=turn.turn_id,
                speaker=selected_name,
                response=response,
                argument_type="claim",
                responding_to=last_speaker,
            )

            # Check turn quality and detect repetition
            if hasattr(self.argument_state, 'check_turn_quality'):
                quality = self.argument_state.check_turn_quality(
                    selected_name, response, last_speaker
                )
                logger.info("TURN QUALITY: %s", quality)

                # If repetition detected, log warning
                if quality.get('repetition_detected'):
                    logger.warning("REPETITION DETECTED for %s - consider regeneration", selected_name)

            # Save to database with finish info
            self.db.turn_repo.insert_turn(
                debate_id=self._get_debate_id(),
                turn_id=turn.turn_id,
                round_num=turn.round_num,
                speaker=selected_name,
                speaker_role=agent.role,
                response=response,
                moderator_question=turn.moderator_question,
                moderator_reason=turn.moderator_reason,
                model=model,
                duration_seconds=duration,
                finish_reason=finish_reason,
                was_truncated=finish_reason == "length",
                continuation_count=continuation_count,
            )

            # Update short-term memory
            if self.short_term_memory:
                self.short_term_memory.add(
                    turn.turn_id, turn.round_num, selected_name,
                    turn.moderator_question, response
                )

            # Notify GUI about memory update
            self._notify(DebateUpdate(
                state=DebateState.RUNNING,
                memory=MemoryEvent(
                    event_type="short_term",
                    details=self.short_term_memory.get_context() if self.short_term_memory else "(No memory)",
                ),
            ))

            # Periodic mid-term consolidation
            if self.consolidator and turn.turn_id % self.config.debate.mid_term_interval == 0:
                recent = self.turn_manager.get_recent_turns(10)
                period = f"turns {turn.turn_id - 9}-{turn.turn_id}"
                self.consolidator.consolidate_mid_term(
                    [{"turn_id": t.turn_id, "speaker": t.speaker, "response": t.response} for t in recent],
                    period,
                    self.llm,
                )

            # Phase management: advance phases based on debate progress
            if turn.turn_id % 5 == 0 and hasattr(self.argument_state, 'current_phase'):
                self._manage_phases()

            # Periodic long-term consolidation
            if self.consolidator and turn.turn_id % self.config.debate.long_term_interval == 0:
                self.consolidator.consolidate_long_term(
                    self.mid_term_memory.get_entries() if self.mid_term_memory else [],
                    self.llm,
                )

            # Notify GUI
            self._notify(DebateUpdate(
                state=DebateState.RUNNING,
                turn=TurnEvent(
                    turn_id=turn.turn_id,
                    round_num=turn.round_num,
                    speaker=selected_name,
                    speaker_role=agent.role,
                    response=response,
                    moderator_question=turn.moderator_question,
                    moderator_reason=turn.moderator_reason,
                    model=model,
                    duration_seconds=duration,
                    finish_reason=finish_reason,
                    was_truncated=finish_reason == "length",
                ),
                moderator=ModeratorEvent(
                    turn_id=turn.turn_id,
                    round_num=turn.round_num,
                    selected_speaker=selected_name,
                    challenge=decision["challenge"],
                    reason=decision["reason"],
                    question=decision.get("question"),
                    detected_issues=decision.get("detected_issues"),
                ),
                stats={
                    "turn_id": turn.turn_id,
                    "round": turn.round_num,
                    "total_turns": self.turn_manager.turn_count,
                },
            ))

            logger.info(
                "TURN %d | MODERATOR SELECTED: %s | ACTUAL AGENT CALLED: %s | FINISH: %s | TRUNCATED: %s",
                turn.turn_id, selected_name, agent.name, finish_reason, finish_reason == "length"
            )

            # Record RAW data
            raw_recorder = _get_raw_recorder()
            if raw_recorder and self._raw_experiment_id:
                try:
                    # Record agent call
                    raw_recorder.record_agent_call(
                        self._raw_experiment_id,
                        agent_id=agent.role,
                        role=agent.config.name or agent.role,
                        input_sent=decision.get("challenge", ""),
                        output_received=response,
                        status="success" if finish_reason == "stop" else "error",
                        tokens_input=len(prompt.split()) // 5,  # Rough estimate
                        tokens_output=len(response.split()),
                        duration_seconds=duration,
                    )
                    # Record debate event
                    raw_recorder.record_debate_event(
                        self._raw_experiment_id,
                        event_type="proposal",
                        agent_id=agent.role,
                        content=response[:500],  # Truncate for storage
                        round_num=turn.round_num,
                    )
                except Exception as rec_exc:
                    logger.warning("RAW recording failed: %s", rec_exc)

            return True

        except Exception as exc:
            logger.error("Turn execution failed: %s", exc)
            self._state.record_error(str(exc))
            self._notify(DebateUpdate(
                state=DebateState.ERROR,
                error=ErrorEvent(error_type="turn_error", message=str(exc)),
            ))
            return False

    def _resolve_agent(self, speaker_name: str) -> Optional[Any]:
        """Resolve a speaker name to the actual agent."""
        # Try exact match first
        if speaker_name in self._speaker_map:
            return self._speaker_map[speaker_name]

        # Try case-insensitive match
        for name, agent in self._speaker_map.items():
            if name.lower() == speaker_name.lower():
                return agent

        # Try role mapping
        if speaker_name.lower() in SPEAKER_TO_ROLE:
            role = SPEAKER_TO_ROLE[speaker_name.lower()]
            if role in self._agents:
                return self._agents[role]

        logger.error("Unknown speaker selected: %s", speaker_name)
        return None

    def _generate_with_continuation(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        generation_id: Optional[str] = None,
    ) -> tuple[str, str, int]:
        """Generate response with continuation ONLY if finish_reason=='length'.

        Returns (response_text, finish_reason, continuation_count).
        """
        import uuid as uuid_module

        max_attempts = getattr(self.config.debate, 'max_continuations', 2)
        full_response = ""
        finish_reason = "stop"
        continuation_count = 0
        call_count = 0

        # Generate unique generation ID if not provided
        if not generation_id:
            import uuid as uuid_module
            generation_id = f"{self._get_debate_id()}-{self.turn_manager.current_turn_id}-{uuid_module.uuid4().hex[:8]}"

        logger.info("GENERATION ID: %s | CALL TYPE: initial", generation_id)

        for attempt in range(max_attempts + 1):
            call_count += 1
            logger.info("MODEL CALL #%d (attempt %d)", call_count, attempt)

            if attempt == 0:
                response_text, finish_reason = self.llm.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                logger.info("INITIAL GENERATION | FINISH_REASON: %s | RESPONSE_LENGTH: %d", finish_reason, len(response_text))
            else:
                # Continue generation - ONLY called when finish_reason == "length"
                continuation_prompt = (
                    "Continue your previous response from exactly where it stopped. "
                    "Do not restart. Do not repeat the previous paragraphs. "
                    "Complete the unfinished argument."
                )
                response_text, finish_reason = self.llm.chat(
                    messages=messages + [{"role": "user", "content": continuation_prompt}],
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens // 2,
                )
                logger.info("CONTINUATION #%d | FINISH_REASON: %s | RESPONSE_LENGTH: %d", continuation_count, finish_reason, len(response_text))

            full_response += response_text

            # CRITICAL: Only stop continuing if finish_reason is "stop"
            # If finish_reason is "length", continue (up to max_attempts)
            if finish_reason == "stop":
                logger.info("STOP condition met - no further continuation")
                break
            elif finish_reason == "length" and continuation_count < max_attempts:
                logger.warning("Response truncated (finish_reason=length), continuing...")
                continuation_count += 1
            else:
                logger.warning("Unexpected finish_reason: %s", finish_reason)
                break

        # Validate call count
        assert call_count <= max_attempts + 1, f"BUG: Too many model calls ({call_count})"

        logger.info("GENERATION COMPLETE | ID: %s | CALLS: %d | CONTINUATIONS: %d | FINISH: %s",
                   generation_id, call_count, continuation_count, finish_reason)

        return full_response.strip(), finish_reason, continuation_count

    def _debate_loop(self) -> None:
        """Main debate loop running in background thread."""
        logger.info("Debate loop started")
        while self._running and self._state.status == "running":
            success = self.step_once()
            if not success:
                time.sleep(1)  # Back off on error

        logger.info("Debate loop ended")

    def _get_moderator_decision(self) -> Optional[dict[str, str]]:
        """Get the next moderator decision with validation and repetition prevention."""
        if self._moderator is None:
            return None

        # Build comprehensive context including argument state
        context = self._build_context(None)
        
        # Get speaker statistics for the moderator prompt
        speaker_stats = []
        for speaker, count in self.argument_state.speaker_turn_count.items():
            speaker_stats.append(f"- {speaker}: {count} turns")
        stats_text = "\n".join(speaker_stats) if speaker_stats else "(No speakers yet)"
        
        # Check for repetition patterns
        recent = self._recent_speakers[-5:] if self._recent_speakers else []
        repetition_info = ""
        if recent:
            from collections import Counter
            counts = Counter(recent)
            repeat_speaker = max(counts, key=counts.get) if counts else None
            if counts[repeat_speaker] >= 2:
                repetition_info = (
                    f"CRITICAL REPETITION WARNING: '{repeat_speaker}' has spoken "
                    f"{counts[repeat_speaker]} times in the last {len(recent)} turns. "
                    f"YOU MUST SELECT A DIFFERENT SPEAKER. This is not optional."
                )
        
        # Get alternatives based on argument state
        alternatives = self.argument_state.get_alternatives()
        alt_text = ", ".join(alternatives[:4]) if alternatives else "All philosophers"
        
        prompt = f"""{self._moderator.system_prompt}

Current debate topic: {self.config.debate.topic}

SPEAKER STATISTICS (must avoid over-representation):
{stats_text}

RECENT SPEAKERS (last {len(recent)} turns): {', '.join(recent) if recent else 'None'}

AVAILABLE ALTERNATIVES (sorted by relevance): {alt_text}

{repetition_info}

Current debate context:
{context}

Return ONLY valid JSON. No markdown. No ```json fences. No commentary before or after the JSON.
Your response must be a single JSON object with these fields:
- selected_speaker: One of: Existentialist, Stoic, Nihilist, Spiritual, Skeptic, Pragmatist
- challenge: A specific philosophical challenge (at least 50 characters) that addresses the current state of the debate
- reason: Why this choice was made, considering who hasn't spoken recently and what needs to be addressed
- question: Optional deeper question to explore (can be null)
- detected_issues: Any issues detected in the debate (can be null)

IMPORTANT RULES:
1. NEVER select a speaker who has already spoken consecutively (unless no alternatives exist)
2. PREFER speakers who haven't spoken recently
3. Address specific unresolved objections or questions
4. Break repetition by selecting someone with a different perspective

Example: {{"selected_speaker": "Nihilist", "challenge": "You argued that meaning is subjective, but the Stoic just pointed out that this creates a paradox where your position itself has no basis. How do you respond?", "reason": "The Nihilist needs to address the logical contradiction raised by the Stoic.", "question": null, "detected_issues": "Logical contradiction in nihilist's position"}}"""

        # Try with validation and retry
        for attempt in range(3):
            try:
                logger.info("MODERATOR REQUEST | Attempt %d | Model: %s", attempt + 1, self._moderator.config.model or "")
                response, finish_reason = self.llm.chat(
                    messages=[
                        {"role": "system", "content": self._moderator.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=self._moderator.config.model or "",
                    temperature=0.5,
                    max_tokens=getattr(self.config.debate, 'moderator_max_tokens', 300),
                )
                logger.info("MODERATOR RESPONSE | Length: %d | Finish Reason: %s", len(response), finish_reason)

                decision = self._moderator.parse_decision(response)

                # Validate the decision
                if self._validate_moderator_decision(decision):
                    logger.info("MODERATOR DECISION: %s selected by %s", decision.get('selected_speaker'), decision.get('reason', '')[:50])
                    return decision

                logger.warning("Moderator decision failed validation: %s", decision)

            except Exception as exc:
                logger.error("Moderator decision attempt %d failed: %s", attempt, exc)

        # Final fallback - deterministic but specific challenge
        logger.error("All moderator retries failed. Using deterministic fallback.")
        return self._get_deterministic_fallback()

    def _validate_moderator_decision(self, decision: dict[str, str]) -> bool:
        """Validate moderator decision has required fields and valid speaker."""
        if not decision:
            return False

        selected = decision.get("selected_speaker", "")
        if selected not in VALID_SPEAKERS:
            logger.error("Invalid speaker in moderator decision: %s", selected)
            return False

        challenge = decision.get("challenge", "")
        if not challenge or challenge == "Continue the discussion.":
            logger.error("Invalid or missing challenge in moderator decision")
            return False

        reason = decision.get("reason", "")
        if not reason:
            logger.error("Missing reason in moderator decision")
            return False

        return True

    def _get_deterministic_fallback(self) -> dict[str, str]:
        """Get a deterministic fallback when moderator fails.

        Uses enhanced DebateState to produce specific, context-aware challenges.
        NEVER uses generic fallback phrases.
        """
        # Choose based on recent speakers to avoid repetition
        recent = self._recent_speakers[-3:] if self._recent_speakers else []
        last_speaker = recent[-1] if recent else None

        # Pick a different speaker intelligently using argument state
        alternatives = self.argument_state.get_alternatives(exclude=last_speaker)
        fallback_speaker = alternatives[0] if alternatives else "Existentialist"

        # Try to find unresolved objections or questions
        unresolved_objection = None
        if hasattr(self.argument_state, 'get_strongest_unresolved_objection'):
            unresolved_objection = self.argument_state.get_strongest_unresolved_objection()

        # Try to get the latest turn's response for context
        latest_turn = None
        try:
            if getattr(self.turn_manager, 'turn_count', 0) > 0:
                all_turns = self.turn_manager.get_all_turns()
                latest_turn = all_turns[-1] if all_turns else None
        except (AttributeError, TypeError):
            pass

        # Build a specific challenge based on available context
        # Priority 1: Use unresolved objection
        if unresolved_objection and hasattr(unresolved_objection, 'content'):
            challenge = (
                f"An unresolved objection was raised: '{unresolved_objection.content[:150]}...' "
                f"Please address this specific concern."
            )
        # Priority 2: Use latest turn context
        elif latest_turn and latest_turn.response:
            response_preview = latest_turn.response[:200].strip()
            challenge = (
                f"Respond to {latest_turn.speaker}'s argument. "
                f"Their key claim was: '{response_preview}...' "
                f"Provide a specific counterpoint or extension."
            )
        # Priority 3: Use thread context
        elif self.argument_state.threads and self.argument_state.active_thread_id in self.argument_state.threads:
            thread = self.argument_state.threads[self.argument_state.active_thread_id]
            if thread.central_question:
                challenge = (
                    f"The debate is currently focused on: '{thread.central_question}'. "
                    f"Please contribute a new perspective or advance the discussion."
                )
        # Priority 4: Use phase-aware challenge
        elif hasattr(self.argument_state, 'current_phase'):
            phase = self.argument_state.current_phase
            if phase == "construction":
                challenge = (
                    f"Now that we've explored the limitations, "
                    f"please propose a constructive solution based on your position."
                )
            elif phase == "saturation":
                challenge = (
                    f"This issue has been sufficiently explored. "
                    f"Please help us move forward to a deeper question."
                )
            else:
                challenge = (
                    f"What does {fallback_speaker.lower()} make of the question "
                    f"'What is the meaning of life?' in light of the current debate?"
                )
        else:
            # Last resort - very specific challenge
            challenge = (
                f"What unique contribution can {fallback_speaker.lower()} make "
                f"that hasn't already been addressed in this debate?"
            )

        return {
            "selected_speaker": fallback_speaker,
            "challenge": challenge,
            "reason": "Moderator recovery fallback - deterministic speaker selection.",
            "question": None,
            "detected_issues": "Moderator failed to produce valid JSON after retries.",
        }

    def _build_context(self, current_turn: Optional[Any]) -> str:
        """Build context for LLM prompts."""
        parts = []

        # Short-term memory
        if self.short_term_memory:
            parts.append(self.short_term_memory.get_context())

        # Mid-term memory
        if self.mid_term_memory:
            mid = self.mid_term_memory.get_context()
            if mid and "(No mid-term" not in mid:
                parts.append(mid)

        # Long-term memory
        if self.long_term_memory:
            lt = self.long_term_memory.get_context()
            if lt and "(No long-term" not in lt:
                parts.append(lt)
        
        # Add argument state summary
        if self.argument_state.turn_count > 0:
            parts.append(self._build_argument_summary())

        return "\n\n".join(parts) if parts else "(No context available)"
    
    def _build_argument_summary(self) -> str:
        """Build a summary of arguments for the prompt context."""
        # Use enhanced DebateState methods if available
        if hasattr(self.argument_state, 'build_moderator_context'):
            return self.argument_state.build_moderator_context()
        
        # Fallback to legacy format
        lines = ["ARGUMENT STATE SUMMARY:"]
        
        # Show speaker distribution
        lines.append("\nSPEAKER DISTRIBUTION:")
        for speaker, count in sorted(
            self.argument_state.speaker_turn_count.items(), 
            key=lambda x: x[1], 
            reverse=True
        ):
            lines.append(f"  - {speaker}: {count} turns")
        
        # Show recent claims
        if hasattr(self.argument_state, 'recent_claims') and self.argument_state.recent_claims:
            lines.append("\nRECENT CLAIMS:")
            for claim in self.argument_state.recent_claims[-5:]:
                lines.append(f"  Turn {claim.turn_id} ({claim.speaker}): {claim.content[:100]}...")
        
        # Show unresolved questions
        if hasattr(self.argument_state, 'unresolved_questions') and self.argument_state.unresolved_questions:
            lines.append("\nUNRESOLVED QUESTIONS:")
            for q in self.argument_state.unresolved_questions[-3:]:
                lines.append(f"  - {q}")
        
        return "\n".join(lines)

    def _get_debate_id(self) -> int:
        """Get current debate ID."""
        if not hasattr(self, '_debate_id'):
            self._debate_id = 1
        return self._debate_id

    def set_debate_id(self, debate_id: int) -> None:
        """Set the current debate ID after creation."""
        self._debate_id = debate_id

    def _manage_phases(self) -> None:
        """Manage debate phase transitions based on progress."""
        state = self.argument_state
        if not hasattr(state, 'current_phase'):
            return

        current = state.current_phase

        # Phase transition logic
        if current == "exploration":
            # Move to destruction after enough turns
            if state.turn_count >= 5:
                state.advance_phase("destruction")

        elif current == "destruction":
            # Check for saturation - have we explored objections enough?
            if state.check_saturation() or state.turn_count >= 10:
                state.advance_phase("saturation")

        elif current == "saturation":
            # Move to construction when saturation reached
            state.advance_phase("construction")

        elif current == "construction":
            # After proposals, move to stress test
            if state.turn_count >= 15:
                state.advance_phase("stress_test")

        elif current == "stress_test":
            # Move to revision
            if state.turn_count >= 18:
                state.advance_phase("revision")

        elif current == "revision":
            # Final synthesis
            state.advance_phase("synthesis")
