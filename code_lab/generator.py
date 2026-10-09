"""Deterministic Python code generation (V1).

Milestone-focused: emits real, importable source + pytest test files for
well-defined templates. This is the "Developer" role output, generated
deterministically so the result is fully reproducible (rule 12).

Detection is a lightweight heuristic on the prompt. When no template matches,
a generic function scaffold is emitted and flagged as "generic" so the
pipeline never pretends it produced a verified implementation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


class CodeGenError(Exception):
    """Raised when code generation fails."""


def _slugify(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower())
    name = re.sub(r"^_+|_+$", "", name)
    return name or "module"


def detect_plan(prompt: str) -> Tuple[str, Dict[str, Any]]:
    """Detect a template plan from the prompt.

    Returns (plan_id, params). Unknown prompts fall back to 'generic'.
    """
    p = prompt.lower()
    if "fibonacci" in p:
        return "fibonacci", {}
    if "factorial" in p:
        return "factorial", {}
    if "is_prime" in p or "prime" in p:
        return "is_prime", {}
    if "palindrome" in p:
        return "palindrome", {}
    if "reverse" in p and "string" in p:
        return "reverse_string", {}
    return "generic", {}


PLANS = {
    "fibonacci": ("fibonacci.py", "test_fibonacci.py"),
    "factorial": ("factorial.py", "test_factorial.py"),
    "is_prime": ("is_prime.py", "test_is_prime.py"),
    "palindrome": ("palindrome.py", "test_palindrome.py"),
    "reverse_string": ("reverse_string.py", "test_reverse_string.py"),
    "generic": ("main.py", "test_main.py"),
}

_SOURCE = {
    "fibonacci": '''"""Fibonacci sequence (deterministic, V1)."""


def fibonacci(n: int) -> list:
    """Return the first n Fibonacci numbers (fibonacci(0) == [], fibonacci(1) == [0])."""
    if n is None or n < 0:
        raise ValueError("n must be a non-negative integer")
    if n == 0:
        return []
    if n == 1:
        return [0]
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq
''',
    "factorial": '''"""Factorial (deterministic, V1)."""


def factorial(n: int) -> int:
    """Return n! for a non-negative integer n."""
    if n is None or n < 0:
        raise ValueError("n must be a non-negative integer")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
''',
    "is_prime": '''"""Primality test (deterministic, V1)."""


def is_prime(n: int) -> bool:
    """Return True if n is a prime number, False otherwise."""
    if n is None:
        raise TypeError("n must be an integer")
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True
''',
    "palindrome": '''"""Palindrome check (deterministic, V1)."""


def is_palindrome(s: str) -> bool:
    """Return True if s reads the same forward and backward."""
    if s is None:
        raise TypeError("s must be a string")
    cleaned = "".join(ch for ch in str(s).lower() if ch.isalnum())
    return cleaned == cleaned[::-1]
''',
    "reverse_string": '''"""Reverse a string (deterministic, V1)."""


def reverse_string(s: str) -> str:
    """Return the reversal of string s."""
    if s is None:
        raise TypeError("s must be a string")
    return s[::-1]
''',
    "generic": '''"""Generic module scaffold (V1)."""


def run():
    """Entry point placeholder. Replace with the requested implementation."""
    return "TODO: not implemented"


if __name__ == "__main__":
    print(run())
''',
}

_TESTS = {
    "fibonacci": '''from fibonacci import fibonacci


def test_fibonacci_zero():
    assert fibonacci(0) == []


def test_fibonacci_one():
    assert fibonacci(1) == [0]


def test_fibonacci_first_ten():
    assert fibonacci(10) == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]


def test_fibonacci_strict_increasing_after_two():
    seq = fibonacci(20)
    assert all(seq[i] < seq[i + 1] for i in range(2, len(seq) - 1))


def test_fibonacci_negative_raises():
    import pytest
    with pytest.raises(ValueError):
        fibonacci(-1)
''',
    "factorial": '''from factorial import factorial


def test_factorial_zero():
    assert factorial(0) == 1


def test_factorial_one():
    assert factorial(1) == 1


def test_factorial_five():
    assert factorial(5) == 120


def test_factorial_ten():
    assert factorial(10) == 3628800


def test_factorial_negative_raises():
    import pytest
    with pytest.raises(ValueError):
        factorial(-3)
''',
    "is_prime": '''from is_prime import is_prime


def test_not_prime_small():
    assert not is_prime(0)
    assert not is_prime(1)


def test_prime_two_three():
    assert is_prime(2)
    assert is_prime(3)


def test_prime_seventeen():
    assert is_prime(17)


def test_not_prime_composite():
    assert not is_prime(15)
    assert not is_prime(100)


def test_none_raises():
    import pytest
    with pytest.raises(TypeError):
        is_prime(None)
''',
    "palindrome": '''from palindrome import is_palindrome


def test_empty():
    assert is_palindrome("")


def test_simple_madam():
    assert is_palindrome("madam")


def test_phrase_mixed_case():
    assert is_palindrome("A man a plan a canal Panama")


def test_not_palindrome():
    assert not is_palindrome("hello")


def test_none_raises():
    import pytest
    with pytest.raises(TypeError):
        is_palindrome(None)
''',
    "reverse_string": '''from reverse_string import reverse_string


def test_reverse_hello():
    assert reverse_string("hello") == "olleh"


def test_reverse_empty():
    assert reverse_string("") == ""


def test_reverse_single():
    assert reverse_string("a") == "a"


def test_reverse_none_raises():
    import pytest
    with pytest.raises(TypeError):
        reverse_string(None)
''',
    # Free-form ("generic") tasks get NO deterministic oracle: the run()->str
        # test was an invented contract that rejects valid arbitrary projects
        # (Tetris, GUI, libraries). Structural validation is performed instead.
        "generic": "",
}


def generate(plan_id: str) -> Tuple[str, str]:
    """Return (source_code, test_code) for the given plan id."""
    if plan_id not in PLANS:
        raise CodeGenError(f"Unknown plan: {plan_id}")
    return _SOURCE[plan_id], _TESTS[plan_id]


def generate_files(prompt: str, seed: int = 42) -> Dict[str, Any]:
    """Generate the source + test filenames and contents for a prompt.

    Deterministic in `seed` (seed is recorded but V1 templates are fixed).
    """
    plan_id, params = detect_plan(prompt)
    src_name, test_name = PLANS[plan_id]
    source, tests = generate(plan_id)
    return {
        "plan_id": plan_id,
        "source_filename": src_name,
        "test_filename": test_name,
        "source": source,
        "tests": tests,
        "deterministic": True,
    }