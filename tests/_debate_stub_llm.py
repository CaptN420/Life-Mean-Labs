"""Deterministic stub LLM for Debate Lab tests / smoke runs."""
from __future__ import annotations

import re
import time
from typing import List, Optional


class StubLLM:
    """Emulates the LLMClient contract used by DebateEngine:

    ``chat(...) -> (text, finish_reason)``, ``last_model_used``, ``_models``,
    ``_router``, ``get_models()``, ``record_usage()``.
    """

    def __init__(self, models: Optional[List[str]] = None,
                 speech_prefix: str = "Stub response on",
                 moderator_malformed: bool = False,
                 chat_delay: float = 0.0,
                 speaker_cycle: Optional[List[str]] = None) -> None:
        self._models = list(models or ["test-model"])
        self._router = None
        self.last_model_used = ""
        self.speech_prefix = speech_prefix
        self.moderator_malformed = moderator_malformed
        self.chat_delay = chat_delay
        self.call_count = 0
        self.speaker_cycle = list(speaker_cycle) if speaker_cycle else None
        self._cycle_idx = 0

    def get_models(self) -> List[str]:
        return list(self._models)

    def chat(self, messages, model: str = "", temperature: float = 0.7,
             max_tokens: int = 1024, **kwargs):
        self.call_count += 1
        if self.chat_delay:
            time.sleep(self.chat_delay)
        content = messages[-1]["content"] if messages else ""
        if "selected_speaker" in content:
            if self.moderator_malformed:
                self.last_model_used = self._pick_model(model)
                return ("This is not JSON. The moderator is completely confused "
                        "and produced a paragraph of prose instead.", "stop")
            m = re.search(r"One of: ([^\n]+)", content)
            speakers = [s.strip() for s in m.group(1).split(",")] if m else ["Existentialist"]
            if not speakers or not speakers[0]:
                speakers = ["Existentialist"]
            if self.speaker_cycle:
                chosen = self.speaker_cycle[self._cycle_idx % len(self.speaker_cycle)]
                self._cycle_idx += 1
            else:
                chosen = speakers[0]
            self.last_model_used = self._pick_model(model)
            return (
                '{"selected_speaker": "' + chosen
                + '", "challenge": "Please address the previous argument with a '
                  'novel point that genuinely moves the debate forward.", '
                  '"reason": "stub", "question": null, "detected_issues": null}',
                "stop",
            )
        self.last_model_used = self._pick_model(model)
        return (f"{self.speech_prefix} {self.last_model_used} "
                f"(model={self.last_model_used})", "stop")

    def _pick_model(self, model: str) -> str:
        if model:
            return model
        if self._router is not None:
            try:
                picked = self._router.select_model()
                if picked:
                    return picked
            except Exception:
                pass
        return self._models[0]

    def record_usage(self, *args, **kwargs) -> None:  # pragma: no cover
        pass


class BlockingLLM(StubLLM):
    """A stub whose chat() never returns — used to prove stop/delete semantics
    (spec §20/§21: a live in-flight call may finish, but no NEW call may begin
    after stop; a worker that cannot terminate blocks deletion)."""

    def chat(self, messages, model: str = "", temperature: float = 0.7,
             max_tokens: int = 1024, **kwargs):
        self.call_count += 1
        while True:  # pragma: no cover - intentionally blocks
            time.sleep(1)
