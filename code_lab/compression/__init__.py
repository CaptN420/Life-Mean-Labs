"""
Life_mean Context Compression Module

Official location for the native context budget and history compression engine.
Migrated from legacy/Mia_Brain/CaptN-BRAIN-main/captn/runtime/

Feature flag: COMPRESSION_ENABLED=false (disabled by default)
Enable with: export COMPRESSION_ENABLED=true

Usage:
    from code_lab.compression import ContextBudget, compress_history
    
    budget = ContextBudget(model="test")
    result = budget.select(
        system_prompt="...",
        messages=[...],
        user_query="...",
    )
"""

from __future__ import annotations

# Export public API
from .context_budget import (
    ContextBudget,
    BudgetConfig,
    SelectionResult,
    SelectionDecision,
    estimate_provider_tokens,
    estimate_messages_tokens,
    estimate_tool_tokens,
    is_budget_enabled,
    DEFAULT_BUDGET_CONFIG,
)

from .history_compressor import (
    HistorySummary,
    compress_history,
    format_compressed_history,
)

from .output_compressor import (
    compress as compress_output,
    savings_report,
)

__all__ = [
    # Context Budget
    "ContextBudget",
    "BudgetConfig",
    "SelectionResult",
    "SelectionDecision",
    "estimate_provider_tokens",
    "estimate_messages_tokens",
    "estimate_tool_tokens",
    "is_budget_enabled",
    "DEFAULT_BUDGET_CONFIG",
    # History Compressor
    "HistorySummary",
    "compress_history",
    "format_compressed_history",
    # Output Compressor
    "compress_output",
    "savings_report",
]
