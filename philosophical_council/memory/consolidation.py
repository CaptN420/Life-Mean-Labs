"""Memory consolidation — transforms raw debate into structured memory."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .mid_term import MidTermEntry, MidTermMemory
from .long_term import LongTermEntry, LongTermMemory
from ..llm.prompts import CONSOLIDATION_PROMPT

logger = logging.getLogger(__name__)

# Canonical MidTermEntry field names (must match memory.mid_term.MidTermEntry).
_MIDTERM_FIELDS = [
    "main_arguments",
    "counter_arguments",
    "agreements",
    "disagreements",
    "contradictions",
    "important_questions",
    "position_changes",
    "unresolved_issues",
]


def _coerce_str_list(value, default=None) -> list[str]:
    """Coerce an LLM-furnished value into a list of non-empty strings."""
    if value is None:
        return list(default) if default else []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif item is not None:
                out.append(str(item).strip())
        return out
    return list(default) if default else []


def _normalize_summary_dto(dto: dict) -> dict:
    """Map an arbitrary summarizer DTO onto the canonical MidTermEntry schema.

    The LLM (or a fallback) may return either the canonical list-shaped fields
    OR a different shape (e.g. ``title``/``sub_title``/``summary``/``cur_task``).
    Rather than pass ``**dto`` into ``MidTermEntry`` (which raises TypeError on
    any unknown key), we explicitly map/coerce and DROP unknown keys so the
    constructor always receives only its own fields. Unknown keys are logged,
    never silently destructive.
    """
    mapped: dict = {}
    for key in _MIDTERM_FIELDS:
        mapped[key] = _coerce_str_list(dto.get(key))
    # If the LLM returned a prose-style DTO (title/sub_title/summary), fold
    # those into main_arguments so the content is not lost.
    if not mapped["main_arguments"]:
        leftovers = []
        for alt in ("summary", "main", "title", "sub_title", "cur_task", "content"):
            val = dto.get(alt)
            if isinstance(val, str) and val.strip() and val.strip() not in leftovers:
                leftovers.append(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip() and item.strip() not in leftovers:
                        leftovers.append(item.strip())
        mapped["main_arguments"] = leftovers
    return mapped


class MemoryConsolidator:
    """Periodically summarizes debate activity into mid-term and long-term memory."""

    def __init__(self, mid_term: MidTermMemory, long_term: LongTermMemory) -> None:
        self.mid_term = mid_term
        self.long_term = long_term
        self._turn_count_since_consolidation = 0

    def should_consolidate(self, turns_since: int, interval: int) -> bool:
        """Check if enough turns have passed to trigger consolidation."""
        return turns_since >= interval

    def consolidate_mid_term(
        self,
        raw_turns: list[dict[str, str]],
        period_label: str,
        llm_client=None,  # Optional LLM client for AI-powered summarization
    ) -> Optional[MidTermEntry]:
        """Summarize a batch of raw turns into mid-term memory.

        The summarizer's raw DTO is mapped onto the canonical MidTermEntry
        schema and VALIDATED before construction (spec §12) — an unexpected
        keyword (e.g. ``title``) can never raise a TypeError inside the
        constructor. Only successfully-built entries are added; LLM output is
        never swallowed silently.
        """
        if not raw_turns:
            return None

        context = self._build_context(raw_turns)
        logger.info("Consolidating mid-term memory for period: %s", period_label)

        if llm_client is not None:
            raw = None
            try:
                raw = self._summarize_with_llm(context, period_label, llm_client)
            except Exception as exc:
                logger.error("LLM consolidator errored: %s", exc)
                self._emit_failure(period_label, f"summarizer_error: {exc}")
            if raw:
                # Normalize FIRST so the constructor receives a valid schema.
                try:
                    mapped = _normalize_summary_dto(dict(raw))
                    entry = MidTermEntry(period=period_label, **mapped)
                    # Fail visibly if the LLM returned no usable content.
                    if not any((entry.main_arguments, entry.counter_arguments,
                                entry.important_questions)):
                        self._emit_failure(period_label,
                                           "schema_empty: LLM DTO carried no usable content")
                    else:
                        self.mid_term.add(entry)
                        return entry
                except TypeError as exc:
                    # A schema mismatch reached the constructor — surface it,
                    # do NOT pretend consolidation succeeded.
                    self._emit_failure(period_label, f"schema_mismatch: {exc}")
                    raise

        # Fallback: simple keyword-based extraction
        entry = self._summarize_fallback(raw_turns, period_label)
        self.mid_term.add(entry)
        return entry

    def _emit_failure(self, period: str, reason: str) -> None:
        """Emit a visible MEMORY_CONSOLIDATION_FAILED signal."""
        logger.error("MEMORY_CONSOLIDATION_FAILED | period=%s | reason=%s", period, reason)
        try:
            raw_recorder = self._raw_recorder()
            if raw_recorder is not None and hasattr(raw_recorder, "record_debate_event"):
                raw_recorder.record_debate_event(
                    experiment_id=None,
                    event_type="memory_consolidation_failed",
                    agent_id="memory",
                    content=f"{period}: {reason}".encode() if False else f"{period}: {reason}",
                    round_num=0,
                )
        except Exception:  # pragma: no cover - best effort
            pass

    def consolidate_long_term(
        self,
        mid_term_entries: list[MidTermEntry],
        llm_client=None,
    ) -> None:
        """Promote important insights from mid-term to long-term memory."""
        if not mid_term_entries:
            return

        logger.info("Consolidating long-term memory from %d mid-term entries", len(mid_term_entries))

        if llm_client is not None:
            try:
                self._promote_with_llm(mid_term_entries, llm_client)
            except Exception as exc:
                logger.error("LLM long-term consolidation failed: %s", exc)
                self._promote_fallback(mid_term_entries)
        else:
            self._promote_fallback(mid_term_entries)

    def _raw_recorder(self):
        """Lazy RAW recorder access (best-effort; never blocks consolidation)."""
        try:
            from ..raw_protocol import RawDebateRecorder
            return RawDebateRecorder()
        except Exception:  # pragma: no cover
            return None

    def _build_context(self, raw_turns: list[dict[str, str]]) -> str:
        """Build a text context from raw turns."""
        lines = ["Debate section to summarize:\n"]
        for turn in raw_turns[-15:]:  # Last 15 turns
            lines.append(f"Turn {turn.get('turn_id', '?')}:")
            lines.append(f"Speaker: {turn.get('speaker', 'unknown')}")
            resp = turn.get('response', '')
            if len(resp) > 500:
                resp = resp[:500] + "..."
            lines.append(resp)
            lines.append("---")
        return "\n".join(lines)

    def _summarize_with_llm(
        self, context: str, period_label: str, llm_client
    ) -> dict[str, object]:
        """Use LLM to produce a structured mid-term summary."""
        from ..llm.client import LLMClient
        if not isinstance(llm_client, LLMClient):
            # Try to use it anyway
            pass

        prompt = CONSOLIDATION_PROMPT.format(period=period_label, context=context)
        response_text, finish_reason = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        return self._parse_consolidation_response(response_text)

    def _parse_consolidation_response(self, raw: str) -> dict[str, object]:
        """Parse a consolidation response into structured data."""
        raw = raw.strip()
        try:
            data = json.loads(raw)
            return data
        except (json.JSONDecodeError, ValueError):
            pass

        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except (json.JSONDecodeError, ValueError):
                pass

        return {
            "main_arguments": [raw[:300]],
            "counter_arguments": [],
            "agreements": [],
            "disagreements": [],
            "contradictions": [],
            "important_questions": [],
            "position_changes": [],
            "unresolved_issues": [],
        }

    def _summarize_fallback(
        self, raw_turns: list[dict[str, str]], period_label: str
    ) -> MidTermEntry:
        """Simple fallback summarization without LLM."""
        arguments = []
        for turn in raw_turns:
            resp = turn.get("response", "")
            if len(resp) > 50:
                # Take first sentence or two
                sentences = re.split(r'[.!?]+', resp)
                for sent in sentences[:2]:
                    sent = sent.strip()
                    if len(sent) > 30:
                        arguments.append(sent)

        return MidTermEntry(
            period=period_label,
            main_arguments=arguments[:10],
        )

    def _promote_with_llm(self, entries: list[MidTermEntry], llm_client) -> None:
        """Use LLM to identify key insights for long-term memory."""
        context = "Long-term memory promotion:\n"
        for entry in entries[-10:]:
            context += f"\n=== {entry.period} ===\n"
            for arg in entry.main_arguments:
                context += f"- {arg}\n"
            for q in entry.important_questions:
                context += f"? {q}\n"

        prompt = f"""Extract key philosophical insights from this debate section for permanent storage.

{context}

Return JSON with these fields:
- entries: array of {{key, category, content}}

Keep only the most important, non-redundant insights."""

        response_text, finish_reason = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )

        try:
            data = json.loads(response_text)
            for item in data.get("entries", []):
                entry = LongTermEntry(
                    key=str(item.get("key", "")),
                    category=item.get("category"),
                    content=str(item.get("content", "")),
                )
                self.long_term.add(entry)
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Failed to parse long-term promotion response")

    def _promote_fallback(self, entries: list[MidTermEntry]) -> None:
        """Fallback: promote important questions and contradictions."""
        for entry in entries[-5:]:
            for q in entry.important_questions[:3]:
                key = f"question_{len(self.long_term.get_all())}"
                self.long_term.add(LongTermEntry(
                    key=key,
                    category="question",
                    content=q,
                ))
            for c in entry.contradictions[:2]:
                key = f"contradiction_{len(self.long_term.get_all())}"
                self.long_term.add(LongTermEntry(
                    key=key,
                    category="contradiction",
                    content=c,
                ))
