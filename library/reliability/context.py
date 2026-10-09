"""Adaptive Context Manager — dynamic budget allocation based on complexity.

Adapted from Mia_Brain (captn/runtime/adaptive_manager.py).
Deterministic complexity analysis with configurable weights.
Pure Python, zero LLM.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AdaptiveContext")


# ═══════════════════════════════════════════════════════════════════
# COMPLEXITY WEIGHTS — Deterministic calibration system
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ComplexityWeights:
    """Deterministic weights for the 6 complexity signal groups.

    All weights must sum to 1.0.
    """
    query_length: float = 0.20
    history_depth: float = 0.30
    tool_complexity: float = 0.20
    memory_retrieval: float = 0.15
    context_pressure: float = 0.10
    multi_dimension: float = 0.05

    def __post_init__(self):
        total = (self.query_length + self.history_depth + self.tool_complexity
                 + self.memory_retrieval + self.context_pressure + self.multi_dimension)
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"ComplexityWeights sum to {total:.4f}, expected 1.0")

    def to_dict(self) -> Dict[str, float]:
        return {
            "query_length": self.query_length,
            "history_depth": self.history_depth,
            "tool_complexity": self.tool_complexity,
            "memory_retrieval": self.memory_retrieval,
            "context_pressure": self.context_pressure,
            "multi_dimension": self.multi_dimension,
        }


DEFAULT_WEIGHTS = ComplexityWeights()

CALIBRATION_VARIANTS: Dict[str, ComplexityWeights] = {
    "current":           ComplexityWeights(0.20, 0.30, 0.20, 0.15, 0.10, 0.05),
    "history_sensitive": ComplexityWeights(0.15, 0.35, 0.20, 0.15, 0.10, 0.05),
    "pressure_sensitive": ComplexityWeights(0.15, 0.30, 0.20, 0.15, 0.15, 0.05),
    "multi_dim":         ComplexityWeights(0.15, 0.30, 0.20, 0.15, 0.10, 0.10),
    "balanced":          ComplexityWeights(0.15, 0.35, 0.20, 0.10, 0.15, 0.05),
}


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS — Configurable defaults
# ═══════════════════════════════════════════════════════════════════

_SIMPLE_THRESHOLD = 0.35
_MODERATE_THRESHOLD = 0.60
_COMPLEX_THRESHOLD = 0.80

_CATEGORY_RANGES: Dict[str, Tuple[int, int]] = {
    "system":    (3_000, 5_000),
    "history":   (2_000, 8_000),
    "memory":    (1_000, 7_000),
    "tools":     (1_000, 5_000),
    "retrieved": (1_000, 5_000),
}

_CATEGORY_IMPORTANCE: Dict[str, float] = {
    "system":    0.25,
    "history":   0.20,
    "memory":    0.20,
    "tools":     0.20,
    "retrieved": 0.15,
}

_CATEGORY_NAMES = ["system", "history", "memory", "tools", "retrieved"]


# ═══════════════════════════════════════════════════════════════════
# COMPLEXITY ANALYZER
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ComplexitySignals:
    """Deterministic signals used to compute task complexity."""
    query_length: int = 0
    query_token_estimate: int = 0
    history_available_tokens: int = 0
    history_message_count: int = 0
    memory_available_tokens: int = 0
    memory_entry_count: int = 0
    tool_count: int = 0
    tool_schema_tokens: int = 0
    retrieved_tokens: int = 0
    retrieved_fragment_count: int = 0
    conversation_turn_count: int = 0
    current_context_tokens: int = 0
    system_tokens: int = 0
    domain_hint_present: bool = False
    multi_tool: bool = False
    has_memory: bool = False
    has_retrieval: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_length": self.query_length,
            "query_tokens": self.query_token_estimate,
            "history_tokens": self.history_available_tokens,
            "history_msgs": self.history_message_count,
            "memory_tokens": self.memory_available_tokens,
            "memory_entries": self.memory_entry_count,
            "tool_count": self.tool_count,
            "tool_tokens": self.tool_schema_tokens,
            "retrieved_tokens": self.retrieved_tokens,
            "retrieved_frags": self.retrieved_fragment_count,
            "turn_count": self.conversation_turn_count,
            "context_tokens": self.current_context_tokens,
            "system_tokens": self.system_tokens,
            "domain_hint": self.domain_hint_present,
            "multi_tool": self.multi_tool,
            "has_memory": self.has_memory,
            "has_retrieval": self.has_retrieval,
        }


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token)."""
    return max(1, len(text) // 4)


def compute_signals(
    system_prompt: str = "",
    messages: Optional[List[Dict[str, Any]]] = None,
    memory_text: str = "",
    tools: Optional[List[Dict[str, Any]]] = None,
    retrieved_context: str = "",
    user_query: str = "",
    domain_hint: str = "",
) -> ComplexitySignals:
    """Extract deterministic complexity signals from request components."""
    msgs = messages or []
    tools_list = tools or []

    # Query signals
    query_len = len(user_query)
    query_tok = _estimate_tokens(user_query)

    # History signals
    hist_tok = sum(_estimate_tokens(m.get("content", "")) for m in msgs)
    non_system = [m for m in msgs if m.get("role") != "system"]
    turn_count = sum(1 for m in non_system if m.get("role") == "user")

    # Memory signals
    mem_tok = _estimate_tokens(memory_text)
    mem_entries = max(1, memory_text.count("\n")) if memory_text else 0

    # Tool signals
    tool_tok = sum(_estimate_tokens(t.get("description", "")) for t in tools_list)
    tool_cnt = len(tools_list)

    # Retrieval signals
    ret_tok = _estimate_tokens(retrieved_context)
    ret_frags = max(1, retrieved_context.count("\n\n")) if retrieved_context else 0

    # System
    sys_tok = _estimate_tokens(system_prompt)

    # Current context
    ctx_tok = sys_tok + hist_tok + mem_tok + tool_tok + ret_tok

    return ComplexitySignals(
        query_length=query_len,
        query_token_estimate=query_tok,
        history_available_tokens=hist_tok,
        history_message_count=len(msgs),
        memory_available_tokens=mem_tok,
        memory_entry_count=mem_entries,
        tool_count=tool_cnt,
        tool_schema_tokens=tool_tok,
        retrieved_tokens=ret_tok,
        retrieved_fragment_count=ret_frags,
        conversation_turn_count=turn_count,
        current_context_tokens=ctx_tok,
        system_tokens=sys_tok,
        domain_hint_present=bool(domain_hint),
        multi_tool=tool_cnt > 1,
        has_memory=mem_tok > 0,
        has_retrieval=ret_tok > 0,
    )


def compute_complexity(signals: ComplexitySignals) -> float:
    """Compute a deterministic task complexity score in [0.0, 1.0]."""
    # 1. Query complexity (0.0–0.2 weight)
    q_len = min(signals.query_length / 200, 1.0)
    q_tok = min(signals.query_token_estimate / 50, 1.0)
    query_score = 0.7 * q_len + 0.3 * q_tok

    # 2. History depth (0.0–0.3 weight)
    hist_depth = min(signals.conversation_turn_count / 50, 1.0)
    hist_volume = min(signals.history_available_tokens / 20_000, 1.0)
    history_score = 0.5 * hist_depth + 0.5 * hist_volume

    # 3. Tool complexity (0.0–0.2 weight)
    tool_count_score = min(signals.tool_count / 50, 1.0)
    tool_volume = min(signals.tool_schema_tokens / 10_000, 1.0)
    tool_score = 0.5 * tool_count_score + 0.5 * tool_volume

    # 4. Memory/retrieval density (0.0–0.15 weight)
    mem_density = min(signals.memory_available_tokens / 10_000, 1.0)
    ret_density = min(signals.retrieved_tokens / 10_000, 1.0)
    density_score = 0.5 * mem_density + 0.5 * ret_density

    # 5. Context pressure (0.0–0.10 weight)
    ctx_pressure = min(signals.current_context_tokens / 30_000, 1.0)

    # 6. Multi-dimension (0.0–0.05)
    active = sum([
        signals.has_memory,
        signals.has_retrieval,
        signals.multi_tool,
        signals.domain_hint_present,
    ])
    multi_score = min(active / 4.0, 1.0)

    complexity = (
        0.20 * query_score +
        0.30 * history_score +
        0.20 * tool_score +
        0.15 * density_score +
        0.10 * ctx_pressure +
        0.05 * multi_score
    )

    return max(0.0, min(1.0, complexity))


def compute_complexity_weighted(signals: ComplexitySignals, weights: ComplexityWeights = DEFAULT_WEIGHTS) -> float:
    """Compute complexity using custom weight configuration."""
    q_len = min(signals.query_length / 200, 1.0)
    q_tok = min(signals.query_token_estimate / 50, 1.0)
    query_score = 0.7 * q_len + 0.3 * q_tok

    hist_depth = min(signals.conversation_turn_count / 50, 1.0)
    hist_volume = min(signals.history_available_tokens / 20_000, 1.0)
    history_score = 0.5 * hist_depth + 0.5 * hist_volume

    tool_count_score = min(signals.tool_count / 50, 1.0)
    tool_volume = min(signals.tool_schema_tokens / 10_000, 1.0)
    tool_score = 0.5 * tool_count_score + 0.5 * tool_volume

    mem_density = min(signals.memory_available_tokens / 10_000, 1.0)
    ret_density = min(signals.retrieved_tokens / 10_000, 1.0)
    density_score = 0.5 * mem_density + 0.5 * ret_density

    ctx_pressure = min(signals.current_context_tokens / 30_000, 1.0)

    active = sum([signals.has_memory, signals.has_retrieval, signals.multi_tool, signals.domain_hint_present])
    multi_score = min(active / 4.0, 1.0)

    complexity = (
        weights.query_length * query_score +
        weights.history_depth * history_score +
        weights.tool_complexity * tool_score +
        weights.memory_retrieval * density_score +
        weights.context_pressure * ctx_pressure +
        weights.multi_dimension * multi_score
    )
    return max(0.0, min(1.0, complexity))


def classify_complexity(score: float) -> str:
    """Classify a complexity score into a human-readable label."""
    if score < _SIMPLE_THRESHOLD:
        return "simple"
    elif score < _MODERATE_THRESHOLD:
        return "moderate"
    elif score < _COMPLEX_THRESHOLD:
        return "complex"
    else:
        return "very_complex"


# ═══════════════════════════════════════════════════════════════════
# ADAPTIVE BUDGET PLANNER
# ═══════════════════════════════════════════════════════════════════


@dataclass
class AdaptiveBudgetPlan:
    """Result of the adaptive budget planner."""
    complexity_score: float = 0.0
    complexity_label: str = ""
    total_budget: int = 30_000
    budget_strategy: str = "adaptive"

    system: int = 0
    history: int = 0
    memory: int = 0
    tools: int = 0
    retrieved: int = 0

    available_system: int = 0
    available_history: int = 0
    available_memory: int = 0
    available_tools: int = 0
    available_retrieved: int = 0

    redistribution_count: int = 0
    redistribution_reason: str = ""

    signals: Optional[ComplexitySignals] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "complexity_score": round(self.complexity_score, 4),
            "complexity_label": self.complexity_label,
            "total_budget": self.total_budget,
            "budget_strategy": self.budget_strategy,
            "allocation": {
                "system": self.system,
                "history": self.history,
                "memory": self.memory,
                "tools": self.tools,
                "retrieved": self.retrieved,
            },
            "available": {
                "system": self.available_system,
                "history": self.available_history,
                "memory": self.available_memory,
                "tools": self.available_tools,
                "retrieved": self.available_retrieved,
            },
            "redistribution_count": self.redistribution_count,
            "redistribution_reason": self.redistribution_reason,
        }


def _infer_strategy(signals: ComplexitySignals, score: float) -> str:
    """Infer a human-readable budget strategy from signals and complexity."""
    if signals.tool_count > 30 and signals.tool_schema_tokens > 8000:
        return "tool_heavy"
    if signals.tool_count > 15 and signals.tool_schema_tokens > 5000 and score > 0.3:
        return "tool_assisted"
    if signals.conversation_turn_count > 40:
        return "history_heavy"
    if signals.memory_available_tokens > 15000:
        return "memory_heavy"
    if signals.retrieved_tokens > 10000:
        return "retrieval_heavy"
    if signals.conversation_turn_count > 20 and score > 0.25:
        return "extended_conversation"
    if score < _SIMPLE_THRESHOLD:
        return "simple_conversation"
    if score < _MODERATE_THRESHOLD:
        return "balanced"
    if score < _COMPLEX_THRESHOLD:
        return "complex_analysis"
    return "very_complex_research"


def plan_budget(
    signals: ComplexitySignals,
    max_total: int = 30_000,
    custom_weights: Optional[ComplexityWeights] = None,
) -> AdaptiveBudgetPlan:
    """Compute an adaptive budget allocation."""
    if custom_weights is not None:
        score = compute_complexity_weighted(signals, custom_weights)
    else:
        score = compute_complexity(signals)
    label = classify_complexity(score)

    budget_ratio = 0.3 + 0.7 * score
    total = max(5_000, min(max_total, int(max_total * budget_ratio)))
    total = int(round(total / 1000) * 1000)

    avail = {
        "system": signals.system_tokens,
        "history": signals.history_available_tokens,
        "memory": signals.memory_available_tokens,
        "tools": signals.tool_schema_tokens,
        "retrieved": signals.retrieved_tokens,
    }

    sys_alloc = min(max(_CATEGORY_RANGES["system"][0], avail["system"]), total // 2)
    remaining = total - sys_alloc

    categories = ["history", "memory", "tools", "retrieved"]
    weights: Dict[str, float] = {}
    for cat in categories:
        base = _CATEGORY_IMPORTANCE.get(cat, 0.15)
        if cat == "tools" and signals.multi_tool and score > 0.5:
            base *= 1.3
        if cat == "memory" and signals.has_memory and score > 0.5:
            base *= 1.2
        if cat == "history" and signals.conversation_turn_count > 20:
            base *= 1.2
        weights[cat] = base
    total_w = sum(weights.values())

    alloc: Dict[str, int] = {}
    for cat in categories:
        raw = int(remaining * weights[cat] / total_w)
        min_b, max_b = _CATEGORY_RANGES[cat]
        alloc[cat] = max(min_b, min(max_b, raw))

    alloc["system"] = sys_alloc

    for cat in _CATEGORY_NAMES:
        alloc[cat] = min(alloc[cat], max(avail.get(cat, 0), _CATEGORY_RANGES[cat][0]))

    current_sum = sum(alloc[cat] for cat in _CATEGORY_NAMES)
    redistribution_count = 0
    redistribution_reason = ""

    if current_sum < total:
        surplus = total - current_sum
        redistribution_count = surplus
        redistribution_reason = f"underfilled: {surplus} tokens redistributed"

        candidates = []
        for cat in categories:
            _, max_b = _CATEGORY_RANGES[cat]
            if alloc[cat] < avail[cat] and alloc[cat] < max_b:
                room = min(avail[cat], max_b) - alloc[cat]
                candidates.append((_CATEGORY_IMPORTANCE.get(cat, 0.1), cat, room))
        candidates.sort(key=lambda x: -x[0])

        for _, cat, room in candidates:
            give = min(surplus, room)
            if give <= 0:
                continue
            alloc[cat] += give
            surplus -= give
            redistribution_count += give
            if surplus <= 0:
                break

    elif current_sum > total:
        excess = current_sum - total
        redistribution_count = -excess
        redistribution_reason = f"overallocated: trimmed {excess} tokens"

        candidates = sorted(categories, key=lambda c: _CATEGORY_IMPORTANCE.get(c, 0.1))
        for cat in candidates:
            min_b, _ = _CATEGORY_RANGES[cat]
            can_cut = alloc[cat] - min_b
            cut = min(excess, can_cut)
            if cut <= 0:
                continue
            alloc[cat] -= cut
            excess -= cut
            if excess <= 0:
                break

    strategy = _infer_strategy(signals, score)

    return AdaptiveBudgetPlan(
        complexity_score=score,
        complexity_label=label,
        total_budget=total,
        budget_strategy=strategy,
        system=alloc["system"],
        history=alloc["history"],
        memory=alloc["memory"],
        tools=alloc["tools"],
        retrieved=alloc["retrieved"],
        available_system=signals.system_tokens,
        available_history=signals.history_available_tokens,
        available_memory=signals.memory_available_tokens,
        available_tools=signals.tool_schema_tokens,
        available_retrieved=signals.retrieved_tokens,
        redistribution_count=redistribution_count,
        redistribution_reason=redistribution_reason,
        signals=signals,
    )
