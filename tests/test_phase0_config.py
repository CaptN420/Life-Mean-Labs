"""Tests for experiment configuration.

Phase 0: Repository mapping and deterministic mode trace.
"""

import pytest


def test_experiment_config_defaults():
    """Test default configuration values."""
    from experiments.config import ExperimentConfig
    config = ExperimentConfig()
    assert config.deterministic is True
    assert config.llm_reasoning is False
    assert config.tools is True
    assert config.thinkers is False
    assert config.reflection is False
    assert config.debate is False
    assert config.diversification is False
    assert config.domain == "math"
    assert config.difficulty_range == (1, 5)
    assert config.num_tasks == 100
    assert config.seed == 42


def test_experiment_config_custom_values():
    """Test custom configuration values."""
    from experiments.config import ExperimentConfig
    config = ExperimentConfig(
        deterministic=False,
        llm_reasoning=True,
        domain="physics",
        difficulty_range=(3, 5),
        num_tasks=500,
        seed=123,
    )
    assert config.deterministic is False
    assert config.llm_reasoning is True
    assert config.domain == "physics"
    assert config.difficulty_range == (3, 5)
    assert config.num_tasks == 500
    assert config.seed == 123


def test_experiment_config_auto_generates_ids():
    """Test that experiment_id and run_id are auto-generated."""
    from experiments.config import ExperimentConfig
    config = ExperimentConfig()
    assert config.experiment_id != ""
    assert config.run_id != ""
    assert isinstance(config.experiment_id, str)
    assert isinstance(config.run_id, str)


def test_experiment_config_to_dict():
    """Test serialization to dictionary."""
    from experiments.config import ExperimentConfig
    config = ExperimentConfig(seed=123, experiment_id="exp_001", run_id="run_001")
    d = config.to_dict()
    assert d["seed"] == 123
    assert d["experiment_id"] == "exp_001"
    assert d["run_id"] == "run_001"
    assert d["deterministic"] is True


def test_experiment_config_from_dict():
    """Test deserialization from dictionary."""
    from experiments.config import ExperimentConfig
    data = {
        "deterministic": False,
        "llm_reasoning": True,
        "domain": "coding",
        "difficulty_range": [2, 4],
        "num_tasks": 200,
        "seed": 456,
        "experiment_id": "exp_test",
        "run_id": "run_test",
    }
    config = ExperimentConfig.from_dict(data)
    assert config.deterministic is False
    assert config.llm_reasoning is True
    assert config.domain == "coding"
    assert config.difficulty_range == (2, 4)
    assert config.num_tasks == 200
    assert config.seed == 456


def test_experiment_mode_a():
    """Test Mode A: deterministic only."""
    from experiments.config import get_experiment_mode
    config = get_experiment_mode("A")
    assert config.deterministic is True
    assert config.llm_reasoning is False


def test_experiment_mode_b():
    """Test Mode B: LLM only."""
    from experiments.config import get_experiment_mode
    config = get_experiment_mode("B")
    assert config.deterministic is False
    assert config.llm_reasoning is True


def test_experiment_mode_c():
    """Test Mode C: hybrid."""
    from experiments.config import get_experiment_mode
    config = get_experiment_mode("C")
    assert config.deterministic is True
    assert config.llm_reasoning is True


def test_experiment_mode_d():
    """Test Mode D: full philosophical council."""
    from experiments.config import get_experiment_mode
    config = get_experiment_mode("D")
    assert config.thinkers is True
    assert config.reflection is True
    assert config.debate is True


def test_experiment_mode_e():
    """Test Mode E: diversification."""
    from experiments.config import get_experiment_mode
    config = get_experiment_mode("E")
    assert config.diversification is True


def test_experiment_mode_unknown():
    """Test unknown mode returns default config."""
    from experiments.config import get_experiment_mode
    config = get_experiment_mode("UNKNOWN")
    assert config.deterministic is True  # Default


def test_mode_description():
    """Test human-readable mode description."""
    from experiments.config import ExperimentConfig

    # Mode A
    config_a = ExperimentConfig(deterministic=True, llm_reasoning=False)
    assert "DETERMINISTIC" in config_a.mode_description()

    # Mode B
    config_b = ExperimentConfig(deterministic=False, llm_reasoning=True)
    assert "LLM_ONLY" in config_b.mode_description()

    # Mode C
    config_c = ExperimentConfig(deterministic=True, llm_reasoning=True)
    assert "HYBRID" in config_c.mode_description()

    # With thinkers
    config_d = ExperimentConfig(thinkers=True, reflection=True)
    desc = config_d.mode_description()
    assert "THINKERS" in desc
    assert "REFLECTION" in desc


def test_experiment_config_reproducibility():
    """Test that configuration preserves reproducibility metadata."""
    from experiments.config import ExperimentConfig
    config = ExperimentConfig(
        seed=42,
        generator_version="1.0.0",
        prompt_version="2.0.0",
    )
    d = config.to_dict()
    assert d["seed"] == 42
    assert d["generator_version"] == "1.0.0"
    assert d["prompt_version"] == "2.0.0"
