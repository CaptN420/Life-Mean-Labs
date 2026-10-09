"""Debate test archive system for persistent logging.

This module provides incremental logging of debate tests to a persistent
archive file, enabling comparison and analysis of different orchestration
versions.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ARCHIVE_FILENAME = "debate_test_archive.txt"


class DebateArchive:
    """Manages persistent logging of debate tests."""
    
    def __init__(self, archive_path: Optional[str] = None) -> None:
        if archive_path:
            self.archive_path = Path(archive_path)
        else:
            # Default to project root
            self.archive_path = Path(__file__).parent.parent / ARCHIVE_FILENAME
        
        self._ensure_file_exists()
    
    def _ensure_file_exists(self) -> None:
        """Create archive file if it doesn't exist."""
        if not self.archive_path.exists():
            self.archive_path.touch()
            logger.info("Created debate test archive: %s", self.archive_path)
    
    def start_test(
        self,
        topic: str,
        agents: list[str],
        max_turns: int,
        test_type: str = "manual",
        code_version: Optional[str] = None,
        git_commit: Optional[str] = None,
    ) -> str:
        """Start a new test and return the test ID."""
        now = datetime.now()
        test_id = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        header = f"""
================================================================================
DEBATE TEST
================================================================================

TEST_ID: {test_id}

DATE: {now.strftime('%Y-%m-%d')}
TIME: {now.strftime('%H:%M:%S')}

TOPIC:
{topic}

CONFIGURATION:
Number of agents: {len(agents)}
Agents:
"""
        for agent in agents:
            header += f"  - {agent}\n"
        
        header += f"""
MAX_TURNS: {max_turns}

TEST_TYPE: {test_type}

CODE_VERSION: {code_version or 'unknown'}
GIT_COMMIT: {git_commit or 'unknown'}

================================================================================
DEBATE TRANSCRIPT
================================================================================
"""
        
        self._append(header)
        logger.info("Started debate test %s", test_id)
        return test_id
    
    def log_turn(
        self,
        turn_id: int,
        speaker: str,
        responding_to: Optional[str],
        thread_id: str,
        target_claim: Optional[str],
        main_argument: Optional[str],
        response: str,
        new_claim: Optional[str],
        objection: Optional[str],
        concession: Optional[str],
        position_changed: bool,
        state_changed: bool,
        quality_score: float,
    ) -> None:
        """Log a single turn to the archive."""
        entry = f"""
TURN {turn_id}

SPEAKER: {speaker}

RESPONDING_TO:
{responding_to or 'Moderator'}

THREAD:
{thread_id}

TARGET_CLAIM:
{target_claim or 'N/A'}

MAIN_ARGUMENT:
{main_argument or 'N/A'}

RESPONSE:
{response}

NEW_CLAIM:
{new_claim or 'N/A'}

OBJECTION:
{objection or 'N/A'}

CONCESSION:
{concession or 'N/A'}

POSITION_CHANGED:
{position_changed}

STATE_CHANGED:
{state_changed}

QUALITY_SCORE:
{quality_score:.2f}

--------------------------------------------------------------------------------
"""
        self._append(entry)
    
    def log_error(
        self,
        turn_id: int,
        error_type: str,
        error_message: str,
        recovery_attempted: bool = True,
        recovery_result: Optional[str] = None,
    ) -> None:
        """Log an error that occurred during the debate."""
        entry = f"""
================================================================================
ERROR
================================================================================

TURN: {turn_id}

ERROR_TYPE:
{error_type}

ERROR_MESSAGE:
{error_message}

RECOVERY_ATTEMPTED:
{recovery_attempted}

RECOVERY_RESULT:
{recovery_result or 'N/A'}

================================================================================
"""
        self._append(entry)
    
    def log_fallback(
        self,
        fallback_type: str,
        fallback_reason: str,
        fallback_action: str,
        fallback_success: bool,
    ) -> None:
        """Log a fallback that was triggered."""
        entry = f"""
================================================================================
FALLBACK_TRIGGERED
================================================================================

FALLBACK_TYPE:
{fallback_type}

FALLBACK_REASON:
{fallback_reason}

FALLBACK_ACTION:
{fallback_action}

FALLBACK_SUCCESS:
{fallback_success}

================================================================================
"""
        self._append(entry)
    
    def log_final_state(
        self,
        threads: dict[str, str],
        agent_positions: dict[str, str],
        position_revisions: list[dict],
        unresolved_questions: list[str],
        constructive_proposals: list[str],
    ) -> None:
        """Log the final debate state."""
        lines = ["\n================================================================================", "FINAL DEBATE STATE", "================================================================================"]
        
        # Active threads
        lines.append("\nACTIVE THREADS:\n")
        for thread_id, status in threads.items():
            lines.append(f"THREAD: {thread_id}")
            lines.append(f"STATUS: {status}")
            lines.append("")
        
        # Agent positions
        lines.append("\nAGENT POSITIONS\n")
        for agent, position in agent_positions.items():
            lines.append(f"{agent}:")
            lines.append(position)
            lines.append("")
        
        # Position revisions
        lines.append("\nPOSITION REVISIONS\n")
        for revision in position_revisions:
            lines.append(f"{revision.get('speaker', 'Unknown')}: {revision.get('reason', 'N/A')}")
            lines.append("")
        
        # Unresolved questions
        lines.append("\nUNRESOLVED QUESTIONS\n")
        for i, q in enumerate(unresolved_questions, 1):
            lines.append(f"{i}. {q}")
        
        # Constructive proposals
        lines.append("\nCONSTRUCTIVE PROPOSALS\n")
        for i, proposal in enumerate(constructive_proposals, 1):
            lines.append(f"{i}. {proposal}")
        
        self._append("\n".join(lines))
    
    def log_summary(
        self,
        total_turns: int,
        unique_speakers: list[str],
        repetitions_detected: int,
        fallbacks_triggered: int,
        position_revisions: int,
        new_threads: int,
        closed_threads: int,
        constructive_proposals: int,
        state_changes: int,
        test_status: str,
        metrics: Optional[dict[str, float]] = None,
    ) -> None:
        """Log the test summary."""
        lines = ["\n================================================================================", "TEST SUMMARY", "================================================================================"]
        
        lines.append(f"\nTOTAL_TURNS: {total_turns}")
        lines.append(f"\nUNIQUE_SPEAKERS: {len(unique_speakers)}")
        lines.append(f"\nREPETITIONS_DETECTED: {repetitions_detected}")
        lines.append(f"\nFALLBACKS: {fallbacks_triggered}")
        lines.append(f"\nPOSITION_REVISIONS: {position_revisions}")
        lines.append(f"\nNEW_THREADS: {new_threads}")
        lines.append(f"\nCLOSED_THREADS: {closed_threads}")
        lines.append(f"\nCONSTRUCTIVE_PROPOSALS: {constructive_proposals}")
        lines.append(f"\nSTATE_CHANGES: {state_changes}")
        lines.append(f"\nTEST_STATUS: {test_status}")
        
        # Metrics
        if metrics:
            lines.append("\nARGUMENTATIVE_PROGRESS_SCORE:")
            for metric, value in metrics.items():
                lines.append(f"  {metric}: {value:.3f}")
        
        lines.append("\n================================================================================")
        lines.append("END OF TEST")
        lines.append("================================================================================")
        
        self._append("\n".join(lines))
    
    def _append(self, content: str) -> None:
        """Append content to the archive file."""
        with open(self.archive_path, 'a', encoding='utf-8') as f:
            f.write(content)
        logger.debug("Appended to archive: %s", self.archive_path)
