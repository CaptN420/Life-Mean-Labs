"""Analyse déterministe d'une expression mathématique écrite en clair.

Aucun `eval`, aucun appel LLM, aucune exécution de code venant de l'utilisateur :
on ne reconnaît qu'une **grammaire fermée** (`nom(args)` et `a^b`) portant sur des
littéraux numériques et les constantes `pi` / `e`. Tout ce qui sort de cette
grammaire est refusé explicitement, avec l'expression d'origine conservée.

Pourquoi ce module existe : `detect_tool()` dit *quel* outil prendre, mais rien
n'extraie la valeur. Le runner se rabattait sur `re.findall(r"\\d+", description)`,
ce qui a produit deux défauts mesurés :

    "Calculate sqrt(-1)"  -> x = 1     (le signe était perdu, réponse fabriquée)
    "Calculate tan(90 degrees)" -> 1.6e16 d'un cos calculé en degrés

Codes d'erreur :

- ``UNSUPPORTED_MATH_OPERATION`` : opération inconnue, arité fausse, argument non
  littéral, expression malformée. Rien n'est tenté, rien n'est inventé.
- ``MATH_DOMAIN_ERROR`` : opération connue, entrée hors du domaine réel
  (`sqrt(-1)`, `log(0)`, `tan(90°)`). Le verdict vient de l'outil, pas d'ici.

Convention de base pour les logarithmes (explicite, jamais implicite) :
``ln(x)`` et ``log(x)`` = logarithme **naturel** (base e, convention du
générateur de tâches) ; ``log10(x)`` = base 10 ; ``log(x, b)`` = base b.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

UNSUPPORTED_MATH_OPERATION = "UNSUPPORTED_MATH_OPERATION"
MATH_DOMAIN_ERROR = "MATH_DOMAIN_ERROR"

_NUM = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_PI_FRAC = r"(?:(?P<mult>[-+]?\d+(?:\.\d+)?)\s*\*\s*)?pi(?:\s*/\s*(?P<div>\d+(?:\.\d+)?))?"
# Même forme SANS groupes nommés : `_CARET` assemble deux littéraux, et des
# groupes nommés dupliqués feraient échouer `re.compile` (« redefinition of
# group name 'mult' »).
_PI_FRAC_NC = r"(?:[-+]?\d+(?:\.\d+)?\s*\*\s*)?pi(?:\s*/\s*\d+(?:\.\d+)?)?"
_UNIT = r"(?P<unit>degrees?|deg|°|radians?|rad)?"

_LEAD = re.compile(
    r"^\s*(?:please\s+)?(?:(?:calculate|compute|evaluate|find|determine|solve|"
    r"work\s+out|what\s+is|what's|the\s+value\s+of|the\s+result\s+of|give\s+me)\b[\s:]*)+",
    re.IGNORECASE,
)

_CALL = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<args>[^()]*)\)\s*\.?$")
_CARET = re.compile(rf"^(?P<left>{_NUM}|{_PI_FRAC_NC})\s*\^\s*(?P<right>{_NUM}|{_PI_FRAC_NC})\s*\.?$")

# Opérations mathématiques connues mais NON prises en charge : les nommer permet
# de répondre « opération non supportée » au lieu de laisser le routeur choisir
# un outil au hasard.
_UNSUPPORTED_NAMES = {
    "sec", "csc", "cosec", "cot", "cotan", "asin", "acos", "atan", "arcsin",
    "arccos", "arctan", "sinh", "cosh", "tanh", "log1p", "ln1p", "mod", "modulo",
    "root", "nthroot", "cbrt", "gamma", "erf", "floor", "ceil", "trunc",
}

_FUNCS: Dict[str, Dict[str, Any]] = {
    "sin": {"tool": "trig", "arity": (1, 1), "kind": "angle"},
    "cos": {"tool": "trig", "arity": (1, 1), "kind": "angle"},
    "tan": {"tool": "trig", "arity": (1, 1), "kind": "angle"},
    "ln": {"tool": "log", "arity": (1, 1), "kind": "log", "base": math.e},
    "log": {"tool": "log", "arity": (1, 2), "kind": "log", "base": math.e},
    "log10": {"tool": "log", "arity": (1, 1), "kind": "log", "base": 10.0},
    "log2": {"tool": "log", "arity": (1, 1), "kind": "log", "base": 2.0},
    "exp": {"tool": "exp", "arity": (1, 1), "kind": "value"},
    "sqrt": {"tool": "sqrt", "arity": (1, 1), "kind": "value"},
    "pow": {"tool": "pow", "arity": (2, 2), "kind": "power"},
}


@dataclass(frozen=True)
class MathCall:
    """Résultat d'analyse : soit un appel d'outil prêt, soit une erreur motivée."""

    expression: str
    operation: Optional[str] = None
    tool_name: Optional[str] = None
    kwargs: Optional[Dict[str, Any]] = None
    param_key: str = ""
    unit: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.tool_name is not None

    def to_dict(self) -> Dict[str, Any]:
        """Traçabilité : ce qui a été demandé, reconnu, et retenu."""
        return {
            "expression": self.expression,
            "operation": self.operation,
            "tool": self.tool_name,
            "parameters": dict(self.kwargs or {}),
            "unit": self.unit,
            "error": self.error,
            "error_code": self.error_code,
        }


def _clean(description: str) -> str:
    text = description.strip()
    for _ in range(3):  # « Calculate the value of ... » : préfixes empilés
        stripped = _LEAD.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return text.strip().rstrip("?.!").strip()


def _literal(token: str) -> Tuple[Optional[float], bool]:
    """Retourne (valeur, est_radian_implicite). None si non littéral.

    `est_radian_implicite` est vrai quand la valeur est exprimée en π : une unité
    absente vaut alors des radians (``sin(pi/2)``), jamais des degrés.
    """
    text = token.strip()
    if not text:
        return None, False
    pi_match = re.fullmatch(_PI_FRAC, text, re.IGNORECASE)
    if pi_match:
        mult = float(pi_match.group("mult")) if pi_match.group("mult") else 1.0
        div = float(pi_match.group("div")) if pi_match.group("div") else 1.0
        if div == 0:
            return None, False
        return mult * math.pi / div, True
    if text.lower() == "e":
        return math.e, False
    if re.fullmatch(_NUM, text):
        return float(text), False
    return None, False


def _parse_angle_arg(raw: str, expression: str, name: str = "") -> MathCall:
    text = raw.strip()
    unit_match = re.search(_UNIT + r"\s*$", text, re.IGNORECASE)
    unit_token = ""
    core = text
    if unit_match and unit_match.group("unit"):
        unit_token = unit_match.group("unit").lower()
        core = text[: unit_match.start()].strip()
    value, pi_based = _literal(core)
    if value is None:
        return MathCall(
            expression=expression,
            error=f"argument {raw.strip()!r} is not a numeric literal",
            error_code=UNSUPPORTED_MATH_OPERATION,
        )

    if unit_token in ("radians", "radian", "rad"):
        unit = "radians"
    elif unit_token in ("degrees", "degree", "deg", "°"):
        unit = "degrees"
    elif pi_based:
        unit = "radians"  # π/2 sans unité : radians, explicitement
    else:
        unit = "degrees"  # convention du générateur : "sin(144 degrees)"

    key = "angle_rad" if unit == "radians" else "angle_deg"
    return MathCall(expression=expression, operation=name, tool_name="trig",
                    kwargs={key: value}, param_key=key, unit=unit)


def _parse_args(args_raw: str, spec: Dict[str, Any], expression: str,
                name: str) -> MathCall:
    if "(" in args_raw or ")" in args_raw:
        return MathCall(expression=expression,
                        error="nested expressions are not supported",
                        error_code=UNSUPPORTED_MATH_OPERATION)
    parts = [p.strip() for p in args_raw.split(",")] if args_raw.strip() else []
    low, high = spec["arity"]
    if not (low <= len(parts) <= high):
        return MathCall(
            expression=expression,
            error=f"{name} expects {low}" + (f"-{high}" if high != low else "")
                  + f" argument(s), got {len(parts)}",
            error_code=UNSUPPORTED_MATH_OPERATION,
        )

    kind = spec["kind"]
    if kind == "angle":
        if len(parts) != 1:
            return MathCall(expression=expression,
                            error=f"{name} takes exactly one angle",
                            error_code=UNSUPPORTED_MATH_OPERATION)
        return _parse_angle_arg(parts[0], expression, name)

    values: List[float] = []
    for part in parts:
        unit_match = re.search(_UNIT + r"\s*$", part, re.IGNORECASE)
        if unit_match and unit_match.group("unit"):
            return MathCall(expression=expression,
                            error=f"unit given where none is expected: {part!r}",
                            error_code=UNSUPPORTED_MATH_OPERATION)
        value, _pi = _literal(part)
        if value is None:
            return MathCall(expression=expression,
                            error=f"argument {part!r} is not a numeric literal",
                            error_code=UNSUPPORTED_MATH_OPERATION)
        values.append(value)

    if kind == "log":
        base = float(spec["base"])
        if len(values) == 2:
            base = values[1]
        return MathCall(expression=expression, operation=name, tool_name="log",
                        kwargs={"value": values[0], "base": base},
                        param_key="value")
    if kind == "value":
        return MathCall(expression=expression, operation=name,
                        tool_name=str(spec["tool"]),
                        kwargs={"x": values[0]}, param_key="x")
    if kind == "power":
        return MathCall(expression=expression, operation=name, tool_name="pow",
                        kwargs={"base": values[0], "exponent": values[1]},
                        param_key="base")
    return MathCall(expression=expression,
                    error=f"internal: unknown kind {kind!r}",
                    error_code=UNSUPPORTED_MATH_OPERATION)


def parse_math_task(description: str) -> Optional[MathCall]:
    """Analyse une description de tâche mathématique.

    Returns:
        ``None`` si la description n'est pas une expression mathématique
        exploitable (les autres domaines ne sont donc pas affectés), sinon un
        ``MathCall`` — soit exécutable, soit porteur d'un code d'erreur.
    """
    if not description or not description.strip():
        return None
    expression = _clean(description)
    if not expression:
        return None

    call = _CALL.match(expression)
    if call:
        name = call.group("name").lower()
        spec = _FUNCS.get(name)
        if spec is None:
            if name in _UNSUPPORTED_NAMES:
                return MathCall(
                    expression=expression,
                    error=f"math operation {name!r} is not supported",
                    error_code=UNSUPPORTED_MATH_OPERATION,
                )
            return None  # pas une fonction mathématique connue : on ne tranche pas
        return _parse_args(call.group("args"), spec, expression, name)

    caret = _CARET.match(expression)
    if caret:
        left, _l_pi = _literal(caret.group("left"))
        right, _r_pi = _literal(caret.group("right"))
        if left is None or right is None:
            return MathCall(expression=expression,
                            error="power operands must be numeric literals",
                            error_code=UNSUPPORTED_MATH_OPERATION)
        return MathCall(expression=expression, operation="pow", tool_name="pow",
                        kwargs={"base": left, "exponent": right},
                        param_key="base")

    if "^" in expression:
        # « 2^ » : intention de puissance, opérande manquant. Refus motivé.
        return MathCall(expression=expression,
                        error="power expression is incomplete (missing operand)",
                        error_code=UNSUPPORTED_MATH_OPERATION)

    return None
