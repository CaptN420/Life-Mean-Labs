"""Outils mathématiques : détection, paramètres exacts, refus explicites.

Trois défauts mesurés avant ce fichier de tests :

    "Calculate sqrt(-1)"  -> answer 1        (le balayage `\\d+` perdait le signe)
    "Calculate tan(90 degrees)" -> 1.6e16    (cos calculé en degrés, tan "inf")
    "Calculate 2^8"       -> answer None     (aucun mot-clé pour le worker)

Les tests couvrent : analyse sans eval, unités explicites, domaines invalides,
opérations inconnues, entrées malformées, traçabilité et non-régression.
"""

from __future__ import annotations

import math

import pytest

from experiments.generation.schemas import GeneratedTask
from experiments.runner import ExperimentRunner, UnsupportedTaskError
from library.tools.detection import detect_tool
from library.tools.math import MATH_TOOLS
from library.tools.math_expressions import (
    MATH_DOMAIN_ERROR,
    UNSUPPORTED_MATH_OPERATION,
    parse_math_task,
)

TOL = 1e-6


def _task(description: str, ground_truth=None) -> GeneratedTask:
    return GeneratedTask(
        task_id="t_math", domain="math", difficulty=1,
        description=description, ground_truth=ground_truth,
        reasoning_type="calculation",
    )


# ── 1. analyse : grammaire fermée, aucun eval ──────────────────────────────


@pytest.mark.parametrize("description,tool,kwargs", [
    ("Calculate sin(144 degrees)", "trig", {"angle_deg": 144.0}),
    ("Calculate cos(60 deg)", "trig", {"angle_deg": 60.0}),
    ("Calculate tan(45°)", "trig", {"angle_deg": 45.0}),
    ("Calculate sin(pi/2)", "trig", {"angle_rad": math.pi / 2}),
    ("Calculate cos(0.5 radians)", "trig", {"angle_rad": 0.5}),
    ("Calculate log(28)", "log", {"value": 28.0, "base": math.e}),
    ("Calculate ln(28)", "log", {"value": 28.0, "base": math.e}),
    ("Calculate log10(100)", "log", {"value": 100.0, "base": 10.0}),
    ("Calculate log2(8)", "log", {"value": 8.0, "base": 2.0}),
    ("Calculate log(8, 2)", "log", {"value": 8.0, "base": 2.0}),
    ("Calculate exp(2)", "exp", {"x": 2.0}),
    ("Calculate sqrt(144)", "sqrt", {"x": 144.0}),
    ("Calculate sqrt(2.25)", "sqrt", {"x": 2.25}),
    ("Calculate pow(2, 8)", "pow", {"base": 2.0, "exponent": 8.0}),
    ("Calculate 2^8", "pow", {"base": 2.0, "exponent": 8.0}),
    ("Evaluate -4^2", "pow", {"base": -4.0, "exponent": 2.0}),
])
def test_parses_supported_expressions(description, tool, kwargs):
    call = parse_math_task(description)
    assert call is not None and call.ok, call
    assert call.tool_name == tool
    assert call.kwargs == kwargs


def test_units_are_never_implicit():
    deg = parse_math_task("Calculate sin(30 degrees)")
    rad = parse_math_task("Calculate sin(30 radians)")
    assert deg.unit == "degrees" and "angle_deg" in deg.kwargs
    assert rad.unit == "radians" and "angle_rad" in rad.kwargs
    # un littéral en π sans unité est en radians, explicitement
    pi_call = parse_math_task("Calculate sin(pi/6)")
    assert pi_call.unit == "radians"
    assert pi_call.kwargs["angle_rad"] == pytest.approx(math.pi / 6)


def test_log_bases_are_documented_and_distinct():
    natural = parse_math_task("Calculate log(28)")
    ten = parse_math_task("Calculate log10(28)")
    assert natural.kwargs["base"] == math.e  # convention du générateur
    assert ten.kwargs["base"] == 10.0


@pytest.mark.parametrize("description,code", [
    ("Calculate csc(30 degrees)", UNSUPPORTED_MATH_OPERATION),
    ("Calculate arctan(1)", UNSUPPORTED_MATH_OPERATION),
    ("Calculate sin(30, 60)", UNSUPPORTED_MATH_OPERATION),
    ("Calculate sin(x)", UNSUPPORTED_MATH_OPERATION),
    ("Calculate log()", UNSUPPORTED_MATH_OPERATION),
    ("Calculate pow(2)", UNSUPPORTED_MATH_OPERATION),
    ("Calculate sqrt(4, 9)", UNSUPPORTED_MATH_OPERATION),
    ("Calculate exp(2 degrees)", UNSUPPORTED_MATH_OPERATION),
    ("Calculate 2^", UNSUPPORTED_MATH_OPERATION),
])
def test_malformed_or_unknown_expressions_are_refused(description, code):
    call = parse_math_task(description)
    assert call is not None, "an expression-looking input must never be ignored"
    assert call.ok is False
    assert call.error_code == code
    assert call.expression


def test_non_math_text_is_not_claimed():
    assert parse_math_task("Write a sorting function in Python") is None
    assert parse_math_task("") is None


# ── 2. l'outil trig, unités et singularités ────────────────────────────────


def test_trig_degrees_and_radians_agree():
    deg = MATH_TOOLS["trig"]["fn"](angle_deg=90)
    rad = MATH_TOOLS["trig"]["fn"](angle_rad=math.pi / 2)
    assert deg["sin"] == pytest.approx(1.0, abs=TOL)
    assert rad["sin"] == pytest.approx(1.0, abs=TOL)
    assert deg["unit"] == "degrees" and rad["unit"] == "radians"


def test_tan_at_90_is_explicitly_undefined_not_approximated():
    """sin/cos restent calculables ; tan est None et signalé, jamais 1.6e16."""
    out = MATH_TOOLS["trig"]["fn"](angle_deg=90)
    assert out["valid"] is True
    assert out["sin"] == pytest.approx(1.0, abs=TOL)
    assert out["tan"] is None
    assert out["tan_undefined"] is True
    assert "undefined" in out["note"]


def test_both_units_at_once_are_refused():
    out = MATH_TOOLS["trig"]["fn"](angle_deg=90, angle_rad=1.0)
    assert out["valid"] is False


# ── 3. domaines invalides : refus explicite, jamais de valeur inventée ─────


@pytest.mark.parametrize("description", [
    "Calculate sqrt(-1)",
    "Calculate sqrt(-2.5)",
    "Calculate log(0)",
    "Calculate log(-5)",
    "Calculate ln(0)",
    "Calculate log10(-1)",
    "Calculate log(8, 0)",
])
def test_out_of_domain_inputs_fail_explicitly(description):
    result = ExperimentRunner().run_task(_task(description, 0.0))
    assert result.answer is None, f"{description} produced a fabricated answer"
    assert result.error and result.error.startswith(MATH_DOMAIN_ERROR)
    assert result.is_valid is False


def test_no_sign_loss_on_negative_sqrt():
    """`sqrt(-1)` renvoyait 1.0 : le signe était mangé par `re.findall(r'\\d+')`."""
    result = ExperimentRunner().run_task(_task("Calculate sqrt(-1)", 1.0))
    assert result.answer != 1.0
    assert result.answer is None


# ── 4. exécution réelle de bout en bout ────────────────────────────────────


@pytest.mark.parametrize("description,expected", [
    ("Calculate sin(144 degrees)", round(math.sin(math.radians(144)), 6)),
    ("Calculate cos(60 degrees)", round(math.cos(math.radians(60)), 6)),
    ("Calculate tan(45 degrees)", 1.0),
    ("Calculate log(28)", round(math.log(28), 6)),
    ("Calculate ln(28)", round(math.log(28), 6)),
    ("Calculate log10(100)", 2.0),
    ("Calculate exp(2)", round(math.exp(2), 6)),
    ("Calculate sqrt(144)", 12.0),
    ("Calculate 2^8", 256.0),
    ("Calculate pow(2, 8)", 256.0),
    ("Calculate sin(pi/2)", 1.0),
])
def test_runner_answers_supported_operations(description, expected):
    result = ExperimentRunner().run_task(_task(description, expected))
    assert result.error is None, result.error
    assert result.answer == pytest.approx(expected, abs=TOL)
    assert result.is_valid is True


def test_unsupported_operation_keeps_its_expression():
    runner = ExperimentRunner()
    with pytest.raises(UnsupportedTaskError) as excinfo:
        task = _task("Calculate csc(30 degrees)")
        runner._execute_task(task, runner._route_task(task))
    message = str(excinfo.value)
    assert message.startswith(UNSUPPORTED_MATH_OPERATION)
    assert "csc(30 degrees)" in message


# ── 5. non-régression sur les outils déjà fonctionnels ────────────────────


@pytest.mark.parametrize("description,expected", [
    ("Calculate gcd(12, 18)", 6),
    ("Calculate lcm(4, 6)", 12),
    ("Calculate factorial(5)", 120),
    ("Calculate fibonacci(10)", 55),
    ("Calculate is_prime(97)", True),
    ("Calculate is_prime(100)", False),
])
def test_existing_math_tools_still_work(description, expected):
    result = ExperimentRunner().run_task(_task(description, expected))
    assert result.error is None, result.error
    assert result.answer == expected
    assert result.is_valid is True


def test_detection_recognises_the_new_operations():
    for description, tool in [
        ("Calculate ln(28)", "math_log"),
        ("Calculate log10(100)", "math_log"),
        ("Calculate exp(2)", "math_exp"),
        ("Calculate pow(2, 8)", "math_pow"),
    ]:
        detection = detect_tool(description)
        assert detection is not None, description
        assert detection["tool_name"] == tool
        assert detection["domain"] == "math"


def test_detection_does_not_hijack_words_containing_exp():
    """« explicit » contient « exp » : la clé courte exige un mot entier."""
    detection = detect_tool("Write an explicit sorting function")
    assert detection is None or detection["domain"] != "math", detection


# ── 6. traçabilité de l'expression ────────────────────────────────────────


def test_math_expression_is_traced_with_its_parameters():
    traces = []
    runner = ExperimentRunner()
    runner.trace_sink = traces.append
    result = runner.run_task(_task("Calculate log10(100)", 2.0))
    assert result.answer == pytest.approx(2.0)

    math_traces = [t for t in traces if t.get("rule") == "MathExpressionRule"]
    assert math_traces, [t.get("rule") for t in traces]
    payload = math_traces[-1]["after"]
    assert payload["parameters"] == {"value": 100.0, "base": 10.0}
    assert payload["answer"] == pytest.approx(2.0)
    assert payload["verdict"] == "answered"


def test_rejected_expression_is_traced_too():
    traces = []
    runner = ExperimentRunner()
    runner.trace_sink = traces.append
    runner.run_task(_task("Calculate sqrt(-4)", 2.0))
    math_traces = [t for t in traces if t.get("rule") == "MathExpressionRule"]
    assert math_traces
    payload = math_traces[-1]["after"]
    assert payload["verdict"] == "rejected"
    assert payload["reason"]
