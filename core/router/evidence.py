"""Evidence Validation Layer for Adaptive Router v1.1.

Provides structured validation with evidence tracking,
distinguishing between verified, partial, unverified, and invalid results.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("core.router.evidence")


# ── Enums ────────────────────────────────────────────────────────────────────

class EvidenceStatus(str, Enum):
    """Validation status with evidence."""
    VERIFIED = "VERIFIED"          # Confirmed by applicable verification criteria
    PARTIAL = "PARTIAL"            # Partial verification or insufficient coverage
    UNVERIFIED = "UNVERIFIED"      # No independent conclusive verification
    INVALID = "INVALID"            # Contradictory or incorrect result


class EvidenceType(str, Enum):
    """Types of evidence that can be collected."""
    TYPE_CHECK = "TYPE_CHECK"
    CONSTRAINT_CHECK = "CONSTRAINT_CHECK"
    INVARIANT_CHECK = "INVARIANT_CHECK"
    CROSS_REFERENCE = "CROSS_REFERENCE"
    BENCHMARK = "BENCHMARK"
    SANITY_CHECK = "SANITY_CHECK"


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    """Single piece of evidence for a validation."""
    type: EvidenceType
    description: str
    passed: bool
    details: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "description": self.description,
            "passed": self.passed,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class ValidationResult:
    """Complete validation result with evidence trail."""
    task_id: str
    tool_name: str
    status: EvidenceStatus
    engine_used: str
    evidence: List[EvidenceItem] = field(default_factory=list)
    execution_ms: float = 0.0
    tokens_used: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def is_verified(self) -> bool:
        return self.status == EvidenceStatus.VERIFIED

    @property
    def evidence_summary(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "engine_used": self.engine_used,
            "evidence_count": len(self.evidence),
            "passed_count": sum(1 for e in self.evidence if e.passed),
            "failed_count": sum(1 for e in self.evidence if not e.passed),
            "execution_ms": self.execution_ms,
            "tokens_used": self.tokens_used,
            "errors": self.errors,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.evidence_summary,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ── Evidence Collector ───────────────────────────────────────────────────────

class EvidenceCollector:
    """Collects and manages evidence for validation."""

    def __init__(self, task_id: str, tool_name: str):
        self.task_id = task_id
        self.tool_name = tool_name
        self._evidence: List[EvidenceItem] = []
        self._errors: List[str] = []
        self._start_time: float = time.time()

    def add_evidence(self, evidence_type: EvidenceType, description: str, passed: bool, details: Optional[Dict[str, Any]] = None) -> None:
        """Add a piece of evidence."""
        self._evidence.append(EvidenceItem(
            type=evidence_type,
            description=description,
            passed=passed,
            details=details,
        ))

    def add_error(self, error: str) -> None:
        """Record an error."""
        self._errors.append(error)

    def get_result(self, status: EvidenceStatus, engine_used: str, execution_ms: float = 0.0, tokens_used: int = 0) -> ValidationResult:
        """Get the final validation result."""
        return ValidationResult(
            task_id=self.task_id,
            tool_name=self.tool_name,
            status=status,
            engine_used=engine_used,
            evidence=self._evidence,
            execution_ms=execution_ms,
            tokens_used=tokens_used,
            errors=self._errors,
        )


# ── Validator ────────────────────────────────────────────────────────────────

class EvidenceValidator:
    """Validates results with evidence collection."""

    def __init__(self):
        self._validators: Dict[str, List[Tuple[str, Any]]] = {}  # tool_pattern -> [(name, validator_fn)]

    def register(self, tool_pattern: str, validator_fn, description: str = "") -> None:
        """Register a validator for a tool pattern."""
        if tool_pattern not in self._validators:
            self._validators[tool_pattern] = []
        self._validators[tool_pattern].append((description or tool_pattern, validator_fn))

    def validate(
        self,
        collector: EvidenceCollector,
        tool_name: str,
        result: Any,
        expected_type: Optional[type] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> EvidenceStatus:
        """Validate a result and collect evidence."""
        all_passed = True

        # Type check
        if expected_type is not None:
            type_ok = isinstance(result, expected_type)
            collector.add_evidence(
                EvidenceType.TYPE_CHECK,
                f"Result is {expected_type.__name__}",
                type_ok,
                {"actual_type": type(result).__name__},
            )
            if not type_ok:
                all_passed = False

        # Constraint checks
        if constraints and isinstance(result, dict):
            for constraint_name, check_fn in constraints.items():
                try:
                    passed = check_fn(result)
                    collector.add_evidence(
                        EvidenceType.CONSTRAINT_CHECK,
                        f"Constraint {constraint_name}",
                        passed,
                    )
                    if not passed:
                        all_passed = False
                except Exception as exc:
                    collector.add_error(f"Constraint check failed: {exc}")
                    all_passed = False

        # Default validation for primitives
        if isinstance(result, (int, float, str, bool)):
            collector.add_evidence(
                EvidenceType.SANITY_CHECK,
                "Primitive result",
                True,
            )
        elif isinstance(result, dict) and "result" in result:
            collector.add_evidence(
                EvidenceType.SANITY_CHECK,
                "Dict with 'result' key",
                True,
            )
        elif result is None:
            collector.add_evidence(
                EvidenceType.SANITY_CHECK,
                "None result",
                False,
            )
            all_passed = False

        # Tool-specific validators
        for pattern, validators in self._validators.items():
            if pattern in tool_name:
                for desc, validator_fn in validators:
                    try:
                        passed = validator_fn(result)
                        collector.add_evidence(
                            EvidenceType.CROSS_REFERENCE,
                            desc,
                            passed,
                        )
                        if not passed:
                            all_passed = False
                    except Exception as exc:
                        collector.add_error(f"Validator error: {exc}")
                        all_passed = False

        # Determine final status
        if all_passed and len(self._evidence) > 0:
            return EvidenceStatus.VERIFIED
        elif any(e.passed for e in collector._evidence):
            return EvidenceStatus.PARTIAL
        elif len(collector._errors) > 0:
            return EvidenceStatus.INVALID
        else:
            return EvidenceStatus.UNVERIFIED

    @property
    def _evidence(self) -> List[EvidenceItem]:
        # Helper to access evidence from collector
        return []


# ── Benchmark Engine ─────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """Result of a benchmark execution."""
    task_id: str
    strategy: str
    latency_ms: float
    cpu_time_ms: float
    peak_memory_mb: Optional[float]
    tokens: Optional[int]
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "strategy": self.strategy,
            "latency_ms": self.latency_ms,
            "cpu_time_ms": self.cpu_time_ms,
            "peak_memory_mb": self.peak_memory_mb,
            "tokens": self.tokens,
            "success": self.success,
            "error": self.error,
        }


class BenchmarkEngine:
    """Lightweight benchmarking infrastructure."""

    def __init__(self):
        self._results: Dict[str, List[BenchmarkResult]] = {}

    def run_benchmark(
        self,
        task_id: str,
        strategy: str,
        executor,
        *args,
        **kwargs,
    ) -> BenchmarkResult:
        """Run a single benchmark execution."""
        import time
        import sys

        start = time.perf_counter()
        success = True
        error = None
        tokens = None

        try:
            result = executor(*args, **kwargs)
            if result is None:
                success = False
                error = "Executor returned None"
        except Exception as exc:
            success = False
            error = str(exc)

        elapsed = (time.perf_counter() - start) * 1000

        # Estimate CPU time (approximation on Windows)
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            cpu_time = usage.ru_utime * 1000 + usage.ru_stime * 1000
        except ImportError:
            cpu_time = elapsed  # Fallback on Windows

        # Estimate peak memory (approximation)
        try:
            import resource
            peak_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB to MB
        except ImportError:
            peak_mem = None

        benchmark_result = BenchmarkResult(
            task_id=task_id,
            strategy=strategy,
            latency_ms=elapsed,
            cpu_time_ms=cpu_time,
            peak_memory_mb=peak_mem,
            tokens=tokens,
            success=success,
            error=error,
        )

        if task_id not in self._results:
            self._results[task_id] = []
        self._results[task_id].append(benchmark_result)

        return benchmark_result

    def get_comparison(self, task_id: str) -> Dict[str, Any]:
        """Get comparison of all strategies for a task."""
        if task_id not in self._results:
            return {"error": "No benchmarks found for task"}

        results = self._results[task_id]
        summary = {}
        for result in results:
            strategy = result.strategy
            if strategy not in summary:
                summary[strategy] = {
                    "attempts": 0,
                    "successes": 0,
                    "total_latency_ms": 0.0,
                    "errors": [],
                }
            summary[strategy]["attempts"] += 1
            if result.success:
                summary[strategy]["successes"] += 1
            summary[strategy]["total_latency_ms"] += result.latency_ms
            if result.error:
                summary[strategy]["errors"].append(result.error)

        # Calculate averages
        for strategy, data in summary.items():
            data["avg_latency_ms"] = data["total_latency_ms"] / data["attempts"] if data["attempts"] > 0 else 0.0
            data["success_rate"] = data["successes"] / data["attempts"] if data["attempts"] > 0 else 0.0
            del data["total_latency_ms"]

        return {
            "task_id": task_id,
            "strategies": summary,
        }

    def clear_results(self) -> int:
        """Clear all benchmark results."""
        count = sum(len(v) for v in self._results.values())
        self._results.clear()
        return count
