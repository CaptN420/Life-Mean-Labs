"""
Code Lab Compression Adapter — Minimal integration layer for native compression.

This adapter bridges Code Lab's LLM call path with the native compression engine.
It is designed to be:
  - Disabled by default (COMPRESSION_ENABLED=false)
  - Non-invasive to existing behavior
  - Safe to disable at any time

Usage:
    from code_lab.compression_adapter import compress_context_if_enabled
    
    # In CodingAgent.turn() or equivalent:
    compressed_messages = compress_context_if_enabled(messages, system_prompt, ...)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CodeLab.CompressionAdapter")

# Feature flag — must be explicitly "true" to enable
COMPRESSION_ENABLED_ENV = "COMPRESSION_ENABLED"


def is_compression_enabled() -> bool:
    """Check if compression is explicitly enabled."""
    value = os.environ.get(COMPRESSION_ENABLED_ENV, "false").strip().lower()
    return value in ("true", "1", "yes", "on")


def compress_context_if_enabled(
    messages: List[Dict[str, Any]],
    system_prompt: str,
    memory_text: str = "",
    tools: List[Dict[str, Any]] = None,
    retrieved_context: str = "",
    user_query: str = "",
) -> Dict[str, Any]:
    """Compress context if enabled, otherwise return original.
    
    Returns a dict with:
      - messages: the (possibly compressed) messages to send to LLM
      - system_prompt: the system prompt (may be unchanged)
      - compressed: bool indicating if compression was applied
      - stats: dict with compression statistics
      - error: any error that occurred (if compression failed, returns originals)
    """
    # Check feature flag
    if not is_compression_enabled():
        return {
            "messages": messages,
            "system_prompt": system_prompt,
            "compressed": False,
            "stats": {},
            "error": None,
        }
    
    # Import compression engine
    try:
        from code_lab.compression import ContextBudget, BudgetConfig
    except ImportError as e:
        logger.error("Failed to import compression engine: %s", e)
        return {
            "messages": messages,
            "system_prompt": system_prompt,
            "compressed": False,
            "stats": {},
            "error": f"Import error: {e}",
        }
    
    # Run compression with error handling
    try:
        budget = ContextBudget(
            model="test",  # Will use estimate mode
            config=BudgetConfig(
                total=4000,   # Conservative budget
                history=2000,
                system=1000,
                memory=500,
                tools=500,
                retrieved=500,
            )
        )
        
        result = budget.select(
            system_prompt=system_prompt,
            messages=messages,
            memory_text=memory_text,
            tools=tools or [],
            retrieved_context=retrieved_context,
            user_query=user_query,
        )
        
        # Check if compression actually did something useful
        if result.selected_total_tokens >= result.original_total_tokens:
            # No compression achieved, return originals
            logger.debug("Compression achieved no reduction (%d -> %d)", 
                        result.original_total_tokens, result.selected_total_tokens)
            return {
                "messages": messages,
                "system_prompt": system_prompt,
                "compressed": False,
                "stats": {"reason": "no_reduction"},
                "error": None,
            }
        
        logger.info("Compression applied: %d -> %d tokens (%.1f%% reduction)",
                   result.original_total_tokens, result.selected_total_tokens,
                   (1 - result.selected_total_tokens / max(result.original_total_tokens, 1)) * 100)
        
        return {
            "messages": result.selected_messages or messages,
            "system_prompt": system_prompt,  # System prompt always preserved
            "compressed": True,
            "stats": {
                "original_tokens": result.original_total_tokens,
                "selected_tokens": result.selected_total_tokens,
                "reduction_pct": (1 - result.selected_total_tokens / max(result.original_total_tokens, 1)) * 100,
                "history_dropped": result.history_items_dropped,
            },
            "error": None,
        }
        
    except Exception as e:
        logger.warning("Compression failed, using original context: %s", e)
        return {
            "messages": messages,
            "system_prompt": system_prompt,
            "compressed": False,
            "stats": {},
            "error": str(e),
        }
