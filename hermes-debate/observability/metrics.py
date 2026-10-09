"""
Metrics collection for Hermes orchestrator.
Tracks performance, resource usage, and debate statistics.
"""

import time
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: dict = field(default_factory=dict)


class MetricsCollector:
    """Collects and aggregates metrics from the Hermes system."""

    def __init__(self):
        self._metrics: dict[str, list[float]] = {}
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._start_time = datetime.utcnow()

    def increment(self, name: str, value: int = 1, **tags) -> None:
        """Increment a counter metric."""
        self._counters[name] = self._counters.get(name, 0) + value
        if tags:
            tag_key = f"{name}__{','.join(f'{k}={v}' for k, v in tags.items())}"
            self._metrics[tag_key] = self._metrics.get(tag_key, []) + [float(value)]

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge metric."""
        self._gauges[name] = value

    def histogram(self, name: str, value: float, **tags) -> None:
        """Record a histogram value."""
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(value)

    def get_counter(self, name: str) -> int:
        """Get counter value."""
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> Optional[float]:
        """Get gauge value."""
        return self._gauges.get(name)

    def get_histogram_stats(self, name: str) -> dict:
        """Get histogram statistics."""
        values = self._metrics.get(name, [])
        if not values:
            return {'count': 0, 'mean': 0.0, 'min': 0.0, 'max': 0.0}

        return {
            'count': len(values),
            'mean': sum(values) / len(values),
            'min': min(values),
            'max': max(values),
        }

    def summary(self) -> dict:
        """Get full metrics summary."""
        return {
            'uptime_seconds': (datetime.utcnow() - self._start_time).total_seconds(),
            'counters': dict(self._counters),
            'gauges': dict(self._gauges),
            'histograms': {
                name: self.get_histogram_stats(name)
                for name in self._metrics
            },
        }


# Predefined metric names
METRICS = {
    # Clef metrics
    'clef_latency_ms': 'Time to get decision from Clef',
    'clef_calls': 'Total CLEF decision calls',
    'clef_invalid_decisions': 'Invalid decisions from CLEF',

    # Reranker metrics
    'reranker_latency_ms': 'Time for reranking',
    'reranker_documents_processed': 'Documents processed by reranker',

    # Model metrics
    'model_load_time_ms': 'Time to load a model',
    'model_unload_time_ms': 'Time to unload a model',
    'model_inference_latency_ms': 'Time for model inference',
    'tokens_generated': 'Total tokens generated',

    # VRAM metrics
    'vram_peak_mb': 'Peak VRAM usage',
    'vram_current_mb': 'Current VRAM usage',

    # Debate metrics
    'turn_count': 'Number of debate turns',
    'routing_accuracy': 'Percentage of correct routing decisions',
    'fallback_count': 'Number of fallback activations',
    'loop_count': 'Number of loops detected',
    'judge_count': 'Number of judge calls',
    'consensus_reached': 'Consensus reached count',
}


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    return MetricsCollector()
