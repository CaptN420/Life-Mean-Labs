"""Subject tree (folder architecture) tests.

Covers: auto-created folders on new subject, register/unregister/subject_of,
tree traversal (recursive + non-recursive), path-traversal rejection, and
bootstrap-from-RAW (topic=domain, subfolder=difficulty_range, empty test
artifacts skipped). All tests use a tmp root — never the real data/subjects.
"""

import json

import pytest

from compare.subjects import SubjectTree, SubjectTreeError
from compare.loader import default_raw_dir


def _tree(tmp_path):
    return SubjectTree(root=tmp_path / "subjects")


def _write_raw(tmppath, experiment_id, domain, dr, tasks=2, valid=True):
    p = tmppath / "raw" / f"{experiment_id}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    for i in range(tasks):
        line = {
            "run_id": f"run_{experiment_id}", "task_id": f"t{i}",
            "experiment_id": experiment_id,
            "config": {"domain": domain, "difficulty_range": dr,
                       "num_tasks": tasks, "seed": 1, "deterministic": True},
            "validation_result": {"valid": valid, "score": 1.0,
                                  "method": "deterministic"},
            "metadata": {"domain": domain, "difficulty": 1},
        }
        p.write_text(json.dumps(line) + "\n", encoding="utf-8")
    return tmppath / "raw"


# ── register / folders ─────────────────────────────────────────────────────
def test_register_auto_creates_general_folder(tmp_path):
    t = _tree(tmp_path)
    payload = t.register("exp_a", "math/[1,5]")
    assert payload["topic"] == "math"
    assert payload["subfolder"] == "[1,5]"
    assert (tmp_path / "subjects" / "math" / "[1,5]").is_dir()


def test_new_topic_creates_folder_automatically(tmp_path):
    t = _tree(tmp_path)
    t.register("exp_a", "philosophical")
    assert (tmp_path / "subjects" / "philosophical").is_dir()
    assert t.topics() == ["philosophical"]


def test_register_is_idempotent(tmp_path):
    t = _tree(tmp_path)
    t.register("exp_a", "math/[1,5]")
    t.register("exp_a", "math/[1,5]")
    assert t.experiment_ids("math/[1,5]") == ["exp_a"]


def test_subject_of_and_unregister(tmp_path):
    t = _tree(tmp_path)
    t.register("exp_a", "math/[1,5]")
    assert t.subject_of("exp_a") == "math/[1,5]"
    assert t.unregister("exp_a") is True
    assert t.subject_of("exp_a") is None
    assert t.experiment_ids("math") == []


# ── traversal ──────────────────────────────────────────────────────────────
def test_experiment_ids_recursive_and_exact(tmp_path):
    t = _tree(tmp_path)
    t.register("exp_a", "math/[1,5]")
    t.register("exp_b", "math/[1,3]")
    t.register("exp_c", "chemistry/[1,5]")
    assert t.experiment_ids("math") == ["exp_a", "exp_b"]
    assert t.experiment_ids("math/[1,5]") == ["exp_a"]
    assert t.experiment_ids("math", recursive=False) == []


def test_tree_nested_structure(tmp_path):
    t = _tree(tmp_path)
    t.register("exp_a", "math/[1,5]")
    tree = t.tree()
    assert "math" in tree["subjects"]
    assert "[1,5]" in tree["subjects"]["math"]["subjects"]
    assert tree["subjects"]["math"]["subjects"]["[1,5]"]["experiments"] == ["exp_a"]


# ── security: path traversal ───────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["../evil", "a/../../b", "..", ".", "a\\..\\b",
                                 "math/../x", "a:b", "a*b", "a?b"])
def test_path_traversal_rejected(tmp_path, bad):
    t = _tree(tmp_path)
    with pytest.raises(SubjectTreeError):
        t.register("exp_a", bad)


def test_empty_subject_rejected(tmp_path):
    t = _tree(tmp_path)
    with pytest.raises(SubjectTreeError):
        t.register("exp_a", "   ")


# ── bootstrap from RAW ────────────────────────────────────────────────────
def test_bootstrap_uses_domain_and_difficulty(tmp_path):
    _write_raw(tmp_path, "exp_a", "math", [1, 5])
    _write_raw(tmp_path, "exp_b", "math", [1, 1])
    _write_raw(tmp_path, "exp_c", "chemistry", [1, 5])
    t = _tree(tmp_path)
    summary = t.bootstrap_from_raw(raw_dir=tmp_path / "raw")
    assert summary["registered"]["math/[1,5]"] == 1
    assert summary["registered"]["math/[1,1]"] == 1
    assert summary["registered"]["chemistry/[1,5]"] == 1
    assert summary["skipped_no_evidence"] == 0
    assert t.experiment_ids("math") == ["exp_a", "exp_b"]


def test_bootstrap_skips_empty_no_verdict_artifacts(tmp_path):
    # A real run with verdicts.
    _write_raw(tmp_path, "exp_a", "math", [1, 5], tasks=2, valid=True)
    # An empty artifact: a file with a line but no validation verdict.
    rawdir = tmp_path / "raw"
    p = rawdir / "test_artifact.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"run_id": "r", "task_id": "t",
                             "experiment_id": "test_artifact",
                             "config": {"domain": "math"}}) + "\n",
                 encoding="utf-8")
    t = _tree(tmp_path)
    summary = t.bootstrap_from_raw(raw_dir=rawdir)
    assert summary["skipped_no_evidence"] == 1
    assert "test_artifact" not in t.experiment_ids("math")


def test_bootstrap_unknown_domain_goes_to_unknown(tmp_path):
    _write_raw(tmp_path, "exp_a", "math", None)  # no difficulty_range -> other
    t = _tree(tmp_path)
    summary = t.bootstrap_from_raw(raw_dir=tmp_path / "raw")
    assert summary["registered"]["math/other"] == 1