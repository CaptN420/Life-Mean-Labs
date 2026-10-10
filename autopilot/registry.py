"""Model registry and candidate promotion.

Implements the STABLE / CANDIDATE / REJECTED model lifecycle (design doc §37)
with full lineage tracking.

Core rules:
- A candidate never replaces the stable model without passing a held-out
  benchmark and an explicit promotion decision (§38).
- Training and promotion stay separate: you can benchmark a candidate without
  promoting it, and you never silently mutate a dataset that trained a model
  (§39).
- Rejected candidates are retained, not destroyed (§35).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ModelRegistry")


class ModelStatus(str, Enum):
    STABLE = "stable"
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class PromotionDecision(str, Enum):
    PROMOTE = "promote"
    REJECT = "reject"


@dataclass
class BenchmarkResult:
    """Result of evaluating a candidate on a held-out benchmark."""

    benchmark_id: str
    benchmark_name: str
    metrics: Dict[str, float]
    compared_to: Optional[str] = None  # stable model id it was compared against
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "benchmark_name": self.benchmark_name,
            "metrics": dict(self.metrics),
            "compared_to": self.compared_to,
            "timestamp": self.timestamp,
        }


@dataclass
class ModelRecord:
    """A single model with full lineage and lifecycle state."""

    model_id: str = field(default_factory=lambda: f"model_{uuid.uuid4().hex[:8]}")
    name: str = ""
    status: ModelStatus = ModelStatus.CANDIDATE
    parent_model_id: Optional[str] = None
    training_dataset_id: Optional[str] = None
    training_config: Dict[str, Any] = field(default_factory=dict)
    benchmark_results: List[BenchmarkResult] = field(default_factory=list)
    promotion_decision: Optional[PromotionDecision] = None
    promotion_reason: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def latest_benchmark(self) -> Optional[BenchmarkResult]:
        """Most recent benchmark result, or None."""
        if not self.benchmark_results:
            return None
        return max(self.benchmark_results, key=lambda b: b.timestamp)

    def best_metric(self, metric: str = "accuracy") -> Optional[float]:
        """Best value of a metric across benchmarks."""
        values = [
            b.metrics.get(metric)
            for b in self.benchmark_results
            if metric in b.metrics
        ]
        values = [v for v in values if v is not None]
        return max(values) if values else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "status": self.status.value,
            "parent_model_id": self.parent_model_id,
            "training_dataset_id": self.training_dataset_id,
            "training_config": self.training_config,
            "benchmark_results": [b.to_dict() for b in self.benchmark_results],
            "promotion_decision": (
                self.promotion_decision.value if self.promotion_decision else None
            ),
            "promotion_reason": self.promotion_reason,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelRecord":
        record = cls(
            model_id=data.get("model_id", f"model_{uuid.uuid4().hex[:8]}"),
            name=data.get("name", ""),
            status=ModelStatus(data.get("status", "candidate")),
            parent_model_id=data.get("parent_model_id"),
            training_dataset_id=data.get("training_dataset_id"),
            training_config=data.get("training_config", {}),
            benchmark_results=[
                BenchmarkResult(
                    benchmark_id=b.get("benchmark_id"),
                    benchmark_name=b.get("benchmark_name", ""),
                    metrics=b.get("metrics", {}),
                    compared_to=b.get("compared_to"),
                    timestamp=b.get("timestamp", time.time()),
                )
                for b in data.get("benchmark_results", [])
            ],
            promotion_decision=(
                PromotionDecision(data["promotion_decision"])
                if data.get("promotion_decision")
                else None
            ),
            promotion_reason=data.get("promotion_reason", ""),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
        )
        return record


class ModelRegistry:
    """Tracks stable, candidate and rejected models with lineage."""

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the registry.

        Args:
            storage_path: Path to JSON registry file.
                Defaults to `autopilot/data/model_registry.json`.
        """
        if storage_path is None:
            # State file is written relative to the CWD so it is writable in
            # both a source checkout and a wheel install (never site-packages).
            storage_path = str(Path.cwd() / "autopilot" / "data" / "model_registry.json")
        self.storage_path = Path(storage_path)
        self._models: Dict[str, ModelRecord] = {}
        self._load()

    # ---- Storage -----------------------------------------------------------

    def _load(self) -> None:
        """Load registry from disk."""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for mid, record_data in data.items():
                self._models[mid] = ModelRecord.from_dict(record_data)
            logger.info("Loaded %d models from registry", len(self._models))
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Failed to load model registry: %s", e)

    def _persist(self) -> None:
        """Persist registry to disk (atomic write)."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.storage_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {mid: r.to_dict() for mid, r in self._models.items()},
                f,
                indent=2,
            )
        tmp.replace(self.storage_path)

    # ---- Registration ------------------------------------------------------

    def register_candidate(
        self,
        *,
        name: str = "",
        parent_model_id: Optional[str] = None,
        training_dataset_id: Optional[str] = None,
        training_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ModelRecord:
        """Register a new candidate model.

        Args:
            name: Human-readable model name
            parent_model_id: The stable model this candidate derives from
            training_dataset_id: Dataset used for training (idempotency/lineage)
            training_config: Training hyperparameters/provenance
            metadata: Extra metadata

        Returns:
            The registered candidate ModelRecord
        """
        parent_id = parent_model_id or self.stable_model_id()
        record = ModelRecord(
            name=name,
            status=ModelStatus.CANDIDATE,
            parent_model_id=parent_id,
            training_dataset_id=training_dataset_id,
            training_config=training_config or {},
            metadata=metadata or {},
        )
        self._models[record.model_id] = record
        self._persist()
        logger.info("Registered candidate %s (parent=%s)", record.model_id, parent_id)
        return record

    def record_benchmark(
        self,
        model_id: str,
        *,
        benchmark_name: str,
        metrics: Dict[str, float],
    ) -> BenchmarkResult:
        """Attach a held-out benchmark result to a model.

        Args:
            model_id: Model to update
            benchmark_name: Name of the held-out benchmark
            metrics: Metric -> value map (e.g. {"accuracy": 0.83})

        Returns:
            The BenchmarkResult
        """
        model = self.get(model_id)
        if model is None:
            raise KeyError(f"Model {model_id} not found")

        stable_id = None
        if model.status != ModelStatus.STABLE:
            stable_id = self.stable_model_id()
        result = BenchmarkResult(
            benchmark_id=f"bench_{uuid.uuid4().hex[:8]}",
            benchmark_name=benchmark_name,
            metrics=metrics,
            compared_to=None if model_id == stable_id else stable_id,
        )
        model.benchmark_results.append(result)
        self._persist()
        logger.info("Recorded benchmark %s for %s: %s", benchmark_name, model_id, metrics)
        return result

    # ---- Promotion ----------------------------------------------------------

    def decide_promotion(
        self,
        model_id: str,
        metric: str = "accuracy",
        min_improvement: float = 0.0,
    ) -> bool:
        """Compare a candidate against the stable model and decide promotion.

        The stable model is NOT automatically overwritten. A candidate is
        promoted only if it is strictly better (or equal within the
        improvement margin) on the held-out metric.

        Args:
            model_id: Candidate model to evaluate
            metric: Benchmark metric used for comparison
            min_improvement: Minimum margin required to improve on stable

        Returns:
            promotion_decision result; True if promoted, False if rejected
        """
        candidate = self.get(model_id)
        if candidate is None:
            raise KeyError(f"Model {model_id} not found")
        if candidate.status == ModelStatus.STABLE:
            raise ValueError("Cannot promote the stable model")

        stable_id = self.stable_model_id()
        stable = self.get(stable_id) if stable_id else None

        c_metric = candidate.best_metric(metric) or 0.0
        s_metric = stable.best_metric(metric) if stable else 0.0

        decision = PromotionDecision.PROMOTE if c_metric >= s_metric + min_improvement else PromotionDecision.REJECT
        candidate.promotion_decision = decision
        candidate.promotion_reason = (
            f"candidate {metric}={c_metric:.3f} vs stable {metric}={s_metric:.3f}"
            + (f" (requires +{min_improvement})" if min_improvement else "")
        )

        if decision == PromotionDecision.PROMOTE:
            # Demote old stable, promote candidate.
            if stable is not None:
                stable.status = ModelStatus.REJECTED
                stable.promotion_decision = PromotionDecision.REJECT
                stable.promotion_reason = "superseded by " + model_id
            candidate.status = ModelStatus.STABLE
        else:
            candidate.status = ModelStatus.REJECTED

        self._persist()
        logger.info(
            "Promotion decision for %s: %s (%s)", model_id, decision.value, candidate.promotion_reason
        )
        return decision == PromotionDecision.PROMOTE

    # ---- Queries ------------------------------------------------------------

    def get(self, model_id: str) -> Optional[ModelRecord]:
        """Get a model by ID."""
        return self._models.get(model_id)

    def get_by_name(self, name: str) -> Optional[ModelRecord]:
        """Get the newest model with the given name.

        ``created_at`` is ``time.time()``; two candidates registered in the
        same clock tick can tie. ``max`` is therefore additionally keyed by
        the registration index (dict insertion order), so the "newest" model
        is deterministic — independent of PYTHONHASHSEED / dict iteration —
        and a tie resolves to the most-recently registered candidate.
        """
        matches = [m for m in self._models.values() if m.name == name]
        if not matches:
            return None
        return max(
            enumerate(matches),
            key=lambda iv: (iv[1].created_at, iv[0]),
        )[1]

    def all(self) -> List[ModelRecord]:
        """All models."""
        return list(self._models.values())

    def stable_model_id(self) -> Optional[str]:
        """ID of the current stable model, or None."""
        for m in self._models.values():
            if m.status == ModelStatus.STABLE:
                return m.model_id
        return None

    def stable_model(self) -> Optional[ModelRecord]:
        """The current stable model, or None."""
        mid = self.stable_model_id()
        return self.get(mid) if mid else None

    def candidates(self) -> List[ModelRecord]:
        """All candidate models."""
        return [m for m in self._models.values() if m.status == ModelStatus.CANDIDATE]

    def rejected(self) -> List[ModelRecord]:
        """All rejected models (retained, never destroyed §35)."""
        return [m for m in self._models.values() if m.status == ModelStatus.REJECTED]

    def count(self) -> int:
        """Number of tracked models."""
        return len(self._models)

    def lineage(self, model_id: str) -> List[str]:
        """Chain of parent model IDs from a model back to the root."""
        chain: List[str] = []
        mid = model_id
        visited = set()
        while mid and mid not in visited:
            visited.add(mid)
            chain.append(mid)
            model = self.get(mid)
            mid = model.parent_model_id if model else None
        return chain