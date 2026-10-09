"""Compare V1 — pairwise comparability classification.

Deterministically decides how confidently two runs can be compared, based on
the immutable condition snapshots carried in RAW (NOT on outcome metrics —
the whole point of a controlled comparison is that the independent variables
are the same except for the ones under study).

Levels (spec §26):
- HIGHLY_CONTROLLED        — conditions differ in exactly one variable
- PARTIALLY_CONTROLLED     — share the same domain/template but differ in 2+
- EXPLORATORY              — related but loosely matched (different setup,
                              same broad goal)
- NOT_DIRECTLY_COMPARABLE  — conditions are so different that any conclusion
                              would be misleading

Compare NEVER claims causality from an uncontrolled comparison: the level + a
reason are returned so callers (and the UI) can tell a measured difference
from a confounded one.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from compare.models import ComparabilityKind, PairOutcome

# Independent variables that define the experimental condition. These are the
# keys Compare treats as meaningful when deciding comparability.
_CONDITION_KEYS = (
    "domain",
    "num_tasks",
    "difficulty_range",
    "seed",
    "deterministic",
    "debate",
    "llm_reasoning",
    "tools",
    "thinkers",
    "reflection",
    "diversification",
    "template_id",
    "generator_version",
    "prompt_version",
)


def _cond(condition: Dict[str, Any]) -> Dict[str, Any]:
    """Filter a condition to the comparison-relevant independent variables,
    normalised to strings so values compare robustly."""
    out: Dict[str, Any] = {}
    for k in _CONDITION_KEYS:
        if k in condition:
            v = condition[k]
            if isinstance(v, (list, tuple)):
                v = tuple(v)
            out[k] = v
    return out


def _same_domain(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return _cond(left).get("domain") == _cond(right).get("domain")


def _diff_map(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Tuple[Any, Any]]:
    """Variables where the two conditions differ: {key: (left, right)}."""
    lc, rc = _cond(left), _cond(right)
    keys = sorted(set(lc) | set(rc))
    return {k: (lc.get(k, "<absent>"), rc.get(k, "<absent>")) for k in keys
            if lc.get(k) != rc.get(k)}


def _substance(lc: Dict[str, Any], rc: Dict[str, Any]) -> bool:
    """Whether the two conditions record enough independent variables to claim
    experimental control. A minimal/legacy condition that only records
    ``domain`` does NOT provide control — two such runs must not be called
    HIGHLY_CONTROLLED just because their single recorded var matches."""
    meaningful_l = [k for k in lc if k != "domain"]
    meaningful_r = [k for k in rc if k != "domain"]
    return bool(meaningful_l) and bool(meaningful_r)


def compare_pair(left: RunMetrics, right: RunMetrics) -> PairOutcome:
    """Classify the comparability of two runs and report common/changed vars."""
    pair = PairOutcome(left=left.experiment_id, right=right.experiment_id)
    if left.experiment_id == right.experiment_id:
        pair.comparability = ComparabilityKind.NOT_DIRECTLY_COMPARABLE
        pair.reason = "same experiment compared to itself"
        return pair

    lc, rc = _cond(left.condition), _cond(right.condition)
    diffs = _diff_map(lc, rc)

    # Common variables.
    common = {k: lc[k] for k in lc if k in rc and lc[k] == rc[k]}
    pair.common_variables = common

    lkeys = set(lc)
    rkeys = set(rc)

    if not _substance(lc, rc):
        pair.comparability = ComparabilityKind.EXPLORATORY
        pair.reason = ("insufficient recorded independent variables (minimal/"
                       "legacy conditions) to claim experimental control")
    elif _same_domain(lc, rc) and len(diffs) == 0:
        # Identical conditions (only run-id / id differ): re-runs, seedless.
        pair.comparability = ComparabilityKind.HIGHLY_CONTROLLED
        pair.reason = "identical conditions (same independent variables)"
    elif _same_domain(lc, rc) and len(diffs) == 1:
        key = next(iter(diffs))
        pair.comparability = ComparabilityKind.HIGHLY_CONTROLLED
        pair.reason = (
            f"same domain, single variable differs: {key} "
            f"({diffs[key][0]} vs {diffs[key][1]})")
    elif _same_domain(lc, rc):
        pair.comparability = ComparabilityKind.PARTIALLY_CONTROLLED
        pair.reason = f"same domain, {len(diffs)} variables differ"
    elif lkeys and rkeys:
        # Both define a condition but the domains differ.
        pair.comparability = ComparabilityKind.EXPLORATORY
        pair.reason = "conditions share no domain; loose exploratory match"
    else:
        pair.comparability = ComparabilityKind.NOT_DIRECTLY_COMPARABLE
        pair.reason = "conditions are too different for a meaningful comparison"

    pair.changed_variables = {k: v[0] for k, v in diffs.items()}
    return pair