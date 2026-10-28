"""Metrics collection for LIFE_MEAN.

Collects and aggregates system metrics.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


class MetricsCollector:
    """Collects and aggregates system metrics."""

    def __init__(self):
        self._metrics: Dict[str, List[MetricPoint]] = {}
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}

    def increment(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter."""
        self._counters[name] = self._counters.get(name, 0) + value
        self._record_point(name, float(value), tags)

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge value."""
        self._gauges[name] = value
        self._record_point(name, value, tags)

    def observe(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record an observation in a histogram."""
        if name not in self._histograms:
            self._histograms[name] = []
        self._histograms[name].append(value)

        # Keep only last 1000 observations
        if len(self._histograms[name]) > 1000:
            self._histograms[name] = self._histograms[name][-500:]

        self._record_point(name, value, tags)

    def _record_point(self, name: str, value: float, tags: Optional[Dict[str, str]]) -> None:
        """Record a metric point."""
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(MetricPoint(name=name, value=value, tags=tags or {}))

        # Keep only last 1000 points
        if len(self._metrics[name]) > 1000:
            self._metrics[name] = self._metrics[name][-500:]

    def get_counter(self, name: str) -> int:
        """Get a counter value."""
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> Optional[float]:
        """Get a gauge value."""
        return self._gauges.get(name)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get histogram statistics."""
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0}

        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    def get_recent_points(
        self,
        name: str,
        limit: int = 100,
    ) -> List[MetricPoint]:
        """Get recent metric points."""
        points = self._metrics.get(name, [])
        return points[-limit:]

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                name: self.get_histogram_stats(name)
                for name in self._histograms
            },
        }

    def reset(self) -> int:
        """Reset all metrics. Returns count reset."""
        count = len(self._metrics) + len(self._counters) + len(self._gauges) + len(self._histograms)
        self._metrics.clear()
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        return count
