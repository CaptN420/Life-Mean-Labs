"""Compare V1 — deterministic comparison of historical experiment runs.

A top-level research instrument (design doc M1 / §26). Consumes RAW JSONL
evidence from ``data/raw_debates/<experiment_id>.jsonl`` and extracts, per run:

- immutable condition (config snapshot)
- success/pass metrics
- domain / difficulty breakdown
- tools + workers actually used
- failure-reason counts

then pairwise:

- classifies comparability (HIGHLY_CONTROLLED / PARTIALLY_CONTROLLED /
  EXPLORATORY / NOT_DIRECTLY_COMPARABLE)
- separates OBSERVATION / HYPOTHESIS / REPAIR_CANDIDATE
- detects repeated failure patterns

All analysis is **deterministic** — no LLM is required. Findings are labelled
so the engine never claims causality from an uncontrolled comparison. Compare
never reads history immutability: it only reads RAW, it never rewrites it.

    from compare import CompareEngine
    report = CompareEngine().compare("exp_a", "exp_b")
"""

from compare.comparability import compare_pair
from compare.loader import (
    CompareLoadError,
    load_experiment,
    load_experiments,
    list_available_experiments,
)
from compare.models import (
    COMPARABILITY_LEVELS,
    FINDING_KINDS,
    ComparisonOutcome,
    ComparabilityKind,
    FailurePattern,
    Finding,
    FindingKind,
    PairOutcome,
    RunMetrics,
    TaskRecord,
)
from compare.analyzer import CompareEngine, build_report
from compare.index import build_index, default_index_path, load_index, write_index
from compare.subjects import (
    DEFAULT_SUBJECTS_DIR,
    SubjectTree,
    SubjectTreeError,
    default_subjects_dir,
)

__all__ = [
    "COMPARABILITY_LEVELS", "FINDING_KINDS",
    "ComparabilityKind", "ComparisonOutcome",
    "compare_pair",
    "CompareLoadError", "load_experiment",
    "load_experiments", "list_available_experiments",
    "FailurePattern", "Finding", "FindingKind", "PairOutcome",
    "RunMetrics", "TaskRecord",
    "CompareEngine", "build_report",
    "build_index", "default_index_path", "load_index", "write_index",
    "DEFAULT_SUBJECTS_DIR", "SubjectTree", "SubjectTreeError",
    "default_subjects_dir",
]