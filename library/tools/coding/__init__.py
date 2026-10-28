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


# ── Code Generator tool ─────────────────────────────────────────────────────

def coding_generator(
    description: str = "",
    difficulty: int = 2,
    function_name: str = "",
    test_cases: str = "",
) -> Dict[str, Any]:
    """Generate Python code from a natural language task description.

    This is a DETERMINISTIC code generator that produces simple Python
    functions based on pattern matching the task description. It handles
    common algorithmic patterns (fibonacci, factorial, gcd, etc.) and
    returns the generated source code.

    Args:
        description: Natural language description of the coding task.
        difficulty: Task difficulty level (1-5).
        function_name: Optional specific function name to generate.
        test_cases: Optional test cases to include.

    Returns:
        Dict with 'source' (generated code), 'valid', and metadata.
    """
    if not description:
        return {"valid": False, "error": "No description provided"}

    desc_lower = description.lower()
    source = ""
    func_name = function_name or _extract_function_name(desc_lower)

    # ── Pattern-based code generation ──────────────────────────────────────

    # Fibonacci
    if "fibonacci" in desc_lower or "fib" in desc_lower:
        source = f'''def {func_name}(n: int) -> list[int]:
            """Return the first n Fibonacci numbers."""
            if n <= 0:
                return []
            if n == 1:
                return [0]
            seq = [0, 1]
            for _ in range(2, n):
                seq.append(seq[-1] + seq[-2])
            return seq'''

    # Factorial
    elif "factorial" in desc_lower or "n!" in desc_lower:
        source = f'''def {func_name}(n: int) -> int:
            """Return n factorial."""
            if n < 0:
                raise ValueError("n must be >= 0")
            result = 1
            for i in range(2, n + 1):
                result *= i
            return result'''

    # GCD/LCM
    elif "gcd" in desc_lower or "greatest common divisor" in desc_lower:
        source = f'''def {func_name}(a: int, b: int) -> int:
            """Return the greatest common divisor of a and b."""
            while b:
                a, b = b, a % b
            return abs(a)'''

    elif "lcm" in desc_lower or "least common multiple" in desc_lower:
        source = f'''def {func_name}(a: int, b: int) -> int:
            """Return the least common multiple of a and b."""
            if a == 0 or b == 0:
                return 0
            x, y = abs(a), abs(b)
            while y:
                x, y = y, x % y
            return abs(a * b) // x'''

    # Prime checking
    elif "prime" in desc_lower or "primality" in desc_lower:
        source = f'''def {func_name}(n: int) -> bool:
            """Check if n is prime."""
            if n < 2:
                return False
            if n == 2:
                return True
            if n % 2 == 0:
                return False
            for i in range(3, int(n**0.5) + 1, 2):
                if n % i == 0:
                    return False
            return True'''

    # Sorting
    elif "sort" in desc_lower:
        source = f'''def {func_name}(arr: list[int]) -> list[int]:
            """Sort an array using bubble sort."""
            arr = list(arr)
            n = len(arr)
            for i in range(n):
                for j in range(0, n - i - 1):
                    if arr[j] > arr[j + 1]:
                        arr[j], arr[j + 1] = arr[j + 1], arr[j]
            return arr'''

    # Search
    elif "search" in desc_lower or "find" in desc_lower:
        source = f'''def {func_name}(arr: list[int], target: int) -> int:
            """Binary search for target in sorted array. Returns index or -1."""
            left, right = 0, len(arr) - 1
            while left <= right:
                mid = (left + right) // 2
                if arr[mid] == target:
                    return mid
                elif arr[mid] < target:
                    left = mid + 1
                else:
                    right = mid - 1
            return -1'''

    # Sum/average
    elif "sum" in desc_lower or "addition" in desc_lower:
        source = f'''def {func_name}(numbers: list[int]) -> int:
            """Return the sum of a list of numbers."""
            total = 0
            for n in numbers:
                total += n
            return total'''

    elif "average" in desc_lower or "mean" in desc_lower:
        source = f'''def {func_name}(numbers: list[int]) -> float:
            """Return the average of a list of numbers."""
            if not numbers:
                return 0.0
            total = 0
            for n in numbers:
                total += n
            return total / len(numbers)'''

    # Reverse
    elif "reverse" in desc_lower:
        source = f'''def {func_name}(text: str) -> str:
            """Return the reversed string."""
            return text[::-1]'''

    # Palindrome
    elif "palindrome" in desc_lower:
        source = f'''def {func_name}(text: str) -> bool:
            """Check if text is a palindrome."""
            text = text.lower().replace(" ", "")
            return text == text[::-1]'''

    # Default: simple placeholder
    else:
        source = f'''def {func_name}():
            """Generated function for: {description[:50]}"""
            pass'''

    # Build result
    result = {
        "valid": True,
        "source": source,
        "function_name": func_name,
        "difficulty": difficulty,
        "description": description,
    }

    # Add test cases if provided
    if test_cases:
        result["test_cases"] = test_cases

    return result


def _extract_function_name(description: str) -> str:
    """Extract a function name from description or generate one."""
    # Try to find a named function in the description
    patterns = [
        r"def\s+([a-z_]+)",
        r"named\s+([a-z_]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, description)
        if m:
            return m.group(1)

    # Generate from keywords
    keywords = {
        "fibonacci": "fibonacci",
        "factorial": "factorial",
        "gcd": "gcd",
        "lcm": "lcm",
        "prime": "is_prime",
        "sort": "sort_array",
        "search": "binary_search",
        "sum": "sum_numbers",
        "average": "calculate_average",
        "reverse": "reverse_string",
        "palindrome": "is_palindrome",
    }

    for keyword, name in keywords.items():
        if keyword in description:
            return name

    return "solution"


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
