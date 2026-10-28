"""Team Coding Workflow — Junior / Mid / Senior pipeline.

Three-tier developer roles, each with its own coding baseline strategy:

  JUNIOR   → "get it working" first draft, naive but functional
  MID      → "make it right" refactor, add error handling, coverage
  SENIOR   → "make it robust" optimization, deep review, security

After each role's turn the pipeline runs a VALIDATOR gate (pytest + compile).
The NEXT agent reads the PREVIOUS agent's output and builds on it intelligently
(intelligent reprise) rather than starting from scratch.

Architecture:
  PHASE 0  ARCHITECT   (Senior-level planning, produces spec)
  PHASE 1  JUNIOR      (baseline implementation)
             └─ VALIDATOR gate 1
  PHASE 2  MID         (refinement + error handling)
             └─ VALIDATOR gate 2
  PHASE 3  SENIOR      (optimization + deep review)
             └─ VALIDATOR gate 3
  PHASE 4  FINAL       (deterministic oracle validation)

Each role's system prompt encodes its philosophy so the LLM behaves like a
real team member at that seniority level.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CodeLab.TeamWorkflow")

# ── Role system prompts ────────────────────────────────────────────────────

ROLE_PROMPTS: Dict[str, str] = {
    "ARCHITECT": (
        "You are the ARCHITECT — a senior engineer who designs before coding.\n"
        "Given a user prompt, produce a CONCISE architecture spec:\n"
        "  1. Module structure (files to create)\n"
        "  2. Public API / function signatures\n"
        "  3. Data flow between modules\n"
        "  4. Test strategy (what to test, how)\n"
        "  5. Key design decisions and trade-offs\n"
        "Return structured text with sections: MODULES:, SIGNATURES:, FLOW:, TESTS:, DECISIONS:\n"
        "Do NOT write implementation code. This is a PLAN, not a program."
    ),
    "JUNIOR": (
        "You are a JUNIOR developer — eager, pragmatic, learning by doing.\n"
        "Your job: GET IT WORKING. Write the first complete implementation.\n"
        "Rules:\n"
        "  - Follow the architecture spec provided\n"
        "  - Prefer simple, readable code over clever tricks\n"
        "  - Add basic tests that cover the happy path\n"
        "  - It's OK if edge cases aren't perfect — they will be fixed later\n"
        "  - Emit ONE complete Python module between ```python ... ``` markers\n"
        "  - If you're unsure about something, make a reasonable guess and move on\n"
        "Your baseline: working code > perfect code. Ship it."
    ),
    "MID": (
        "You are a MID-LEVEL developer — you make code production-ready.\n"
        "Your job: TAKE THE BASELINE and make it RIGHT.\n"
        "Rules:\n"
        "  - Read the previous implementation carefully before changing anything\n"
        "  - Add proper error handling (try/except, validation, meaningful messages)\n"
        "  - Improve test coverage — target edge cases the junior missed\n"
        "  - Refactor for clarity: rename variables, extract helpers, remove duplication\n"
        "  - Ensure type hints where they add value\n"
        "  - Emit the COMPLETE refined module between ```python ... ``` markers\n"
        "Your baseline: robust code > clever code. Ship it right."
    ),
    "SENIOR": (
        "You are a SENIOR developer — you make code ship-worthy.\n"
        "Your job: TAKE THE REFINED CODE and make it ROBUST.\n"
        "Rules:\n"
        "  - Read the mid-level implementation carefully\n"
        "  - Performance: identify bottlenecks, suggest or apply optimizations\n"
        "  - Security: check for injection, unsafe patterns, data leakage\n"
        "  - Architecture: verify the design holds under stress\n"
        "  - Code review: name quality, documentation gaps, maintainability\n"
        "  - Emit the COMPLETE optimized module between ```python ... ``` markers\n"
        "  - Follow with a REVIEW section: what changed and why\n"
        "Your baseline: production-grade code. Ship it strong."
    ),
}

# ── Turn reprise templates ─────────────────────────────────────────────────

def _junior_task(prompt: str, language: str, architect_spec: str) -> str:
    """Build the task for the junior developer turn."""
    return (
        f"Language: {language}\n"
        f"User prompt:\n{prompt}\n\n"
        f"ARCHITECT SPEC:\n{architect_spec}\n\n"
        "Implement the module following this spec. Get it working. "
        "Emit ONE complete Python file between ```python ... ``` markers."
    )


def _mid_task(source: str, test_output: str, language: str) -> str:
    """Build the task for the mid-level developer turn (intelligent reprise)."""
    return (
        f"Language: {language}\n"
        f"Previous implementation (junior baseline):\n"
        f"```python\n{source}\n```\n"
        f"Test output:\n{test_output}\n\n"
        "Read this code carefully. Refactor for clarity, add error handling, "
        "improve tests. Emit the COMPLETE refined module between ```python ... ``` markers."
    )


def _senior_task(source: str, test_output: str, language: str) -> str:
    """Build the task for the senior developer turn (intelligent reprise)."""
    return (
        f"Language: {language}\n"
        f"Refined implementation (mid-level):\n"
        f"```python\n{source}\n```\n"
        f"Test output:\n{test_output}\n\n"
        "Read this code carefully. Optimize for performance, check security, "
        "review architecture. Emit the COMPLETE optimized module between ```python ... ``` markers, "
        "followed by a REVIEW section explaining your changes."
    )


# ── Validator gate ─────────────────────────────────────────────────────────

@dataclass
class ValidatorResult:
    """Result of a validator gate."""
    passed: bool
    compile_ok: bool
    pytest_passed: int
    pytest_failed: int
    pytest_total: int
    output: str = ""
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "compile_ok": self.compile_ok,
            "pytest_passed": self.pytest_passed,
            "pytest_failed": self.pytest_failed,
            "pytest_total": self.pytest_total,
            "output": self.output[-2000:],
            "errors": self.errors,
        }


def run_validator(workspace: Path, source_file: str, test_file: Optional[str] = None) -> ValidatorResult:
    """Run deterministic validation on the current workspace state.

    Checks:
      1. Every .py file compiles (SyntaxError check)
      2. pytest runs and passes (if test file present)
      3. Structural: at least one function/class/import in source
    """
    import subprocess
    import sys
    import ast
    import re

    errors: List[str] = []

    # ── Compile check ───────────────────────────────────────────────────
    compile_ok = True
    py_files = list(workspace.glob("*.py"))
    if not py_files:
        return ValidatorResult(passed=False, compile_ok=False, pytest_passed=0,
                               pytest_failed=0, pytest_total=0,
                               output="No Python files found.", errors=["no_python_files"])

    for py_file in py_files:
        if py_file.name.startswith("test_"):
            continue
        try:
            src = py_file.read_text(encoding="utf-8")
            compile(src, str(py_file), "exec")
        except SyntaxError as e:
            compile_ok = False
            errors.append(f"SyntaxError in {py_file.name}: {e}")

    if not compile_ok:
        return ValidatorResult(passed=False, compile_ok=False, pytest_passed=0,
                               pytest_failed=0, pytest_total=0,
                               output="Compilation failed.", errors=errors)

    # ── Substantive code check ──────────────────────────────────────────
    substantive = False
    for py_file in py_files:
        if py_file.name.startswith("test_"):
            continue
        src = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                               ast.Import, ast.ImportFrom)) for n in tree.body):
            substantive = True
            break
    if not substantive:
        return ValidatorResult(passed=False, compile_ok=True, pytest_passed=0,
                               pytest_failed=0, pytest_total=0,
                               output="No substantive code found (literal-only output?).",
                               errors=["phantom_output"])

    # ── Pytest ──────────────────────────────────────────────────────────
    cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"]
    if test_file:
        test_path = workspace / test_file
        if test_path.exists():
            cmd.append(str(test_path))
    else:
        # Run all tests in workspace
        pass

    try:
        proc = subprocess.run(cmd, cwd=str(workspace), capture_output=True,
                              text=True, timeout=120)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        passed_count = 0
        failed = 0
        m = re.search(r"(\d+) passed", out)
        if m:
            passed_count = int(m.group(1))
        m = re.search(r"(\d+) failed", out)
        if m:
            failed = int(m.group(1))
        total = passed_count + failed
        return ValidatorResult(
            passed=proc.returncode == 0 and passed_count > 0,
            compile_ok=True,
            pytest_passed=passed_count,
            pytest_failed=failed,
            pytest_total=total,
            output=out[-2000:],
        )
    except subprocess.TimeoutExpired:
        return ValidatorResult(passed=False, compile_ok=True, pytest_passed=0,
                               pytest_failed=0, pytest_total=0,
                               output="pytest timed out.", errors=["timeout"])
    except Exception as e:
        return ValidatorResult(passed=False, compile_ok=True, pytest_passed=0,
                               pytest_failed=0, pytest_total=0,
                               output=f"pytest error: {e}", errors=[str(e)])


# ── Team pipeline orchestrator ─────────────────────────────────────────────

@dataclass
class TeamTurn:
    """Result of one team member's turn."""
    role: str
    phase: int
    response: str
    validator: Optional[ValidatorResult] = None
    timestamp: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "phase": self.phase,
            "response_length": len(self.response),
            "validator": self.validator.to_dict() if self.validator else None,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }


class TeamPipeline:
    """Orchestrates the 3-tier team coding workflow.

    Each phase can run standalone (for experimentation) or as part of the full pipeline.
    The pipeline state is serializable for RAW persistence.
    """

    def __init__(self, workspace: Path, language: str = "python",
                 max_iterations_per_phase: int = 2):
        self.workspace = workspace
        self.language = language
        self.max_iterations = max_iterations_per_phase
        self.turns: List[TeamTurn] = []
        self.architect_spec: str = ""
        self._trace_index: int = 0

    def run_full(self, prompt: str, llm_client=None,
                 role_prompts: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run the complete 4-phase team pipeline.

        Returns a structured result with all turns, validator outcomes, and final status.
        """
        results = {
            "prompt": prompt,
            "language": self.language,
            "phases": [],
            "final_status": "unknown",
            "turns": [],
        }

        # PHASE 0: ARCHITECT
        architect_result = self._run_architect(prompt, llm_client, role_prompts)
        if architect_result["ok"]:
            self.architect_spec = architect_result["response"]
            results["phases"].append({"phase": 0, "role": "ARCHITECT", "status": "done"})
        else:
            results["phases"].append({"phase": 0, "role": "ARCHITECT", "status": "failed",
                                       "error": architect_result.get("error")})
            return self._finalize(results, "architect_failed")

        # PHASE 1: JUNIOR
        junior_result = self._run_junior(prompt, self.architect_spec, llm_client, role_prompts)
        if not junior_result["ok"]:
            results["phases"].append({"phase": 1, "role": "JUNIOR", "status": "failed"})
            return self._finalize(results, "junior_failed")

        # VALIDATOR GATE 1
        v1 = self._run_validator_gate(1)
        junior_result["validator"] = v1
        self.turns.append(TeamTurn(role="JUNIOR", phase=1, response=junior_result["response"],
                                   validator=v1))
        results["phases"].append({"phase": 1, "role": "JUNIOR", "status": "done",
                                   "validator": v1.to_dict()})

        if not v1.passed:
            # Try one repair iteration
            junior_result = self._run_junior(prompt, self.architect_spec, llm_client,
                                              role_prompts, retry=True)
            v1 = self._run_validator_gate(1)
            self.turns[-1].validator = v1
            results["phases"][-1]["validator"] = v1.to_dict()

        if not v1.passed:
            return self._finalize(results, "junior_validator_failed")

        # PHASE 2: MID
        mid_result = self._run_mid(self._get_latest_source(), v1.output, llm_client, role_prompts)
        if not mid_result["ok"]:
            results["phases"].append({"phase": 2, "role": "MID", "status": "failed"})
            return self._finalize(results, "mid_failed")

        # VALIDATOR GATE 2
        v2 = self._run_validator_gate(2)
        mid_result["validator"] = v2
        self.turns.append(TeamTurn(role="MID", phase=2, response=mid_result["response"],
                                   validator=v2))
        results["phases"].append({"phase": 2, "role": "MID", "status": "done",
                                   "validator": v2.to_dict()})

        if not v2.passed:
            mid_result = self._run_mid(self._get_latest_source(), v2.output, llm_client, role_prompts)
            v2 = self._run_validator_gate(2)
            self.turns[-1].validator = v2
            results["phases"][-1]["validator"] = v2.to_dict()

        if not v2.passed:
            return self._finalize(results, "mid_validator_failed")

        # PHASE 3: SENIOR
        senior_result = self._run_senior(self._get_latest_source(), v2.output, llm_client, role_prompts)
        if not senior_result["ok"]:
            results["phases"].append({"phase": 3, "role": "SENIOR", "status": "failed"})
            return self._finalize(results, "senior_failed")

        # VALIDATOR GATE 3
        v3 = self._run_validator_gate(3)
        senior_result["validator"] = v3
        self.turns.append(TeamTurn(role="SENIOR", phase=3, response=senior_result["response"],
                                   validator=v3))
        results["phases"].append({"phase": 3, "role": "SENIOR", "status": "done",
                                   "validator": v3.to_dict()})

        # PHASE 4: FINAL DETERMINISTIC VALIDATION
        final_v = self._run_final_validation()
        results["phases"].append({"phase": 4, "role": "VALIDATOR", "status": "done",
                                   "validator": final_v.to_dict()})

        if final_v.passed:
            return self._finalize(results, "passed")
        else:
            return self._finalize(results, "final_validation_failed")

    def _run_architect(self, prompt: str, llm_client=None,
                       role_prompts: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run the ARCHITECT phase."""
        system = (role_prompts.get("ARCHITECT", ROLE_PROMPTS["ARCHITECT"])
                  if role_prompts else ROLE_PROMPTS["ARCHITECT"])
        task = f"Language: {self.language}\nUser prompt:\n{prompt}\n\nProduce an architecture spec."
        return self._call_llm(system, task, max_tokens=1600)

    def _run_junior(self, prompt: str, spec: str, llm_client=None,
                    role_prompts: Optional[Dict[str, str]] = None, retry: bool = False) -> Dict[str, Any]:
        """Run the JUNIOR phase."""
        system = (role_prompts.get("JUNIOR", ROLE_PROMPTS["JUNIOR"])
                  if role_prompts else ROLE_PROMPTS["JUNIOR"])
        task = _junior_task(prompt, self.language, spec)
        return self._call_llm(system, task, max_tokens=8000)

    def _run_mid(self, source: str, test_output: str, llm_client=None,
                 role_prompts: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run the MID phase (intelligent reprise)."""
        system = (role_prompts.get("MID", ROLE_PROMPTS["MID"])
                  if role_prompts else ROLE_PROMPTS["MID"])
        task = _mid_task(source, test_output, self.language)
        return self._call_llm(system, task, max_tokens=8000)

    def _run_senior(self, source: str, test_output: str, llm_client=None,
                    role_prompts: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run the SENIOR phase (intelligent reprise)."""
        system = (role_prompts.get("SENIOR", ROLE_PROMPTS["SENIOR"])
                  if role_prompts else ROLE_PROMPTS["SENIOR"])
        task = _senior_task(source, test_output, self.language)
        return self._call_llm(system, task, max_tokens=8000)

    def _call_llm(self, system: str, task: str, max_tokens: int = 1200,
                  temperature: float = 0.4,
                  llm_client: Any = None) -> Dict[str, Any]:
        """Call the LLM client if available, otherwise return degenerate result."""
        t0 = time.time()
        if llm_client is None:
            # Deterministic fallback — return empty (caller handles)
            return {"ok": False, "response": "", "error": "no_llm_client",
                    "duration": time.time() - t0}

        try:
            from philosophical_council.llm.client import LLMClient
            if not hasattr(llm_client, 'chat'):
                return {"ok": False, "response": "", "error": "invalid_client",
                        "duration": time.time() - t0}
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": task},
            ]
            text, finish = llm_client.chat(messages, temperature=temperature,
                                            max_tokens=max_tokens)
            duration = time.time() - t0
            if not text or not text.strip():
                return {"ok": False, "response": "", "error": "empty_response",
                        "duration": duration}
            return {"ok": True, "response": text.strip(), "finish": finish,
                    "duration": round(duration, 2)}
        except Exception as e:
            return {"ok": False, "response": "", "error": str(e),
                    "duration": time.time() - t0}

    def _run_validator_gate(self, phase: int) -> ValidatorResult:
        """Run the validator for the current workspace state."""
        source_files = [f for f in self.workspace.glob("*.py") if not f.name.startswith("test_")]
        test_files = list(self.workspace.glob("test_*.py"))
        source_file = str(source_files[0].name) if source_files else ""
        test_file = str(test_files[0].name) if test_files else None
        return run_validator(self.workspace, source_file, test_file)

    def _get_latest_source(self) -> str:
        """Get the current source file content for intelligent reprise."""
        source_files = [f for f in self.workspace.glob("*.py") if not f.name.startswith("test_")]
        if source_files:
            try:
                return source_files[0].read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    def _run_final_validation(self) -> ValidatorResult:
        """Run the final deterministic validation."""
        return self._run_validator_gate(4)

    def _finalize(self, results: Dict[str, Any], status: str) -> Dict[str, Any]:
        """Finalize the pipeline result."""
        results["final_status"] = status
        results["turns"] = [t.to_dict() for t in self.turns]
        return results

    def get_turn_summary(self) -> str:
        """Human-readable summary of all team turns."""
        lines = ["=== Team Coding Workflow Summary ===", ""]
        for turn in self.turns:
            v = turn.validator
            status = "✓ PASS" if (v and v.passed) else ("✗ FAIL" if v else "no validator")
            lines.append(f"Phase {turn.phase} — {turn.role}: {status}")
            if v:
                lines.append(f"  Tests: {v.pytest_passed}/{v.pytest_total} passed")
        return "\n".join(lines)
