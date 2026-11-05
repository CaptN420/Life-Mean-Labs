"""Tool coverage + explicit failure for generated tasks.

Two defects found by running a real experiment (seed 21, Docker):

  1. the generator emits ``Calculate sin(144 degrees)`` / ``Calculate log(28)``,
     but ``detect_tool`` returned None although the ``trig`` / ``log`` tools
     existed → the runner answered ``None``;
  2. that ``None`` was silent: an unsupported task looked exactly like a wrong
     answer, so nothing in the artifact said "we have no tool for this".

These tests pin both: the tasks are solved, and an unservable task fails with a
machine-readable reason that reaches the serialized result (hence RAW).
"""

from __future__ import annotations

import math

import pytest

from experiments.generation.schemas import GeneratedTask
from experiments.runner import ExperimentRunner, UnsupportedTaskError
from library.tools.detection import detect_tool
from library.tools.math import MATH_TOOLS


def _task(description: str, ground_truth, domain: str = "math") -> GeneratedTask:
    return GeneratedTask(
        task_id="t_" + description[:8].replace(" ", "_"),
        description=description,
        domain=domain,
        difficulty=1,
        ground_truth=ground_truth,
        reasoning_type="calculation",
        generation_strategy="template",
    )


@pytest.mark.parametrize(
    "description,tool,domain",
    [
        ("Calculate sin(144 degrees)", "math_trig", "math"),
        ("Calculate cos(60 degrees)", "math_trig", "math"),
        ("Calculate tan(45 degrees)", "math_trig", "math"),
        ("Calculate log(28)", "math_log", "math"),
        ("Calculate square root of 49", "math_sqrt", "math"),
        ("Find the GCD of 45 and 41", "math_gcd", "math"),
    ],
)
def test_detection_covers_generated_task_families(description, tool, domain):
    detected = detect_tool(description)
    assert detected is not None, f"no tool detected for {description!r}"
    assert detected["tool_name"] == tool
    assert detected["domain"] == domain


@pytest.mark.parametrize(
    "description,ground_truth",
    [
        ("Calculate sin(144 degrees)", round(math.sin(math.radians(144)), 6)),
        ("Calculate cos(60 degrees)", round(math.cos(math.radians(60)), 6)),
        ("Calculate log(28)", round(math.log(28), 6)),
        ("Calculate square root of 49", 7.0),
    ],
)
def test_runner_answers_trig_log_sqrt(description, ground_truth):
    result = ExperimentRunner().run_task(_task(description, ground_truth))
    assert result.error is None, result.error
    assert result.answer == pytest.approx(ground_truth, abs=1e-6)
    assert result.is_valid


def test_log_uses_natural_base_like_the_generator():
    """``log(28)`` ground truth is ``math.log(28)`` (natural), not log10."""
    result = ExperimentRunner().run_task(_task("Calculate log(28)", round(math.log(28), 6)))
    assert result.answer == pytest.approx(3.332205, abs=1e-6)
    assert result.answer != pytest.approx(round(math.log10(28), 6), abs=1e-6)


def test_unsupported_task_fails_explicitly_not_silently():
    result = ExperimentRunner().run_task(
        _task("Prove the Riemann hypothesis rigorously", "proof")
    )
    assert result.answer is None
    assert result.is_valid is False
    assert result.error and result.error.startswith("UNSUPPORTED_TASK")
    # the reason survives serialization, so RAW carries it
    assert result.to_dict()["error"].startswith("UNSUPPORTED_TASK")


def test_error_is_none_on_a_normal_success():
    result = ExperimentRunner().run_task(_task("Find the GCD of 45 and 41", 1))
    assert result.is_valid and result.error is None
    assert "error" in result.to_dict()


def test_sqrt_tool_rejects_negative_input():
    out = MATH_TOOLS["sqrt"]["fn"](x=-4)
    assert out["valid"] is False
    assert "error" in out


def test_math_ground_truth_roundtrip_for_newly_covered_tools():
    """Sanity check: the tool outputs equal the generator's rounding (6 dp)."""
    assert MATH_TOOLS["trig"]["fn"](angle_deg=144)["sin"] == round(math.sin(math.radians(144)), 6)
    assert MATH_TOOLS["log"]["fn"](value=28, base=math.e)["log"] == round(math.log(28), 6)
