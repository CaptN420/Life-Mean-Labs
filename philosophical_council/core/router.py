"""Model router engine for dynamic model selection."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class RouterMethod(str, Enum):
    """Available routing methods."""

    CONTEXT_AWARE = "context_aware"
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    LLM = "llm"
    RANDOM = "random"


@dataclass
class ModelCandidate:
    """A model candidate with metadata for routing."""

    id: str
    parameter_count: str = ""  # e.g., "7B", "13B"
    vram_estimate_gb: float = 0.0
    usage_count: int = 0
    success_count: int = 0
    avg_response_time: float = 0.0

    @property
    def quality_score(self) -> float:
        """Calculate a quality score based on performance."""
        if self.usage_count == 0:
            return 0.5  # Neutral for unknown models

        success_rate = self.success_count / self.usage_count
        speed_bonus = max(0, 1.0 - (self.avg_response_time / 5.0))  # Normalize to 5s
        return (success_rate * 0.7) + (speed_bonus * 0.3)


@dataclass
class RoutingContext:
    """Context information for making routing decisions."""

    topic: str = ""
    current_debate_depth: int = 0  # How deep in the debate
    last_speaker_roles: list[str] = field(default_factory=list)
    requires_creativity: bool = False
    requires_reasoning: bool = False
    requires_speed: bool = False


class ModelRouter:
    """Intelligent model router that selects appropriate models based on context."""

    def __init__(self, available_models: list[str] | None = None) -> None:
        self._pool: dict[str, ModelCandidate] = {}
        self._method = RouterMethod.CONTEXT_AWARE
        self._round_robin_index = 0

        if available_models:
            for model_id in available_models:
                self.add_model(model_id)

    def add_model(self, model_id: str, **kwargs: object) -> None:
        """Add a model to the routing pool."""
        self._pool[model_id] = ModelCandidate(
            id=model_id,
            parameter_count=kwargs.get("parameter_count", ""),
            vram_estimate_gb=kwargs.get("vram_estimate_gb", 0.0),
        )
        logger.debug("Added model to router pool: %s", model_id)

    def remove_model(self, model_id: str) -> bool:
        """Remove a model from the routing pool."""
        if model_id in self._pool:
            del self._pool[model_id]
            logger.debug("Removed model from router pool: %s", model_id)
            return True
        return False

    def set_method(self, method: str) -> None:
        """Set the routing method."""
        try:
            self._method = RouterMethod(method)
            logger.info("Router method set to: %s", method)
        except ValueError:
            logger.warning("Invalid router method: %s, falling back to context_aware", method)
            self._method = RouterMethod.CONTEXT_AWARE

    def select_model(self, context: Optional[RoutingContext] = None) -> str:
        """Select a model based on the current context and routing method."""
        if not self._pool:
            logger.warning("No models available in router pool")
            return ""

        context = context or RoutingContext()

        if self._method == RouterMethod.ROUND_ROBIN:
            return self._round_robin_select()
        elif self._method == RouterMethod.WEIGHTED:
            return self._weighted_select(context)
        elif self._method == RouterMethod.CONTEXT_AWARE:
            return self._context_aware_select(context)
        elif self._method == RouterMethod.RANDOM:
            return self._random_select()
        else:
            return self._round_robin_select()

    def _round_robin_select(self) -> str:
        """Select next model in round-robin fashion."""
        if not self._pool:
            return ""

        models = list(self._pool.keys())
        if not models:
            return ""

        selected = models[self._round_robin_index % len(models)]
        self._round_robin_index += 1
        logger.debug("Round-robin selected: %s", selected)
        return selected

    def _weighted_select(self, context: RoutingContext) -> str:
        """Select model based on quality scores and weights."""
        if not self._pool:
            return ""

        # Calculate weights for each model
        candidates = []
        for model_id, candidate in self._pool.items():
            weight = candidate.quality_score

            # Bonus for models that match context requirements
            if context.requires_speed and candidate.vram_estimate_gb < 8.0:
                weight *= 1.2  # Prefer faster/smaller models for speed
            if context.requires_reasoning and candidate.parameter_count >= "13B":
                weight *= 1.3  # Prefer larger models for reasoning

            candidates.append((model_id, weight))

        # Weighted random selection
        total_weight = sum(w for _, w in candidates)
        if total_weight <= 0:
            return self._random_select()

        weights = [w / total_weight for _, w in candidates]
        selected = random.choices(
            [m for m, _ in candidates],
            weights=weights,
            k=1,
        )[0]

        logger.debug("Weighted select: %s (total weight: %.2f)", selected, total_weight)
        return selected

    def _context_aware_select(self, context: RoutingContext) -> str:
        """Select model based on debate context and requirements."""
        if not self._pool:
            return ""

        # Score each model based on context
        best_model = None
        best_score = -1

        for model_id, candidate in self._pool.items():
            score = 0.5  # Base score

            # Factor 1: Parameter count vs requirements
            param_b = float(candidate.parameter_count.replace("B", "").replace("b", "")) if candidate.parameter_count else 0
            if context.requires_reasoning and param_b >= 7:
                score += 0.3  # Bonus for reasoning-capable models
            elif context.requires_speed and param_b <= 7:
                score += 0.2  # Bonus for faster models

            # Factor 2: VRAM estimation (prefer models that fit)
            if candidate.vram_estimate_gb > 0 and candidate.vram_estimate_gb < 16:
                score += 0.1  # Prefer models with reasonable VRAM

            # Factor 3: Historical performance
            score += candidate.quality_score * 0.2

            if score > best_score:
                best_score = score
                best_model = model_id

        logger.debug("Context-aware select: %s (score: %.2f)", best_model, best_score)
        return best_model or self._round_robin_select()

    def _random_select(self) -> str:
        """Select a random model."""
        if not self._pool:
            return ""
        return random.choice(list(self._pool.keys()))

    def record_performance(
        self,
        model_id: str,
        success: bool,
        response_time: float,
    ) -> None:
        """Record performance metrics for a model."""
        if model_id not in self._pool:
            return

        candidate = self._pool[model_id]
        candidate.usage_count += 1
        if success:
            candidate.success_count += 1

        # Update average response time (exponential moving average)
        alpha = 0.1
        candidate.avg_response_time = (
            alpha * response_time + (1 - alpha) * candidate.avg_response_time
        )

        logger.debug(
            "Recorded performance for %s: success=%s, time=%.2fs",
            model_id,
            success,
            response_time,
        )

    def get_pool_summary(self) -> dict[str, object]:
        """Get a summary of the model pool."""
        return {
            "method": self._method.value,
            "models": {
                model_id: {
                    "parameter_count": c.parameter_count,
                    "vram_estimate_gb": c.vram_estimate_gb,
                    "usage_count": c.usage_count,
                    "success_count": c.success_count,
                    "quality_score": c.quality_score,
                }
                for model_id, c in self._pool.items()
            },
        }

    @property
    def available_models(self) -> list[str]:
        """Get list of available model IDs."""
        return list(self._pool.keys())

    def clear_pool(self) -> None:
        """Clear the model pool."""
        self._pool.clear()
        logger.info("Router pool cleared")
