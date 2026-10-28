"""Metacognitive error memory for autonomous repair.

Tracks errors across runs, identifies patterns, and prevents repeating
failed strategies. Enables learning from past failures.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CodeLab.ErrorMemory")


class ErrorRecord:
    """Records an error and the strategies tried to fix it."""

    def __init__(self, error_type: str, error_message: str, run_id: str):
        self.error_type = error_type
        self.error_message = error_message
        self.run_id = run_id
        self.strategies_tried: List[str] = []
        self.successful_fixes: List[Dict[str, Any]] = []
        self.first_seen: float = time.time()
        self.last_seen: float = time.time()
        self.count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message[:200],
            "run_id": self.run_id,
            "strategies_tried": self.strategies_tried,
            "successful_fixes": self.successful_fixes,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "count": self.count,
        }


class ErrorMemory:
    """Persistent memory of errors and repair strategies."""

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = memory_dir or Path.cwd() / "code_lab_runs" / "_error_memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._errors: Dict[str, ErrorRecord] = {}
        self._load()

    def _load(self) -> None:
        """Load error memory from disk."""
        mem_path = self.memory_dir / "error_memory.json"
        if not mem_path.exists():
            return
        try:
            data = json.loads(mem_path.read_text(encoding="utf-8"))
            for key, rec_data in data.items():
                rec = ErrorRecord(
                    error_type=rec_data["error_type"],
                    error_message=rec_data.get("error_message", ""),
                    run_id=rec_data.get("run_id", "unknown"),
                )
                rec.strategies_tried = rec_data.get("strategies_tried", [])
                rec.successful_fixes = rec_data.get("successful_fixes", [])
                rec.first_seen = rec_data.get("first_seen", time.time())
                rec.last_seen = rec_data.get("last_seen", time.time())
                rec.count = rec_data.get("count", 1)
                self._errors[key] = rec
            logger.info("Loaded %d error records from memory", len(self._errors))
        except Exception as e:
            logger.warning("Failed to load error memory: %s", e)

    def _save(self) -> None:
        """Persist error memory to disk."""
        mem_path = self.memory_dir / "error_memory.json"
        data = {k: v.to_dict() for k, v in self._errors.items()}
        mem_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_error(self, error_type: str, error_message: str, run_id: str) -> ErrorRecord:
        """Record an error occurrence."""
        # Create signature from error type and first line
        sig = self._make_signature(error_type, error_message)

        if sig in self._errors:
            rec = self._errors[sig]
            rec.count += 1
            rec.last_seen = time.time()
            rec.run_id = run_id
        else:
            rec = ErrorRecord(error_type, error_message, run_id)
            self._errors[sig] = rec

        self._save()
        return rec

    def record_strategy_attempt(self, error_type: str, strategy: str, success: bool,
                                fix_details: Optional[Dict[str, Any]] = None) -> None:
        """Record that a strategy was tried for an error."""
        sig = self._make_signature(error_type, "")
        if sig not in self._errors:
            return

        rec = self._errors[sig]
        if strategy not in rec.strategies_tried:
            rec.strategies_tried.append(strategy)

        if success and fix_details:
            rec.successful_fixes.append(fix_details)

        self._save()

    def get_failed_strategies(self, error_type: str) -> List[str]:
        """Get list of strategies that failed for this error type."""
        sig = self._make_signature(error_type, "")
        if sig not in self._errors:
            return []
        # Return all strategies (we track attempts, not failures specifically)
        return self._errors[sig].strategies_tried

    def get_successful_fixes(self, error_type: str) -> List[Dict[str, Any]]:
        """Get list of successful fixes for this error type."""
        sig = self._make_signature(error_type, "")
        if sig not in self._errors:
            return []
        return self._errors[sig].successful_fixes

    def should_avoid_strategy(self, error_type: str, strategy: str) -> bool:
        """Check if a strategy should be avoided for this error."""
        # If we've tried this strategy 3+ times without success, avoid it
        sig = self._make_signature(error_type, "")
        if sig not in self._errors:
            return False

        rec = self._errors[sig]
        if strategy in rec.strategies_tried:
            # Count how many times this specific strategy was tried
            count = rec.strategies_tried.count(strategy)
            # If tried 3+ times, avoid
            return count >= 3

        return False

    def get_recommendation(self, error_type: str) -> Optional[str]:
        """Get a recommended strategy for an error type."""
        sig = self._make_signature(error_type, "")
        if sig not in self._errors:
            return None

        rec = self._errors[sig]
        if rec.successful_fixes:
            # Return the most recent successful fix approach
            return "apply_known_fix"

        # Suggest trying a different strategy
        return "try_alternative"

    def clear_run_errors(self, run_id: str) -> int:
        """Clear errors associated with a specific run."""
        cleared = 0
        keys_to_remove = []
        for sig, rec in self._errors.items():
            if rec.run_id == run_id:
                keys_to_remove.append(sig)
                cleared += 1
        for key in keys_to_remove:
            del self._errors[key]
        if keys_to_remove:
            self._save()
        return cleared

    def _make_signature(self, error_type: str, error_message: str) -> str:
        """Create a signature for deduplication."""
        # Use error type + first 80 chars of message
        msg_preview = error_message[:80] if error_message else ""
        return f"{error_type}|{msg_preview}"

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about error memory."""
        total_errors = sum(r.count for r in self._errors.values())
        total_strategies = sum(len(r.strategies_tried) for r in self._errors.values())
        total_fixes = sum(len(r.successful_fixes) for r in self._errors.values())

        return {
            "unique_errors": len(self._errors),
            "total_occurrences": total_errors,
            "strategies_attempted": total_strategies,
            "successful_fixes": total_fixes,
        }
