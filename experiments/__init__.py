"""Experiments — Synthetic data generation infrastructure.

This package provides tools for generating, validating, and exporting
synthetic training data using the existing reasoning architecture.
"""

from __future__ import annotations

from experiments.config import ExperimentConfig, get_experiment_mode

__all__ = ["ExperimentConfig", "get_experiment_mode"]
