"""Tool detection mapping — keywords → tools.

Adapted from Mia_Brain (captn/runtime/tool_worker.py TOOL_DETECTION).
Maps natural language keywords to deterministic tool names with scores.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

# ── Dynamic tool registry — imports lazily to avoid circular deps ────────────

_TOOL_MODULES = {
    "math": ("library.tools.math", "MATH_TOOLS"),
    "chemistry": ("library.tools.chemistry", "CHEMISTRY_TOOLS"),
    "physics": ("library.tools.physics", "PHYSICS_TOOLS"),
    "coding": ("library.tools.coding", "CODING_TOOLS"),
    "logic": ("library.tools.logic", "LOGIC_TOOLS"),
}

_TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _get_tool_registry(domain: str) -> Dict[str, Any]:
    """Lazy-load a tool registry by domain."""
    if domain not in _TOOL_MODULES:
        return {}
    mod_path, attr_name = _TOOL_MODULES[domain]
    if domain not in _TOOL_REGISTRY:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            _TOOL_REGISTRY[domain] = getattr(mod, attr_name)
        except Exception as e:
            _TOOL_REGISTRY[domain] = {}
    return _TOOL_REGISTRY[domain]


def list_all_tools() -> List[Dict[str, str]]:
    """List all available tools across all domains."""
    tools = []
    for domain in sorted(_TOOL_MODULES.keys()):
        registry = _get_tool_registry(domain)
        for name, info in registry.items():
            tools.append({"name": f"{domain}_{name}", "domain": domain, "description": info.get("desc", "")})
    return tools

# ── Tool detection mapping: keywords → (tool_name, param_key, default_kwargs) ──
TOOL_DETECTION: Dict[str, List[Dict[str, Any]]] = {
    # ── Code Review (ruff + pylint + flake8 + bandit + mypy) ──
    "review": [
        {"tool": "review_review", "param": "code", "score": 10},
    ],
    "code review": [
        {"tool": "review_review", "param": "code", "score": 15},
    ],
    "lint": [
        {"tool": "review_review", "param": "code", "score": 10},
    ],
    "ruff": [{"tool": "review_review", "param": "code", "score": 15}],
    "mypy": [{"tool": "review_review", "param": "code", "score": 15}],
    "pylint": [{"tool": "review_review", "param": "code", "score": 15}],
    "format code": [{"tool": "review_format", "param": "code", "score": 15}],
    "security audit": [{"tool": "review_review", "param": "code", "score": 12}],
    "type check": [{"tool": "review_review", "param": "code", "score": 10}],

    # ── Algebra ──
    "simplify": [
        {"tool": "algebra_simplify", "param": "expression", "score": 15},
    ],
    "expand": [
        {"tool": "algebra_expand", "param": "expression", "score": 15},
    ],
    "derivative": [
        {"tool": "algebra_derivative", "param": "expression", "score": 15},
    ],
    "solve": [
        {"tool": "algebra_solve", "param": "equation", "score": 15},
    ],
    "factor": [
        {"tool": "algebra_factor", "param": "expression", "score": 15},
    ],

    # ── Math tools (simplified - most algorithms now use coding_generator) ──
    "trig": [{"tool": "math_trig", "param": "angle_deg", "score": 10}],
    "logarithm": [{"tool": "math_log_", "param": "value", "score": 10}],
    "bayes": [{"tool": "math_bayes_theorem", "param": "prior", "score": 12}],

    # ── Physics ──
    "force": [{"tool": "physics_force", "param": "mass", "score": 12}],
    "ohms law": [{"tool": "physics_ohms_law", "param": "voltage", "score": 15}],
    "kinematics": [{"tool": "physics_kinematics", "param": "v0", "score": 12}],
    "momentum": [{"tool": "physics_momentum", "param": "mass", "score": 12}],
    "density": [{"tool": "physics_density", "param": "mass", "score": 10}],

    # ── Chemistry ──
    "molar mass": [{"tool": "chemistry_molar_mass", "param": "formula", "score": 15}],
    "ph": [{"tool": "chemistry_ph", "param": "H_conc", "score": 12}],
    "mole": [{"tool": "chemistry_mole", "param": "mass", "score": 10}],
    "balance": [{"tool": "chemsym_balance", "param": "equation", "score": 12}],

    # ── Logic ──
    "syllogism": [{"tool": "logic_syllogism", "param": "major", "score": 12}],
    "fallacy": [{"tool": "logic_fallacy", "param": "text", "score": 12}],

    # ── Coding tools ──
    "loc": [{"tool": "coding_loc", "param": "source", "score": 10}],
    "cyclomatic": [{"tool": "coding_cyclomatic", "param": "source", "score": 10}],
    "regex": [{"tool": "coding_validate_regex", "param": "pattern", "score": 10}],
    "write code": [{"tool": "coding_generator", "param": "description", "score": 20}],
    "coding task": [{"tool": "coding_generator", "param": "description", "score": 20}],
    "generate function": [{"tool": "coding_generator", "param": "description", "score": 20}],
    "implement": [{"tool": "coding_generator", "param": "description", "score": 18}],
    "fibonacci": [{"tool": "coding_generator", "param": "description", "score": 15}],
    "factorial": [{"tool": "coding_generator", "param": "description", "score": 15}],
    "gcd": [{"tool": "coding_generator", "param": "description", "score": 15}],
    "lcm": [{"tool": "coding_generator", "param": "description", "score": 15}],
    "prime": [{"tool": "coding_generator", "param": "description", "score": 15}],
    "sort": [{"tool": "coding_generator", "param": "description", "score": 15}],
    "search": [{"tool": "coding_generator", "param": "description", "score": 15}],

    # ── Math (advanced) ──
    "integrate": [{"tool": "eqsolve_integrate", "param": "expr", "score": 12}],
    "taylor": [{"tool": "eqsolve_taylor", "param": "expr", "score": 10}],
    "limit": [{"tool": "eqsolve_limit", "param": "expr", "score": 12}],
}

# Domain map for filtering
DOMAIN_MAP: Dict[str, str] = {
    # Coding
    "review": "coding", "code review": "coding", "lint": "coding",
    "ruff": "coding", "mypy": "coding", "pylint": "coding",
    "format code": "coding", "security audit": "coding", "type check": "coding",
    "loc": "coding", "cyclomatic": "coding", "regex": "coding",
    "write code": "coding", "coding task": "coding", "generate function": "coding",
    "implement": "coding", "fibonacci": "coding", "factorial": "coding",
    "gcd": "coding", "lcm": "coding", "prime": "coding", "sort": "coding",
    "search": "coding",
    # Math
    "simplify": "math", "expand": "math", "derivative": "math",
    "solve": "math", "factor": "math",
    "trig": "math", "logarithm": "math", "bayes": "math",
    "integrate": "math", "taylor": "math", "limit": "math",
    # Physics
    "force": "physics", "ohms law": "physics", "kinematics": "physics",
    "momentum": "physics", "density": "physics",
    # Chemistry
    "molar mass": "chemistry", "ph": "chemistry", "mole": "chemistry",
    "balance": "chemistry",
    # Logic
    "syllogism": "philosophy", "fallacy": "philosophy",
}


def detect_tool(description: str, source_code: str = "") -> dict | None:
    """Auto-detect the best tool from a natural language description.

    Args:
        description: Natural language description of the task.
        source_code: Optional source code to include in kwargs.

    Returns:
        Dict with tool_name, param_key, kwargs, score, domain or None.
    """
    low_desc = description.lower() if description else ""
    low_source = source_code.lower() if source_code else ""

    best_score = 0
    best_match = None

    for key, tools in TOOL_DETECTION.items():
        key_low = key.lower()
        # Match multi-word and single-word patterns
        if len(key_low) <= 3:
            # Short keys must match as whole words
            import re
            pattern = rf'\b{re.escape(key_low)}\b'
            if re.search(pattern, low_desc) or re.search(pattern, low_source):
                for t in tools:
                    if t["score"] > best_score:
                        best_score = t["score"]
                        best_match = {
                            "tool_name": t["tool"],
                            "param_key": t["param"],
                            "kwargs": {},
                            "score": t["score"],
                            "domain": DOMAIN_MAP.get(key, "general"),
                        }
        else:
            # Longer keys can use substring matching
            if key_low in low_desc or key_low in low_source:
                for t in tools:
                    if t["score"] > best_score:
                        best_score = t["score"]
                        best_match = {
                            "tool_name": t["tool"],
                            "param_key": t["param"],
                            "kwargs": {},
                            "score": t["score"],
                            "domain": DOMAIN_MAP.get(key, "general"),
                        }

    # If we found a match, check if source code was provided
    if best_match and source_code:
        param = best_match["param_key"]
        if param in ("code", "source", "expression", "equation"):
            best_match["kwargs"][param] = source_code
        elif "code" in param or "source" in param:
            best_match["kwargs"]["code"] = source_code

    return best_match


def list_tool_domains() -> List[str]:
    """List all available tool domains."""
    return sorted(set(DOMAIN_MAP.values()))
