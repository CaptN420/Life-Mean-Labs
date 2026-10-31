"""CaptN Runtime v1 — Intelligent LLM Runtime Architecture.

Architecture::

    CAPTN RUNTIME
         │
    ┌────┴────┬─────────────┐
    │         │             │
 Routing   Context      Execution
    │         │             │
    │    ┌────┴────┐    ┌────┴────┐
    │    │ Adaptive│    │ Tools  │
    │    │ Memory  │    │ Sandbox│
    │    │Retrieval│    │ MCP    │
    │    └─────────┘    └────────┘
    │         │             │
    └────┬────┘             │
         │                 │
      Provider            │
         │                 │
         ▼                 │
    LLM Response          │
         │                 │
    ┌────┴─────────────────┴──┐
    │                         │
 Telemetry                Experience
    │                         │
    └────────────┬────────────┘
                 │
                 ▼
            Future Brain

Usage:
    from captn.runtime import CaptNRuntime

    runtime = CaptNRuntime()
    result = await runtime.run(
        query="Explain quantum computing",
        context=["...", "..."],
        memory=memory_store,
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("captn.runtime")


# ── Core Data Structures ─────────────────────────────────────────────────────


@dataclass
class RuntimeConfig:
    """Configuration for the CaptN Runtime."""

    # Model selection
    default_model: str = "deepseek/deepseek-v4-flash"
    fallback_model: str = "openai/gpt-4o-mini"

    # Context management
    max_context_tokens: int = 128000
    compression_enabled: bool = True
    compression_ratio: float = 0.65  # Target reduction ratio

    # Memory
    memory_enabled: bool = True
    memory_max_entries: int = 1000
    memory_retrieval_top_k: int = 5

    # Telemetry
    telemetry_enabled: bool = True
    telemetry_save_path: str = "captn_telemetry.jsonl"

    # Experience
    experience_enabled: bool = True
    experience_storage_path: str = "captn_experiences.jsonl"


@dataclass
class RuntimeResult:
    """Result of a runtime execution."""

    success: bool = False
    response: str = ""
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    context_reduction: float = 0.0
    compression_applied: bool = False
    memory_hits: int = 0
    experience_replayed: bool = False
    error: Optional[str] = None

    def report(self) -> str:
        """Generate a human-readable report."""
        return (
            f"✅ Success: {self.success}\n"
            f"📊 Model: {self.model_used}\n"
            f"📥 Tokens in: {self.tokens_input}\n"
            f"📤 Tokens out: {self.tokens_output}\n"
            f"⏱️  Latency: {self.latency_ms:.0f}ms\n"
            f"💰 Cost: ${self.cost_usd:.4f}\n"
            f"📉 Context reduction: {self.context_reduction:.1%}\n"
            f"🧠 Memory hits: {self.memory_hits}\n"
            f"💾 Experience replayed: {self.experience_replayed}"
        )


@dataclass
class TelemetryEvent:
    """Telemetry event for tracking runtime performance."""

    event_type: str  # "request", "response", "compression", "memory_hit", "experience_replay"
    timestamp: float = field(default_factory=time.time)
    query_hash: str = ""
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    context_reduction: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "query_hash": self.query_hash,
            "model": self.model,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "context_reduction": self.context_reduction,
            "metadata": self.metadata,
        }


# ── Routing Component ────────────────────────────────────────────────────────


class ModelRouter:
    """Routes queries to appropriate models based on task type.

    Enhanced with:
    - Difficulty classification (0-4)
    - Opposition mode for diversity
    - Fairness boost for underused workers
    - Domain-specific routing tables
    """

    # ── Worker Definitions ───────────────────────────────────────────────

    WORKER_CAPABILITIES = {
        "deepseek_coder_v2": {
            "tags": ["code", "python", "generate", "function", "implement"],
            "domain": "coding",
            "description": "DeepSeek Coder v2 — expert code generation",
        },
        "deepseek_v4_flash": {
            "tags": ["analysis", "explain", "compare", "general"],
            "domain": "analysis",
            "description": "DeepSeek v4 Flash — fast analysis and reasoning",
        },
        "gpt_4": {
            "tags": ["math", "calculate", "equation", "code", "quality"],
            "domain": "quality",
            "description": "GPT-4 — high-quality code and math",
        },
        "claude_sonnet": {
            "tags": ["creative", "write", "analyze", "compare"],
            "domain": "creative",
            "description": "Claude Sonnet — creative and analytical",
        },
        "claude_haiku": {
            "tags": ["fast", "simple", "quick", "summary"],
            "domain": "speed",
            "description": "Claude Haiku — fast and lightweight",
        },
        "deepseek_math": {
            "tags": ["math", "calculus", "algebra", "equation", "calculate"],
            "domain": "math",
            "description": "DeepSeek Math — specialized mathematics",
        },
    }

    # ── Routing Tables ───────────────────────────────────────────────────

    WORKER_ROUTES = {
        "code": ["deepseek_coder_v2", "gpt_4"],
        "python": ["deepseek_coder_v2"],
        "generate": ["deepseek_coder_v2", "gpt_4"],
        "function": ["deepseek_coder_v2"],
        "debug": ["deepseek_v4_flash", "gpt_4"],
        "fix": ["deepseek_v4_flash", "gpt_4"],
        "bug": ["deepseek_v4_flash", "gpt_4"],
        "error": ["deepseek_v4_flash", "gpt_4"],
        "lint": ["gpt_4"],
        "analyse": ["deepseek_v4_flash", "claude_sonnet"],
        "analysis": ["deepseek_v4_flash", "claude_sonnet"],
        "validate": ["gpt_4"],
        "quality": ["gpt_4"],
        "math": ["deepseek_math", "gpt_4"],
        "equation": ["deepseek_math", "gpt_4"],
        "algebra": ["deepseek_math", "gpt_4"],
        "calculus": ["deepseek_math", "gpt_4"],
        "physics": ["deepseek_v4_flash", "gpt_4"],
        "chemistry": ["deepseek_v4_flash", "gpt_4"],
        "logic": ["deepseek_v4_flash", "claude_sonnet"],
        "creative": ["claude_sonnet", "claude_haiku"],
        "write": ["claude_sonnet", "claude_haiku"],
        "summary": ["claude_haiku", "deepseek_v4_flash"],
        "fast": ["claude_haiku", "deepseek_v4_flash"],
        "general": ["deepseek_v4_flash", "gpt_4"],
    }

    # ── Opposition Domains ───────────────────────────────────────────────

    OPPOSITION_DOMAINS = {
        "coding": "quality",
        "quality": "coding",
        "analysis": "creative",
        "creative": "analysis",
        "math": "general",
        "general": "math",
    }

    # ── Difficulty Keywords ──────────────────────────────────────────────

    _DIFFICULTY_KEYWORDS = {
        0: [],
        1: [],
        2: ["complex", "analyse", "debug", "multi-step", "workflow"],
        3: ["complex", "multi-step", "debug", "analyse", "pipeline", "critical"],
        4: ["very complex", "critical", "production", "enterprise", "large-scale"],
    }

    _ADAPTIVE_TOP_K = {0: 1, 1: 1, 2: 2, 3: 3, 4: 4}

    def __init__(self):
        self.usage: Dict[str, int] = {name: 0 for name in self.WORKER_CAPABILITIES}
        self._rotation: Dict[str, int] = {}

    @staticmethod
    def classify_difficulty(description: str) -> int:
        """Classify task difficulty Level 0-4 based on description."""
        if not description or len(description.strip()) < 5:
            return 0

        low_desc = description.lower()
        word_count = len(low_desc.split())

        # Level 4: very complex
        severe = ModelRouter._DIFFICULTY_KEYWORDS[4]
        severe_hits = sum(1 for kw in severe if kw in low_desc)
        if severe_hits >= 3 and word_count > 15:
            return 4

        # Level 3: complex
        complex_words = ModelRouter._DIFFICULTY_KEYWORDS[3]
        complex_hits = sum(1 for kw in complex_words if kw in low_desc)
        if complex_hits >= 2 or (complex_hits >= 1 and word_count > 20):
            return 3

        # Level 1: simple (short descriptions without complex keywords)
        if word_count <= 5:
            return 1

        # Level 2: medium (default)
        return 2

    def score_worker(self, name: str, description: str) -> float:
        """Score a worker for a task description."""
        cap = self.WORKER_CAPABILITIES.get(name)
        if not cap:
            return 0.0

        low_desc = (description or "").lower()

        # 1. Route table (keyword match)
        score = 0.0
        for key, targets in self.WORKER_ROUTES.items():
            if name in targets:
                if key in low_desc:
                    score += 5.0

        # 2. Worker tags in description
        tag_hits = sum(1 for tag in cap.get("tags", []) if tag in low_desc)
        score += tag_hits * 1.5

        # 3. Fairness boost (underused workers)
        total = sum(self.usage.values()) or 1
        avg = total / max(1, len(self.usage))
        underuse = max(0.0, (avg - self.usage[name]) * 0.1)
        score += int(underuse * 10) / 10.0

        return round(score, 3)

    def route(
        self,
        query: str,
        task_type: Optional[str] = None,
        top_k: int = 1,
        opposition_mode: bool = False,
    ) -> Dict[str, Any]:
        """Select the best model(s) for a query.

        Args:
            query: The user query or task description.
            task_type: Optional explicit task type override.
            top_k: Number of models to return.
            opposition_mode: If True, add a model from opposite domain.

        Returns:
            Dict with selected models, scores, difficulty, etc.
        """
        # Classify difficulty
        difficulty = self.classify_difficulty(query)
        adaptive_top_k = self._ADAPTIVE_TOP_K.get(difficulty, top_k)
        effective_top_k = max(adaptive_top_k, top_k)

        # Score all workers
        scored = [
            (name, self.score_worker(name, query))
            for name in self.WORKER_CAPABILITIES
        ]
        scored = [(n, s) for n, s in scored if s > 0]
        scored.sort(key=lambda x: -x[1])

        # Fallback: generic workers
        if not scored:
            scored = [(name, 0.1) for name in self.WORKER_CAPABILITIES]

        # Select top_k
        chosen = scored[:effective_top_k]
        for name, _ in chosen:
            self.usage[name] = self.usage.get(name, 0) + 1

        # Opposition mode
        opposing = []
        if opposition_mode and chosen:
            primary_domain = self.WORKER_CAPABILITIES.get(chosen[0][0], {}).get("domain", "")
            opp_domain = self.OPPOSITION_DOMAINS.get(primary_domain)
            if opp_domain:
                for name, cap in self.WORKER_CAPABILITIES.items():
                    if (cap.get("domain") == opp_domain
                            and name not in {n for n, _ in chosen}):
                        opp_score = self.score_worker(name, query)
                        opposing.append((name, round(opp_score + 0.01, 3)))
                        if len(opposing) >= effective_top_k:
                            break

        combined = chosen + opposing
        final_selection = combined[:max(effective_top_k, len(chosen) + len(opposing))]

        return {
            "query": query,
            "selected": [name for name, _ in final_selection],
            "scores": dict(final_selection),
            "usage": dict(self.usage),
            "difficulty": difficulty,
            "adaptive_top_k": effective_top_k,
            "opposition_mode": opposition_mode,
            "opposition_count": len(opposing),
        }

    def stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        return {
            "workers": sorted(self.WORKER_CAPABILITIES.keys()),
            "routes": len(self.WORKER_ROUTES),
            "usage": dict(self.usage),
        }


# ── Context Engine ───────────────────────────────────────────────────────────


class ContextEngine:
    """Manages context compression and retrieval.

    Integrates with the production ContextBudget from code_lab.compression
    for relevance-based selection within token budgets.
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._history: List[Dict[str, Any]] = []
        self._memory: List[Dict[str, Any]] = []
        self._budget = None  # Lazy-initialized ContextBudget

    @property
    def budget(self):
        """Lazy-initialize the ContextBudget from code_lab.compression."""
        if self._budget is None:
            try:
                from code_lab.compression import ContextBudget, DEFAULT_BUDGET_CONFIG
                # Map our config to the production budget config
                budget_config = DEFAULT_BUDGET_CONFIG
                self._budget = ContextBudget(model=self.config.default_model)
            except ImportError:
                logger.warning("code_lab.compression not available, using fallback")
                self._budget = None
        return self._budget

    def compress(self, messages: List[Dict[str, str]], max_tokens: int) -> Dict[str, Any]:
        """Compress context messages using production ContextBudget.

        Uses relevance-based selection from code_lab.compression when available,
        falls back to simple recency-based compression.
        """
        if not self.config.compression_enabled:
            return {"compressed": False, "messages": messages, "reduction": 0.0}

        # Try production ContextBudget first
        if self.budget:
            try:
                result = self.budget.select(
                    messages=messages,
                    user_query="",  # Could pass actual query
                    dry_run=True,
                )
                return {
                    "compressed": True,
                    "messages": result.selected_messages,
                    "reduction": result.original_total_tokens > 0 and (1 - result.selected_total_tokens / result.original_total_tokens) or 0.0,
                    "budget_report": result.report(),
                }
            except Exception as e:
                logger.debug(f"ContextBudget failed: {e}, using fallback")

        # Fallback: simple recency-based compression
        total = len(messages)
        if total <= 10:
            return {"compressed": False, "messages": messages, "reduction": 0.0}

        keep_recent = max(5, int(total * (1 - self.config.compression_ratio)))
        compressed_messages = messages[-keep_recent:]

        # Add summary of compressed messages
        if len(messages) > keep_recent:
            compressed_messages = [
                {
                    "role": "system",
                    "content": f"[Summary of {len(messages) - keep_recent} older messages: context was compressed from {total} to {len(compressed_messages)} messages]"
                }
            ] + compressed_messages

        reduction = 1.0 - (len(compressed_messages) / total)
        return {
            "compressed": True,
            "messages": compressed_messages,
            "reduction": reduction,
        }

    def add_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self._history.append({"role": role, "content": content})
        if len(self._history) > 100:
            self._history = self._history[-100:]

    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return list(self._history)

    def save_memory(self, key: str, value: str, metadata: Optional[Dict] = None) -> None:
        """Save a memory entry."""
        self._memory.append({
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })
        if len(self._memory) > self.config.memory_max_entries:
            self._memory = self._memory[-self.config.memory_max_entries:]

    def retrieve_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant memory entries."""
        if not self.config.memory_enabled:
            return []

        # Simple keyword matching (could be enhanced with embeddings)
        query_words = set(query.lower().split())
        scored = []
        for entry in self._memory:
            score = sum(1 for word in query_words if word in entry["value"].lower())
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        return [entry for _, entry in scored[:top_k]]


# ── Experience Engine ────────────────────────────────────────────────────────


class ExperienceEngine:
    """Manages experience storage and retrieval."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._experiences: Dict[str, Dict[str, Any]] = {}

    def store_experience(
        self,
        query: str,
        response: str,
        result: RuntimeResult,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Store an experience record."""
        exp_id = f"EXP-{len(self._experiences) + 1:04d}"
        self._experiences[exp_id] = {
            "id": exp_id,
            "query": query,
            "response": response,
            "result": result.to_dict() if isinstance(result, RuntimeResult) else result,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        return exp_id

    def find_similar(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Find similar past experiences."""
        if not self.config.experience_enabled:
            return []

        # Simple keyword matching (could be enhanced with embeddings)
        query_words = set(query.lower().split())
        scored = []
        for exp in self._experiences.values():
            score = sum(1 for word in query_words if word in exp["query"].lower())
            if score > 0:
                scored.append((score, exp))

        scored.sort(key=lambda x: -x[0])
        return [exp for _, exp in scored[:top_k]]

    def get_experience(self, exp_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific experience."""
        return self._experiences.get(exp_id)

    def stats(self) -> Dict[str, Any]:
        """Get experience statistics."""
        return {
            "total_experiences": len(self._experiences),
        }


# ── Telemetry Engine ─────────────────────────────────────────────────────────


class TelemetryEngine:
    """Collects and persists telemetry data."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._events: List[TelemetryEvent] = []

    def record_event(self, event: TelemetryEvent) -> None:
        """Record a telemetry event."""
        if not self.config.telemetry_enabled:
            return
        self._events.append(event)

    def save_to_disk(self, path: Optional[str] = None) -> int:
        """Save telemetry to JSONL file."""
        save_path = path or self.config.telemetry_save_path
        with open(save_path, "w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return len(self._events)

    def get_stats(self) -> Dict[str, Any]:
        """Get telemetry statistics."""
        if not self._events:
            return {"total_events": 0}

        total_latency = sum(e.latency_ms for e in self._events)
        total_cost = sum(e.cost_usd for e in self._events)
        total_tokens_in = sum(e.tokens_input for e in self._events)
        total_tokens_out = sum(e.tokens_output for e in self._events)

        return {
            "total_events": len(self._events),
            "avg_latency_ms": total_latency / len(self._events),
            "total_cost_usd": total_cost,
            "total_tokens_input": total_tokens_in,
            "total_tokens_output": total_tokens_out,
            "event_types": {
                "request": sum(1 for e in self._events if e.event_type == "request"),
                "response": sum(1 for e in self._events if e.event_type == "response"),
                "compression": sum(1 for e in self._events if e.event_type == "compression"),
                "memory_hit": sum(1 for e in self._events if e.event_type == "memory_hit"),
            },
        }


# ── Main Runtime ─────────────────────────────────────────────────────────────


class CaptNRuntime:
    """Main CaptN Runtime class.

    Orchestrates routing, context management, experience retrieval,
    and telemetry collection.
    """

    def __init__(self, config: Optional[RuntimeConfig] = None):
        self.config = config or RuntimeConfig()
        self.router = ModelRouter()
        self.context_engine = ContextEngine(self.config)
        self.experience_engine = ExperienceEngine(self.config)
        self.telemetry = TelemetryEngine(self.config)

    async def run(
        self,
        query: str,
        context: Optional[List[str]] = None,
        memory_store: Optional[Any] = None,
        task_type: Optional[str] = None,
    ) -> RuntimeResult:
        """Execute a query through the runtime pipeline."""
        start_time = time.time()

        # 1. Find similar experiences
        similar_exps = self.experience_engine.find_similar(query)
        experience_replayed = False
        if similar_exps:
            experience_replayed = True
            logger.info(f"Found {len(similar_exps)} similar experiences")

        # 2. Retrieve relevant memory
        memory_hits = 0
        if self.config.memory_enabled:
            retrieved_memory = self.context_engine.retrieve_memory(query)
            memory_hits = len(retrieved_memory)
            if retrieved_memory:
                logger.info(f"Retrieved {memory_hits} memory entries")

        # 3. Route to appropriate model
        model = self.router.route(query, task_type)

        # 4. Compress context if needed
        messages = [{"role": "user", "content": query}]
        if context:
            messages.extend([{"role": "system", "content": c} for c in context])

        compression_result = self.context_engine.compress(messages, self.config.max_context_tokens)
        context_reduction = compression_result["reduction"]

        # 5. Record telemetry
        self.telemetry.record_event(TelemetryEvent(
            event_type="request",
            query_hash=hash(query),
            model=model,
            tokens_input=len(query.split()) * 2,  # Rough estimate
        ))

        # 6. Simulate LLM call (replace with real implementation)
        # In production, this would call the actual LLM provider
        simulated_response = f"Response to: {query[:50]}... [simulated]"

        elapsed_ms = (time.time() - start_time) * 1000

        # 7. Create result
        result = RuntimeResult(
            success=True,
            response=simulated_response,
            model_used=model,
            tokens_input=len(query.split()) * 2,
            tokens_output=50,
            latency_ms=elapsed_ms,
            cost_usd=0.001,
            context_reduction=context_reduction,
            compression_applied=compression_result["compressed"],
            memory_hits=memory_hits,
            experience_replayed=experience_replayed,
        )

        # 8. Store experience
        if self.config.experience_enabled:
            self.experience_engine.store_experience(query, simulated_response, result)

        # 9. Record response telemetry
        self.telemetry.record_event(TelemetryEvent(
            event_type="response",
            query_hash=hash(query),
            model=model,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            latency_ms=result.latency_ms,
            cost_usd=result.cost_usd,
            context_reduction=result.context_reduction,
        ))

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get runtime status."""
        return {
            "config": {
                "default_model": self.config.default_model,
                "compression_enabled": self.config.compression_enabled,
                "memory_enabled": self.config.memory_enabled,
                "telemetry_enabled": self.config.telemetry_enabled,
            },
            "routing": self.router.stats(),
            "experience": self.experience_engine.stats(),
            "telemetry": self.telemetry.get_stats(),
        }
