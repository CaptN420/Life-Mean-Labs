"""Integrity: canonical single-class consolidation (§5, §6, §19.7-8).

Proves ValidationResult and FailureRecord each have ONE canonical dataclass
across all import paths — not two parallel implementations that can drift.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _syspath():
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    yield


def test_validationresult_one_canonical_class():
    # The engine (oracle) and runner must share the SAME class.
    from experiments.validation.schemas import ValidationResult as Canonical
    from experiments.runner import ValidationResult as RunnerVR
    assert RunnerVR is Canonical
    # The canonical schema carries the extended field set.
    fields = {f.name for f in Canonical.__dataclass_fields__.values()}
    assert {"valid", "score", "method", "evidence", "error", "steps"} <= fields


def test_failurerecord_one_canonical_class_with_validation_method():
    from experiments.failure_bank.schemas import FailureRecord as Canonical
    from experiments.validation.schemas import FailureRecord as ValidationVR
    assert ValidationVR is Canonical
    # validation_method was merged into the canonical schema.
    fields = {f.name for f in Canonical.__dataclass_fields__.values()}
    assert "validation_method" in fields
    # Round-trip preserves it.
    rec = Canonical(task_id="t", experiment_id="e", run_id="r",
                    failed_answer=None, ground_truth=None,
                    validation_method="hybrid")
    back = Canonical.from_dict(rec.to_dict())
    assert back.validation_method == "hybrid"


def _pyproject_text():
    return (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")


def test_packaging_guards_keep_generated_runtimes_out_of_wheel():
    """Wheel-integrity guards (§1/§19.20): the build config must keep generated
    Code Lab runtimes (.pyc, workspaces) out of the wheel while shipping the
    scientific resources. Proven at build time (uv build + clean external venv)
    and guarded here against regression."""
    txt = _pyproject_text()
    # Generated runtime discovery is excluded from packages.find AND data.
    assert "code_lab_runs*" in txt and "code_lab.runs" in txt
    # include-package-data must be counterbalanced by the data exclusion.
    assert "[tool.setuptools.exclude-package-data]" in txt
    # The scientific runtime resources required by §1 are declared.
    assert '"experiments.ui" = ["dashboard.html"]' in txt
    assert '"library.personas.data" = ["*.txt"]' in txt
    assert "role_templates*" in txt  # §1: role_templates must ship
    # MANIFEST.in adds a durable build-time guard.
    manifest = (Path(__file__).resolve().parent.parent / "MANIFEST.in")
    assert manifest.exists()
    assert "code_lab/runs" in manifest.read_text(encoding="utf-8")
