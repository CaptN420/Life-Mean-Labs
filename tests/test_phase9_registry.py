"""Tests for ModelRegistry / candidate promotion (design doc Phase 9, §37 §38 §39)."""

from __future__ import annotations

import pytest

from autopilot.registry import (
    ModelRegistry,
    ModelStatus,
    PromotionDecision,
)


@pytest.fixture()
def registry(tmp_path):
    return ModelRegistry(storage_path=str(tmp_path / "registry.json"))


# ---- Registration ----------------------------------------------------------

def test_register_candidate(registry):
    model = registry.register_candidate(name="v2")
    assert model.model_id
    assert model.status == ModelStatus.CANDIDATE
    assert registry.count() == 1


def test_first_candidate_no_parent(registry):
    model = registry.register_candidate(name="v1")
    assert model.parent_model_id is None  # no stable yet


def test_candidate_links_to_stable_parent(registry):
    stable = registry.register_candidate(name="v1")
    registry.record_benchmark(stable.model_id, benchmark_name="heldout", metrics={"accuracy": 0.8})
    assert registry.decide_promotion(stable.model_id) is True
    assert registry.stable_model_id() == stable.model_id

    candidate = registry.register_candidate(name="v2")
    assert candidate.parent_model_id == stable.model_id
    assert candidate.training_dataset_id is None


# ---- Benchmark -------------------------------------------------------------

def test_record_benchmark_attaches_metrics(registry):
    model = registry.register_candidate(name="v1")
    bench = registry.record_benchmark(
        model.model_id, benchmark_name="holdout_math", metrics={"accuracy": 0.83}
    )
    assert bench.benchmark_name == "holdout_math"
    assert model.best_metric("accuracy") == 0.83
    assert model.latest_benchmark().metrics["accuracy"] == 0.83


def test_record_benchmark_unknown_model_raises(registry):
    with pytest.raises(KeyError):
        registry.record_benchmark("missing", benchmark_name="b", metrics={})


def test_best_metric_returns_max(registry):
    model = registry.register_candidate(name="v1")
    registry.record_benchmark(model.model_id, benchmark_name="b1", metrics={"accuracy": 0.7})
    registry.record_benchmark(model.model_id, benchmark_name="b2", metrics={"accuracy": 0.9})
    assert model.best_metric("accuracy") == 0.9


# ---- Promotion -------------------------------------------------------------

def test_promote_better_candidate(registry):
    # Stable v1: 0.8
    stable = registry.register_candidate(name="v1")
    registry.record_benchmark(stable.model_id, benchmark_name="holdout", metrics={"accuracy": 0.8})
    assert registry.decide_promotion(stable.model_id) is True
    assert registry.stable_model_id() == stable.model_id

    # Candidate v2: 0.9 -> promote
    cand = registry.register_candidate(name="v2")
    registry.record_benchmark(cand.model_id, benchmark_name="holdout", metrics={"accuracy": 0.9})
    promoted = registry.decide_promotion(cand.model_id)
    assert promoted is True
    assert registry.stable_model_id() == cand.model_id
    assert cand.promotion_decision == PromotionDecision.PROMOTE

    # Old stable demoted and retained (never destroyed §35)
    assert stable.status == ModelStatus.REJECTED
    assert stable.promotion_decision == PromotionDecision.REJECT


def test_reject_worse_candidate_and_stable_unchanged(registry):
    stable = registry.register_candidate(name="v1")
    registry.record_benchmark(stable.model_id, benchmark_name="holdout", metrics={"accuracy": 0.8})
    registry.decide_promotion(stable.model_id)
    assert registry.stable_model_id() == stable.model_id

    cand = registry.register_candidate(name="v2")
    registry.record_benchmark(cand.model_id, benchmark_name="holdout", metrics={"accuracy": 0.5})
    promoted = registry.decide_promotion(cand.model_id)
    assert promoted is False
    assert registry.stable_model_id() == stable.model_id  # unchanged
    assert cand.status == ModelStatus.REJECTED
    assert cand.promotion_decision == PromotionDecision.REJECT


def test_min_improvement_margin(registry):
    stable = registry.register_candidate(name="v1")
    registry.record_benchmark(stable.model_id, benchmark_name="holdout", metrics={"accuracy": 0.8})
    registry.decide_promotion(stable.model_id)

    # Equal metric, require +0.05 -> reject
    cand = registry.register_candidate(name="v2")
    registry.record_benchmark(cand.model_id, benchmark_name="holdout", metrics={"accuracy": 0.8})
    assert registry.decide_promotion(cand.model_id, min_improvement=0.05) is False

    # Clearly better, small margin -> promote
    cand2 = registry.register_candidate(name="v3")
    registry.record_benchmark(cand2.model_id, benchmark_name="holdout", metrics={"accuracy": 0.9})
    assert registry.decide_promotion(cand2.model_id, min_improvement=0.01) is True


def test_cannot_promote_stable(registry):
    stable = registry.register_candidate(name="v1")
    registry.record_benchmark(stable.model_id, benchmark_name="b", metrics={"accuracy": 0.8})
    registry.decide_promotion(stable.model_id)
    assert registry.stable_model_id() == stable.model_id
    with pytest.raises(ValueError):
        registry.decide_promotion(stable.model_id)


# ---- Lineage ---------------------------------------------------------------

def test_lineage_chain(registry):
    a = registry.register_candidate(name="v1")
    registry.record_benchmark(a.model_id, benchmark_name="b", metrics={"accuracy": 0.8})
    registry.decide_promotion(a.model_id)  # a becomes stable

    b = registry.register_candidate(name="v2")  # parent = a
    registry.record_benchmark(b.model_id, benchmark_name="b", metrics={"accuracy": 0.9})
    registry.decide_promotion(b.model_id)  # b becomes stable

    chain = registry.lineage(b.model_id)
    assert chain[0] == b.model_id
    assert chain[1] == a.model_id  # root


# ---- Persistence -----------------------------------------------------------

def test_persistence_across_reload(tmp_path):
    path = tmp_path / "registry.json"
    reg1 = ModelRegistry(storage_path=str(path))
    model = reg1.register_candidate(name="v1")
    reg1.record_benchmark(model.model_id, benchmark_name="b", metrics={"accuracy": 0.8})
    reg1.decide_promotion(model.model_id)
    del reg1

    reg2 = ModelRegistry(storage_path=str(path))
    assert reg2.count() == 1
    recovered = reg2.get(model.model_id)
    assert recovered.status == ModelStatus.STABLE
    assert recovered.promotion_decision == PromotionDecision.PROMOTE
    assert recovered.best_metric("accuracy") == 0.8


def test_empty_registry_no_stable(registry):
    assert registry.stable_model_id() is None
    assert registry.stable_model() is None
    assert registry.candidates() == []
    assert registry.rejected() == []


def test_get_by_name(registry):
    m1 = registry.register_candidate(name="same")
    m2 = registry.register_candidate(name="same")
    newest = registry.get_by_name("same")
    assert newest.model_id == m2.model_id
    assert newest.model_id != m1.model_id