"""Coding tools — Deterministic coding/software toolkit (6 tools).

Pure Python, zero LLM. Adapted from Mia_Brain (captn/tools/coding_tools.py).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def loc(source="") -> Dict[str, Any]:
    if not source:
        source = "def foo():\n    pass"
    lines = source.splitlines()
    cl = sum(1 for l in lines if l.strip() and not l.strip().startswith("#"))
    bk = sum(1 for l in lines if not l.strip())
    return {"valid": True, "total": len(lines), "code": cl, "blank": bk}


def cyclomatic(source="") -> Dict[str, Any]:
    if not source:
        source = "def f():\n    if x: pass\n    for y in z: pass"
    d = len(re.findall(r"\b(if|elif|for|while|and|or|except|with|assert)\b", source))
    r = "A(simple)" if d < 10 else "B(moderate)" if d < 20 else "C(complex)" if d < 40 else "D(dangerous)"
    return {"valid": True, "cyclomatic": d + 1, "decision_points": d, "rating": r}


def identify_type(value="42") -> Dict[str, Any]:
    v = value.strip()
    if v in ("True", "False"):
        return {"valid": True, "type": "bool"}
    if v == "None":
        return {"valid": True, "type": "null"}
    try:
        int(v)
        return {"valid": True, "type": "int"}
    except:
        pass
    try:
        float(v)
        return {"valid": True, "type": "float"}
    except:
        pass
    if v.startswith("[") and v.endswith("]"):
        return {"valid": True, "type": "list"}
    if v.startswith("{") and v.endswith("}"):
        return {"valid": True, "type": "dict"}
    return {"valid": True, "type": "str"}


def validate_regex(pattern="^[a-z]+$") -> Dict[str, Any]:
    try:
        re.compile(pattern)
        return {"valid": True, "is_valid": True}
    except re.error as e:
        return {"valid": False, "is_valid": False, "error": str(e)}


def regex_match(pattern=r"\d+", text="abc123") -> Dict[str, Any]:
    try:
        m = re.search(pattern, text)
        return {"valid": True, "matches": m is not None, "matched": m.group(0)[:100] if m else ""}
    except re.error as e:
        return {"valid": False, "error": str(e)}


def complexity_estimate(LOC=1000) -> Dict[str, Any]:
    effort = 2.4 * (LOC / 1000) ** 1.05
    time = 2.5 * effort ** 0.38
    return {"valid": True, "effort_person_months": round(effort, 2), "time_months": round(time, 2)}


CODING_TOOLS: Dict[str, Dict[str, Any]] = {
    "loc": {"fn": loc, "desc": "Lines of code"},
    "cyclomatic": {"fn": cyclomatic, "desc": "Cyclomatic complexity"},
    "identify_type": {"fn": identify_type, "desc": "Type identification"},
    "validate_regex": {"fn": validate_regex, "desc": "Regex validation"},
    "regex_match": {"fn": regex_match, "desc": "Regex matching"},
    "complexity_estimate": {"fn": complexity_estimate, "desc": "Effort from LOC"},
}


def list_tools() -> List[Dict[str, str]]:
    return [{"name": k, "description": v["desc"]} for k, v in CODING_TOOLS.items()]


def execute(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a coding tool by name with kwargs."""
    if tool_name not in CODING_TOOLS:
        return {"valid": False, "error": f"Unknown tool: {tool_name}"}
    fn = CODING_TOOLS[tool_name]["fn"]
    try:
        result = fn(**kwargs)
        return result
    except Exception as e:
        return {"valid": False, "error": str(e)}
