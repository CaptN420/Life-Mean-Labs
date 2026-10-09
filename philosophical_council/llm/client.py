"""LLM client for LM Studio OpenAI-compatible API."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper around the OpenAI Python package for LM Studio."""

    def __init__(self, base_url: str, api_key: str = "lm-studio") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            ) from exc

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = OpenAI(base_url=self.base_url, api_key=api_key)
        self._models: list[str] = []
        self._router: Optional[Any] = None  # Will be set from outside
        # The model actually used by the last inference (resolved via router /
        # fallback when none was configured). Lets the experimental layer record
        # ACTUAL vs CONFIGURED model for provenance (Role Template system).
        self.last_model_used: str = ""

    def get_models(self) -> list[str]:
        """Fetch available models from LM Studio."""
        if self._models:
            return self._models
        try:
            resp = self._client.models.list()
            self._models = [m.id for m in resp.data]
            logger.info("Found %d models in LM Studio", len(self._models))
        except Exception as exc:
            logger.warning("Failed to fetch models: %s", exc)
            self._models = []
        return self._models

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 700,
    ) -> tuple[str, str]:
        """Send a chat completion request and return (response_text, finish_reason)."""
        start_time = time.time()
        try:
            # If no model specified, use router or fallback to first available
            effective_model = self._resolve_model(model)
            self.last_model_used = effective_model

            kwargs: dict[str, Any] = {
                "model": effective_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            response = self._client.chat.completions.create(**kwargs)
            duration = time.time() - start_time
            choice = response.choices[0]
            text = choice.message.content or ""
            finish_reason = choice.finish_reason or "stop"
            usage = getattr(choice, 'usage', None)
            logger.debug("LLM call completed in %.1fs, tokens: %s, finish_reason: %s", duration, usage, finish_reason)

            # Record performance if router is available
            if self._router and effective_model:
                self._router.record_performance(effective_model, True, duration)

            return text.strip(), finish_reason
        except Exception as exc:
            duration = time.time() - start_time
            logger.error("LLM call failed after %.1fs: %s", duration, exc)

            # Record failure if router is available
            if self._router and model:
                self._router.record_performance(model, False, duration)

            return f"[Error responding after {duration:.1f}s: {exc}]", "error"

    def _resolve_model(self, model: Optional[str]) -> str:
        """Resolve a model string, using router if needed."""
        # If explicit model provided, use it
        if model and model.strip():
            return model.strip()

        # Try router first
        if self._router and hasattr(self._router, 'select_model'):
            try:
                selected = self._router.select_model()
                if selected:
                    logger.debug("Router selected model: %s", selected)
                    return selected
            except Exception as exc:
                logger.warning("Router failed: %s", exc)

        # Fallback to first available model
        return self._get_default_model()

    def _get_default_model(self) -> str:
        """Get the first available model for dynamic routing."""
        if not self._models:
            self.get_models()  # Try to fetch models
        return self._models[0] if self._models else ""

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 700,
    ):
        """Stream a chat completion, yielding chunks as they arrive."""
        start_time = time.time()
        try:
            # If no model specified, use router or fallback to first available
            effective_model = self._resolve_model(model)
            self.last_model_used = effective_model

            kwargs: dict[str, Any] = {
                "model": effective_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }

            stream = self._client.chat.completions.create(**kwargs)
            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                full_response += delta
                yield delta
            duration = time.time() - start_time
            logger.debug("Stream completed in %.1fs", duration)

            # Record performance if router is available
            if self._router and effective_model:
                self._router.record_performance(effective_model, True, duration)
        except Exception as exc:
            logger.error("Streaming failed: %s", exc)
            yield f"\n[Error: {exc}]"
