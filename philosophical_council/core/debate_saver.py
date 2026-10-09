"""Save debates to storage directory."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DebateSaver:
    """Save complete debate transcripts to files."""

    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def get_next_log_number(self) -> int:
        """Get the next log number by scanning existing files."""
        max_num = 0
        for f in self.storage_dir.glob("debate_log_*.txt"):
            match = re.search(r'debate_log_(\d+)\.txt', f.name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)
        return max_num + 1

    def save_debate(
        self,
        topic: str,
        turns: list[dict],
        debate_id: Optional[int] = None,
        status: str = "finished",
    ) -> str:
        """Save a complete debate transcript to a file.

        Args:
            topic: The debate topic
            turns: List of turn dicts with keys: turn_id, speaker, response,
                   moderator_question (optional), moderator_reason (optional)
            debate_id: Optional database ID for reference
            status: Final status of the debate

        Returns:
            Path to the saved file
        """
        log_num = self.get_next_log_number()
        filename = f"debate_log_{log_num}.txt"
        filepath = self.storage_dir / filename

        lines = []
        lines.append("=" * 70)
        lines.append(f"DEBATE TRANSCRIPT")
        lines.append(f"Topic: {topic}")
        if debate_id:
            lines.append(f"Debate ID: {debate_id}")
        lines.append(f"Status: {status}")
        lines.append(f"Total turns: {len(turns)}")
        lines.append("=" * 70)
        lines.append("")

        for turn in turns:
            turn_num = turn.get("turn_id", "?")
            speaker = turn.get("speaker", "Unknown")

            lines.append("=" * 70)
            lines.append(f"TURN {turn_num}")
            lines.append("")

            # Moderator challenge (if present)
            mod_question = turn.get("moderator_question")
            mod_reason = turn.get("moderator_reason")
            if mod_question:
                lines.append("MODERATOR")
                lines.append("")
                lines.append(f"Challenge: {mod_question}")
                if mod_reason:
                    lines.append(f"Reason: {mod_reason}")
                lines.append("-" * 70)
                lines.append("")

            # Agent response
            lines.append(f"{speaker}")
            lines.append("")
            response = turn.get("response", "")
            lines.append(response)
            lines.append("")

        lines.append("=" * 70)
        lines.append("END OF DEBATE")
        lines.append("=" * 70)

        content = "\n".join(lines)
        filepath.write_text(content, encoding="utf-8")

        logger.info("Debate saved to: %s", filepath)
        return str(filepath)

    def list_saved_debates(self) -> list[dict]:
        """List all saved debates with metadata."""
        debates = []
        for f in sorted(self.storage_dir.glob("debate_log_*.txt")):
            match = re.search(r'debate_log_(\d+)\.txt', f.name)
            if match:
                log_num = int(match.group(1))
                # Read first few lines to get topic
                content = f.read_text(encoding="utf-8")
                topic_match = re.search(r'Topic: (.+)', content)
                turns_match = re.search(r'Total turns: (\d+)', content)
                debates.append({
                    "filename": f.name,
                    "log_number": log_num,
                    "path": str(f),
                    "topic": topic_match.group(1) if topic_match else "Unknown",
                    "turns": int(turns_match.group(1)) if turns_match else 0,
                })
        return debates
