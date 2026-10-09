"""Autopilot → existing multi-agent LLM adapter.

CONNECTS (does not duplicate) Autopilot's generated tasks to the same stable
core used by Code Lab. The deterministic SmartRouter + ToolWorker path is the
authority; this adapter adds an optional LLM verifier/judge opinion that is
recorded SEPARATELY and can never override deterministic validation (rule 6).

When the LLM backend is unavailable/invalid-token, this adapter reports
availability honestly and the deterministic path is used unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("Experiments.LLMAdapter")


class ExperimentLLMAdapter:
    """Builds/reuses the Code Lab multi-agent verifier for Autopilot runs."""

    def __init__(self, event_handler=None) -> None:
        self._verifier = None
        self.event_handler = event_handler

    def _ensure_verifier(self):
        if self._verifier is None:
            try:
                from code_lab.multiagent import CodingMultiAgent, resolve_llm_credentials
                base_url, api_key = resolve_llm_credentials()
                # Probe availability honestly first.
                from code_lab.multiagent import probe_llm
                self._probe = probe_llm(base_url, api_key)
                if not self._probe.get("available"):
                    self._verifier = None
                    return None
                model_config = None
                try:
                    from philosophical_council.config import Config
                    model_config = Config.default().models
                except Exception:
                    model_config = None
                self._verifier = CodingMultiAgent(
                    base_url=base_url,
                    api_key=api_key,
                    model_config=model_config,
                    on_event=self.event_handler,
                )
            except Exception as e:  # pragma: no cover
                logger.warning("LLM adapter init failed: %s", e)
                self._verifier = None
        return self._verifier

    @property
    def available(self) -> bool:
        v = self._ensure_verifier()
        return v is not None

    @property
    def availability(self) -> Dict[str, Any]:
        self._ensure_verifier()
        return getattr(self, "_probe", {"available": False, "error": "not_probed"})

    def build_runner(self, runner: Any) -> Any:
        """Wrap a runner callable with the optional LLM verifier.

        Returns a callable `run(task, context)` that mirrors the runner but adds
        the judge opinion ONLY when the LLM is really available.
        """
        v = self._ensure_verifier()

        def run(task, context=None):
            if v is not None:
                return runner.run_task_with_llm_verifier(task, context, llm_verifier=v)
            return runner.run_task(task, context)

        return run
