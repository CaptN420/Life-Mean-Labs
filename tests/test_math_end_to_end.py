"""De la génération à la réponse : chaque opération mathématique est branchée.

Le support d'un outil ne vaut que si une tâche peut l'atteindre. Ces tests
vérifient la chaîne complète : le générateur produit la tâche, la vérité terrain
vient du même outil, le runner la résout, et la validation la déclare correcte.

Deux pièges évités ici :
  - `reasoning_type="calculation"` (le défaut) ne doit pas forcer la trigonométrie,
    sinon toutes les tâches mathématiques deviennent des sinus ;
  - les angles de `tan` sont tirés hors de 90° + k·180°, sinon la tâche n'a
    aucune réponse dans le domaine réel.
"""

from __future__ import annotations

import math
import re

import pytest

from experiments.generation.task_generator import TaskGenerator
from experiments.runner import ExperimentRunner
from experiments.ui_controller import ExperimentState

FAMILIES = ("sin", "cos", "tan", "log", "ln", "log10", "sqrt", "exp", "pow")


def _family(description: str) -> str:
    match = re.search(r"\b(sin|cos|tan|log10|log|ln|sqrt|exp|pow)\s*\(", description)
    if match:
        return match.group(1)
    if "^" in description:
        return "pow"
    return ""


def test_calculation_does_not_force_trigonometry():
    """`calculation` est le reasoning_type par défaut : il doit rester varié."""
    families = set()
    generator = TaskGenerator(seed=7)
    for _ in range(80):
        task = generator.generate("math", difficulty=1, reasoning_type="calculation")
        families.add(_family(task.description))
    assert len(families - {""}) >= 5, families


def test_every_supported_family_is_generated():
    families = set()
    for seed in range(1, 6):
        generator = TaskGenerator(seed=seed)
        for _ in range(60):
            task = generator.generate("math", difficulty=1)
            families.add(_family(task.description))
    missing = set(FAMILIES) - families
    assert not missing, f"jamais généré: {sorted(missing)}"


def test_generated_tasks_are_always_answerable():
    runner = ExperimentRunner()
    failures = []
    for seed in range(1, 5):
        generator = TaskGenerator(seed=seed)
        for _ in range(40):
            task = generator.generate("math", difficulty=1)
            result = runner.run_task(task)
            if not result.is_successful:
                failures.append((task.description, task.ground_truth,
                                 result.answer, result.error))
    assert not failures, failures[:5]


def test_tan_is_never_generated_at_a_singularity():
    generator = TaskGenerator(seed=11)
    for _ in range(120):
        task = generator.generate("math", difficulty=1, reasoning_type="tan")
        angle = int(re.search(r"tan\((\d+)", task.description).group(1))
        assert abs(math.cos(math.radians(angle))) > 1e-6, task.description


def test_ground_truth_matches_the_tool_that_answers():
    """Vérité terrain et réponse viennent du même outil : pas de convention double."""
    generator = TaskGenerator(seed=3)
    runner = ExperimentRunner()
    checked = 0
    for _ in range(60):
        task = generator.generate("math", difficulty=1)
        if not _family(task.description):
            continue
        result = runner.run_task(task)
        assert result.answer == pytest.approx(task.ground_truth, abs=1e-6), (
            task.description, result.answer, task.ground_truth,
        )
        checked += 1
    assert checked >= 10


def test_log_ground_truth_is_natural_not_base_ten():
    generator = TaskGenerator(seed=5)
    for _ in range(60):
        task = generator.generate("math", difficulty=1, reasoning_type="log")
        n = int(re.search(r"log\((\d+)\)", task.description).group(1))
        assert task.ground_truth == pytest.approx(round(math.log(n), 6)), task.description
        assert task.ground_truth != pytest.approx(round(math.log10(n), 6))


# ── agrégation des erreurs par code ────────────────────────────────────────


def test_error_codes_are_counted_by_machine_code():
    state = ExperimentState(experiment_id="exp")
    state.errors = [
        "MATH_DOMAIN_ERROR: tool 'math_sqrt' rejected expression='sqrt(-1)'",
        "MATH_DOMAIN_ERROR: tool 'math_log' rejected expression='log(0)'",
        "UNSUPPORTED_MATH_OPERATION: unknown math operation 'csc'",
    ]
    assert state.error_codes() == {"MATH_DOMAIN_ERROR": 2, "UNSUPPORTED_MATH_OPERATION": 1}
    payload = state.to_dict()
    assert payload["error_count"] == 3
    assert payload["error_codes"]["MATH_DOMAIN_ERROR"] == 2


def test_error_codes_are_empty_on_a_clean_run():
    payload = ExperimentState(experiment_id="exp").to_dict()
    assert payload["error_count"] == 0
    assert payload["error_codes"] == {}


def test_unparseable_error_is_not_invented():
    state = ExperimentState(experiment_id="exp")
    state.errors = ["something went wrong"]
    assert state.error_codes() == {"UNCLASSIFIED": 1}
