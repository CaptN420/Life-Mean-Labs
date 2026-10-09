"""SmartRouter — deterministic worker routing with pluggable strategies.

Adapted from Mia_Brain (captn/workers/orchestration/smart_router.py).
Implements:
1. Keyword-based routing table (WORKER_ROUTES)
2. Scoring by keyword overlap
3. Fairness boost for underused workers
4. Optional opposition mode for diversity
5. Difficulty-based adaptive top_k selection
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("SmartRouter")

# ── Worker Routes — keyword → workers mapping ──────────────────────────
WORKER_ROUTES: Dict[str, List[str]] = {
    # ── Code generation ──
    "code": ["deterministic_coder", "polyglot_coder"],
    "python": ["deterministic_coder"],
    "generate": ["deterministic_coder", "polyglot_coder"],
    "function": ["deterministic_coder"],
    # ── Debug / Fix ──
    "debug": ["fix_generator", "bug_worker"],
    "fix": ["fix_generator", "bug_worker"],
    "bug": ["bug_worker", "fix_generator"],
    "error": ["bug_worker", "fix_generator"],
    # ── Analysis ──
    "lint": ["tool_worker", "syntax_worker"],
    "linter": ["tool_worker", "syntax_worker"],
    "analyse": ["syntax_worker", "bug_worker"],
    "analysis": ["syntax_worker", "bug_worker"],
    "validate": ["validator"],
    "quality": ["validator"],
    # ── Math ──
    "math": ["math_validation_worker"],
    "equation": ["math_validation_worker"],
    "algebra": ["math_validation_worker"],
    "calculus": ["math_validation_worker"],
    # ── Physics ──
    "physics": ["physics_validation_worker"],
    # ── Chemistry ──
    "chemistry": ["chemistry_validation_worker"],
    # ── Logic ──
    "logic": ["logic_worker"],
    "syllogism": ["logic_worker"],
    "fallacy": ["logic_worker"],
    # ── General ──
    "analyze": ["syntax_worker", "bug_worker"],
    "inspect": ["syntax_worker", "bug_worker"],
}

# ── Worker Capabilities ────────────────────────────────────────────────
WORKER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "deterministic_coder": {
        "tags": ["code", "python", "generate", "function"],
        "domain": "coding",
        "description": "AST transforms: docstrings, type hints, normalization",
    },
    "polyglot_coder": {
        "tags": ["code", "multi-lang", "scaffold", "template"],
        "domain": "coding",
        "description": "Generate code scaffolds in any language",
    },
    "fix_generator": {
        "tags": ["fix", "repair", "patch"],
        "domain": "fixing",
        "description": "Generate fix templates from problem graph models",
    },
    "bug_worker": {
        "tags": ["bug", "error", "debug", "scan"],
        "domain": "analysis",
        "description": "Static bug detection and security patterns",
    },
    "syntax_worker": {
        "tags": ["syntax", "lint", "analyse", "inspect"],
        "domain": "analysis",
        "description": "Syntax validation and file integrity checks",
    },
    "tool_worker": {
        "tags": ["code", "review", "lint", "format", "math", "physics", "chemistry"],
        "domain": "execution",
        "description": "Unified worker wrapping all deterministic tools",
    },
    "validator": {
        "tags": ["validate", "quality", "syntax"],
        "domain": "quality",
        "description": "Final validation rules and quality gates",
    },
    "math_validation_worker": {
        "tags": ["math", "equation", "algebra", "calculus"],
        "domain": "transformation",
        "description": "Mathematics validation — algebra, calculus, numbers",
    },
    "physics_validation_worker": {
        "tags": ["physics", "force", "kinematics", "momentum"],
        "domain": "transformation",
        "description": "Physics validation rules",
    },
    "chemistry_validation_worker": {
        "tags": ["chemistry", "molecule", "reaction"],
        "domain": "transformation",
        "description": "Chemistry validation rules",
    },
    "logic_worker": {
        "tags": ["logic", "syllogism", "fallacy", "argument"],
        "domain": "analysis",
        "description": "Logic and argumentation analysis",
    },
}

# ── Opposition domains for diversity mode ──────────────────────────────
OPPOSITION_DOMAINS: Dict[str, str] = {
    "coding": "quality",
    "quality": "coding",
    "analysis": "fixing",
    "fixing": "analysis",
    "transformation": "acquisition",
}

_WORD_RE = re.compile(r"[a-zàâçéèêëîïôûùüÿñæœ]{3,}")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into",
    "their", "have", "has", "are", "was", "were", "not", "but",
    "task", "need", "want", "please", "just", "also",
}

# ── Difficulty levels ──────────────────────────────────────────────────
_DIFFICULTY_KEYWORDS: Dict[int, List[str]] = {
    0: [],
    1: [],
    2: ["complex", "analyse", "debug", "multi-step", "workflow"],
    3: ["complex", "multi-step", "debug", "analyse", "pipeline", "critical"],
    4: ["very complex", "critical", "production", "enterprise", "large-scale"],
}

_ADAPTIVE_TOP_K: Dict[int, int] = {
    0: 1,  # trivial
    1: 1,  # simple
    2: 2,  # medium (default)
    3: 3,  # complex
    4: 4,  # very complex
}


class SmartRouter:
    """Deterministic worker router with pluggable strategies.

    Selects the best worker(s) for a task by combining:
    - Explicit routing table (WORKER_ROUTES)
    - Keyword overlap scoring
    - Fairness boost for underused workers
    - Optional opposition mode for diversity
    - Difficulty-based adaptive top_k selection
    """

    def __init__(self):
        self.usage: Dict[str, int] = {name: 0 for name in WORKER_CAPABILITIES}
        self._rotation: Dict[str, int] = {}

    @staticmethod
    def classify_difficulty(description: str) -> int:
        """Classify task difficulty Level 0-4 based on description."""
        if not description or len(description.strip()) < 5:
            return 0

        low_desc = description.lower()
        word_count = len(low_desc.split())

        # Level 4: very complex
        severe = _DIFFICULTY_KEYWORDS[4]
        severe_hits = sum(1 for kw in severe if kw in low_desc)
        if severe_hits >= 3 and word_count > 15:
            return 4

        # Level 3: complex
        complex_words = _DIFFICULTY_KEYWORDS[3]
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
        cap = WORKER_CAPABILITIES.get(name)
        if not cap:
            return 0.0

        low_desc = (description or "").lower()
        words = {w for w in _WORD_RE.findall(low_desc) if w not in _STOPWORDS}
        score = 0.0

        # 1. Route table (keyword match)
        for key, targets in WORKER_ROUTES.items():
            if name in targets:
                if key in low_desc:
                    score += 5.0
                elif len(key) >= 4 and key[:4] in low_desc:
                    score += 3.0

        # Bonus for multiple route matches
        route_matches = sum(
            1 for key, targets in WORKER_ROUTES.items()
            if name in targets and (key in low_desc or (len(key) >= 4 and key[:4] in low_desc))
        )
        score += min(2.0, route_matches * 0.3)

        # 2. Worker tags in description
        tag_hits = sum(1 for tag in cap.get("tags", []) if tag in words or tag in low_desc)
        score += tag_hits * 1.5

        # 3. Description overlap
        desc_words = {w for w in _WORD_RE.findall(cap.get("description", "").lower())
                      if w not in _STOPWORDS}
        overlap = len(words & desc_words)
        score += overlap * 0.8

        # 4. Fairness boost (underused workers)
        total = sum(self.usage.values()) or 1
        avg = total / max(1, len(self.usage))
        underuse = max(0.0, (avg - self.usage[name]) * 0.1)
        score += int(underuse * 10) / 10.0

        return round(score, 3)

    def route(
        self,
        description: str,
        top_k: int = 1,
        opposition_mode: bool = False,
        exclude: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Select top_k workers for a task description.

        Args:
            description: Task description.
            top_k: Number of workers to select (adapted by difficulty).
            opposition_mode: If True, add a worker from opposite domain.
            exclude: Workers to exclude.

        Returns:
            Dict with selected, scores, usage, difficulty, etc.
        """
        difficulty = self.classify_difficulty(description)
        adaptive_top_k = _ADAPTIVE_TOP_K.get(difficulty, top_k or 1)
        effective_top_k = max(adaptive_top_k, top_k or 0)

        exclude_set: set = set(exclude) if exclude else set()

        scored: List[Tuple[str, float]] = [
            (name, self.score_worker(name, description))
            for name in WORKER_CAPABILITIES
            if name not in exclude_set
        ]

        # Keep workers with score > 0
        scored = [(n, s) for n, s in scored if s > 0]

        # Fallback: generic workers with small score
        if not scored:
            scored = [
                (name, 0.1)
                for name in WORKER_CAPABILITIES
                if name not in exclude_set
            ]

        # Sort by score descending
        scored.sort(key=lambda x: -x[1])

        # Round-robin rotation for equal scores
        key_words = _WORD_RE.findall((description or "").lower())
        rot_key = "|".join(sorted(set(key_words))) or "_"
        offset = self._rotation.get(rot_key, 0)
        self._rotation[rot_key] = offset + 1

        # Group by equal score and rotate
        groups: List[List[Tuple[str, float]]] = []
        for item in scored:
            if groups and abs(groups[-1][-1][1] - item[1]) < 1e-9:
                groups[-1].append(item)
            else:
                groups.append([item])

        flat: List[Tuple[str, float]] = []
        for group in groups:
            n = len(group)
            rotated = [group[(offset + i) % n] for i in range(n)]
            flat.extend(rotated)

        chosen = flat[:max(1, effective_top_k)]
        for name, _ in chosen:
            self.usage[name] += 1

        # Opposition mode
        opposing = []
        if opposition_mode and chosen:
            primary_domain = WORKER_CAPABILITIES.get(chosen[0][0], {}).get("domain", "")
            opp_domain = OPPOSITION_DOMAINS.get(primary_domain)

            if opp_domain:
                for name, cap in WORKER_CAPABILITIES.items():
                    if (cap.get("domain") == opp_domain
                            and name not in {n for n, _ in chosen}
                            and name not in exclude_set):
                        opp_score = self.score_worker(name, description)
                        opposing.append((name, round(opp_score + 0.01, 3)))
                        if len(opposing) >= max(1, effective_top_k):
                            break

        combined = chosen + opposing
        final_selection = combined[:max(effective_top_k, len(chosen) + len(opposing))]

        return {
            "description": description,
            "selected": [name for name, _ in final_selection],
            "scores": dict(final_selection),
            "usage": dict(self.usage),
            "difficulty": difficulty,
            "adaptive_top_k": effective_top_k,
            "opposition_mode": opposition_mode,
            "opposition_count": len(opposing),
            "timestamp": time.time(),
        }

    def resolve_pipeline_steps(self, description: str, top_k: int = 2) -> List[str]:
        """Generate pipeline steps from a task description.

        Orders selected workers by domain precedence:
        acquisition → analysis → coding → quality → coordination
        """
        result = self.route(description, top_k=top_k)
        selected = result["selected"]

        DOMAIN_ORDER = {
            "acquisition": 0,
            "analysis": 1,
            "coding": 2,
            "fixing": 2,
            "transformation": 3,
            "quality": 4,
            "coordination": 5,
        }

        def sort_key(name: str) -> tuple:
            cap = WORKER_CAPABILITIES.get(name, {})
            domain_order = DOMAIN_ORDER.get(cap.get("domain", ""), 99)
            priority = cap.get("pipeline_priority", 99)
            return (domain_order, priority)

        return sorted(selected, key=sort_key)

    def status(self) -> Dict[str, Any]:
        """Current router state."""
        return {
            "workers_loaded": sorted(WORKER_CAPABILITIES.keys()),
            "routes": len(WORKER_ROUTES),
            "usage": dict(self.usage),
        }


class RouterWorker(SmartRouter):
    """Bus wrapper for SmartRouter (Worker interface)."""

    def __init__(self, bus=None):
        SmartRouter.__init__(self)
        self.bus = bus
        self.is_active = False
        self.name = "smart_router"

    def initialize(self) -> bool:
        logger.info(f"[{self.name}] SmartRouter initialized: "
                    f"{len(WORKER_CAPABILITIES)} workers, {len(WORKER_ROUTES)} routes.")
        self.is_active = True
        return True

    def execute(self, message) -> None:
        from core.events.message import Message

        payload = getattr(message, "payload", {}) or {}
        task_id = payload.get("task_id")
        description = str(payload.get("description", payload.get("topic", "")) or "")
        top_k = int(payload.get("top_k", 1) or 1)
        opposition = bool(payload.get("opposition_mode", False))

        result = self.route(description, top_k=top_k, opposition_mode=opposition)
        logger.info(f"[{self.name}] '{description[:60]}' -> {result['selected']}")

        if self.bus is not None:
            self.bus.publish(Message(
                sender=self.name,
                destination="core",
                type="response",
                payload={
                    "task_id": task_id,
                    "current_step_plugin": self.name,
                    "valid": True,
                    "routing": result,
                },
            ))

    def shutdown(self) -> bool:
        self.is_active = False
        return True
