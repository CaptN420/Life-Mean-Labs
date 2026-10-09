"""Logic tools — Deterministic logic, reasoning and philosophy toolkit (5 tools).

Pure Python, zero LLM. Adapted from Mia_Brain (captn/tools/logic_tools.py).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List


# ── Syllogism Validator (Aristotelian / Categorical) ──────────────────────────

VALID_SYLLOGISMS: Dict[int, List[tuple]] = {
    1: [("A", "A", "A"), ("E", "A", "E"), ("A", "I", "I"), ("E", "I", "O")],
    2: [("E", "A", "E"), ("A", "E", "E"), ("E", "I", "O"), ("A", "O", "O")],
    3: [("A", "A", "I"), ("I", "A", "I"), ("A", "I", "I"), ("E", "A", "O"), ("E", "I", "O")],
    4: [("A", "A", "I"), ("A", "E", "E"), ("I", "A", "I"), ("E", "A", "O"), ("E", "I", "O")],
}

MOOD_NAMES = {
    1: {("A", "A", "A"): "Barbara", ("E", "A", "E"): "Celarent",
        ("A", "I", "I"): "Darii", ("E", "I", "O"): "Ferio"},
    2: {("E", "A", "E"): "Cesare", ("A", "E", "E"): "Camestres",
        ("E", "I", "O"): "Festino", ("A", "O", "O"): "Baroco"},
    3: {("A", "A", "I"): "Darapti", ("I", "A", "I"): "Disamis",
        ("A", "I", "I"): "Datisi", ("E", "A", "O"): "Felapton",
        ("E", "I", "O"): "Ferison"},
    4: {("A", "A", "I"): "Bramantip", ("A", "E", "E"): "Camenes",
        ("I", "A", "I"): "Dimaris", ("E", "A", "O"): "Fesapo",
        ("E", "I", "O"): "Fresison"},
}

FALLACY_MAP = {
    "undistributed_middle": "Le moyen terme n'est pas distribué",
    "illicit_major": "Terme majeur distribué dans la conclusion mais pas dans la prémisse",
    "illicit_minor": "Terme mineur distribué dans la conclusion mais pas dans la prémisse",
    "existential_fallacy": "Conclusion existentielle avec prémisses universelles",
    "four_terms": "Quatre termes (quaternio terminorum)",
    "negative_premises": "Deux prémisses négatives",
    "affirmative_from_negative": "Conclusion affirmative avec prémisse négative",
    "negative_from_affirmative": "Conclusion négative avec deux prémisses affirmatives",
}


def _parse_categorical(proposition: str) -> dict | None:
    p = proposition.strip().rstrip(".")
    p = re.sub(r"\s+", " ", p)
    m = re.match(
        r"(All|No|Some)\s+(.+?)\s+(?:are|is)\s+(not\s+)?(.+?)$",
        p, re.IGNORECASE
    )
    if not m:
        m = re.match(r"(.+?)\s+(?:are|is)\s+(.+?)$", p, re.IGNORECASE)
        if m:
            return {"type": "A", "subject": m.group(1).strip(), "predicate": m.group(2).strip()}
        return None

    quantifier = m.group(1).lower()
    subject = m.group(2).strip()
    has_not = m.group(3) is not None
    predicate = m.group(4).strip()

    if quantifier == "all" and not has_not:
        return {"type": "A", "subject": subject, "predicate": predicate}
    if quantifier == "no":
        return {"type": "E", "subject": subject, "predicate": predicate}
    if quantifier == "some" and not has_not:
        return {"type": "I", "subject": subject, "predicate": predicate}
    if quantifier == "some" and has_not:
        return {"type": "O", "subject": subject, "predicate": predicate}
    return None


def _is_distributed(term: str, proposition_type: str, position: str) -> bool:
    if position == "subject":
        return proposition_type in ("A", "E")
    else:
        return proposition_type in ("E", "O")


def validate_syllogism(major: str, minor: str, conclusion: str) -> Dict[str, Any]:
    maj = _parse_categorical(major)
    min_ = _parse_categorical(minor)
    conc = _parse_categorical(conclusion)

    if not all([maj, min_, conc]):
        errors = []
        if not maj:
            errors.append(f"Major premise invalide: {major}")
        if not min_:
            errors.append(f"Minor premise invalide: {minor}")
        if not conc:
            errors.append(f"Conclusion invalide: {conclusion}")
        return {"valid": False, "error": "; ".join(errors)}

    S = conc["subject"]
    P = conc["predicate"]

    maj_terms = {maj["subject"], maj["predicate"]}
    min_terms = {min_["subject"], min_["predicate"]}
    conc_terms = {conc["subject"], conc["predicate"]}

    middle_candidates = (maj_terms & min_terms) - conc_terms

    if len(middle_candidates) == 0:
        return {
            "valid": False,
            "error": "Aucun moyen terme trouvé (doit apparaître dans les deux prémisses)",
            "fallacies": ["four_terms"],
            "major": major, "minor": minor, "conclusion": conclusion,
        }
    if len(middle_candidates) > 1:
        return {
            "valid": False,
            "error": f"Multiples moyens termes possibles: {middle_candidates}",
            "major": major, "minor": minor, "conclusion": conclusion,
        }

    M = list(middle_candidates)[0]

    if P in (maj["subject"], maj["predicate"]) and S in (min_["subject"], min_["predicate"]):
        pass
    elif P in (min_["subject"], min_["predicate"]) and S in (maj["subject"], maj["predicate"]):
        maj, min_ = min_, maj
        maj_terms, min_terms = min_terms, maj_terms

    if maj["subject"] == M and min_["predicate"] == M:
        figure = 1
    elif maj["predicate"] == M and min_["predicate"] == M:
        figure = 2
    elif maj["subject"] == M and min_["subject"] == M:
        figure = 3
    elif maj["predicate"] == M and min_["subject"] == M:
        figure = 4
    else:
        figure = 0

    mood = (maj["type"], min_["type"], conc["type"])
    fallacies = []

    all_terms = set()
    for prop in [maj, min_, conc]:
        all_terms.add(prop["subject"])
        all_terms.add(prop["predicate"])
    if len(all_terms) != 3:
        fallacies.append("four_terms")

    m_dist_in_maj = _is_distributed(M, maj["type"], "subject" if maj["subject"] == M else "predicate")
    m_dist_in_min = _is_distributed(M, min_["type"], "subject" if min_["subject"] == M else "predicate")
    if not m_dist_in_maj and not m_dist_in_min:
        fallacies.append("undistributed_middle")

    p_dist_in_conc = _is_distributed(P, conc["type"], "subject" if conc["subject"] == P else "predicate")
    p_dist_in_maj = _is_distributed(P, maj["type"], "subject" if maj["subject"] == P else "predicate")
    if p_dist_in_conc and not p_dist_in_maj:
        fallacies.append("illicit_major")

    s_dist_in_conc = _is_distributed(S, conc["type"], "subject" if conc["subject"] == S else "predicate")
    s_dist_in_min = _is_distributed(S, min_["type"], "subject" if min_["subject"] == S else "predicate")
    if s_dist_in_conc and not s_dist_in_min:
        fallacies.append("illicit_minor")

    if maj["type"] in ("E", "O") and min_["type"] in ("E", "O"):
        fallacies.append("negative_premises")

    one_neg = (maj["type"] in ("E", "O")) != (min_["type"] in ("E", "O"))
    if one_neg and conc["type"] not in ("E", "O"):
        fallacies.append("affirmative_from_negative")

    both_aff = maj["type"] in ("A", "I") and min_["type"] in ("A", "I")
    if both_aff and conc["type"] in ("E", "O"):
        fallacies.append("negative_from_affirmative")

    univ_premises = maj["type"] in ("A", "E") and min_["type"] in ("A", "E")
    part_conclusion = conc["type"] in ("I", "O")
    if univ_premises and part_conclusion and mood not in [
        v for valid_moods in VALID_SYLLOGISMS.values() for v in valid_moods
    ]:
        fallacies.append("existential_fallacy")

    is_valid = len(fallacies) == 0
    valid_for_figure = figure in VALID_SYLLOGISMS and mood in VALID_SYLLOGISMS[figure]

    mood_name = ""
    if figure in MOOD_NAMES and mood in MOOD_NAMES[figure]:
        mood_name = MOOD_NAMES[figure][mood]

    return {
        "valid": is_valid,
        "fallacies": fallacies,
        "fallacy_explanations": [FALLACY_MAP.get(f, f) for f in fallacies],
        "figure": figure,
        "mood": f"{maj['type']}{min_['type']}{conc['type']}",
        "mood_name": mood_name,
        "valid_in_traditional": mood in [v for valid_list in VALID_SYLLOGISMS.values() for v in valid_list],
        "terms": {"major_term": P, "minor_term": S, "middle_term": M},
        "major": maj, "minor": min_, "conclusion": conc,
    }


# ── Logical Fallacy Detection ────────────────────────────────────────────────

FALLACY_PATTERNS: List[Dict[str, Any]] = [
    {
        "id": "false_dilemma",
        "name": "Faux dilemme (False Dilemma / False Dichotomy)",
        "pattern": r"(either|or)\s+.*(?:or\s+(?:else\s+)?)?(?:must|will|certainly|completely)",
        "explanation": "Présente deux options comme les seules possibles, alors qu'il en existe d'autres.",
        "confidence_low": 0.4, "confidence_high": 0.8,
    },
    {
        "id": "false_dilemma_2",
        "name": "Faux dilemme (False Dilemma)",
        "pattern": r"(?:ban|destroy|eliminate|all|everyone)\s+.*(?:or|otherwise)\s+.*(?:collapse|chaos|disaster|ruin)",
        "explanation": "Présente une fausse dichotomie avec des conséquences extrêmes.",
        "confidence_low": 0.5, "confidence_high": 0.85,
    },
    {
        "id": "straw_man",
        "name": "Homme de paille (Straw Man)",
        "pattern": r"(?:so you|so you're|so we|you want to|you think we should)\s+(?:want to\s+)?(?:destroy|eliminate|ban|get rid of|remove all)\s+",
        "explanation": "Déforme la position de l'interlocuteur pour la rendre plus facile à attaquer.",
        "confidence_low": 0.5, "confidence_high": 0.85,
    },
    {
        "id": "ad_hominem",
        "name": "Attaque personnelle (Ad Hominem)",
        "pattern": r"(?:you're\s+(?:just|only|merely)\s+)|(?:you\s+only\s+say\s+that\s+because)",
        "explanation": "Attaque la personne au lieu de l'argument.",
        "confidence_low": 0.3, "confidence_high": 0.7,
    },
    {
        "id": "slippery_slope",
        "name": "Pente glissante (Slippery Slope)",
        "pattern": r"(?:first\s+.*,?\s+then|next\s+thing\s+(?:you\s+|we\s+)?know|before\s+long)\s+.*(?:everyone|all|nobody|complete|total)",
        "explanation": "Suppose qu'une première étape mène inévitablement à une chaîne d'événements extrêmes.",
        "confidence_low": 0.3, "confidence_high": 0.7,
    },
    {
        "id": "false_cause",
        "name": "Cause fausse (Post Hoc Ergo Propter Hoc)",
        "pattern": r"(?:because|since|as)\s+.*\s+(?:then|caused|led to|resulted in)\s+",
        "explanation": "Suppose qu'une corrélation implique une causalité.",
        "confidence_low": 0.2, "confidence_high": 0.5,
    },
    {
        "id": "begging_question",
        "name": "Pétition de principe (Begging the Question)",
        "pattern": r"(?:obviously|clearly|of course|it is obvious that|it goes without saying|naturally)\s+",
        "explanation": "Suppose la conclusion dans les prémisses.",
        "confidence_low": 0.2, "confidence_high": 0.5,
    },
    {
        "id": "black_or_white",
        "name": "Argument du noir ou blanc (Black-or-White)",
        "pattern": r"(?:if\s+(?:you'?re\s+)?not\s+(?:with\s+us|for\s+it|on\s+our\s+side),?\s+(?:you'?re|then\s+you'?re)\s+(?:against\s+us|against\s+it))",
        "explanation": "Réduit les positions à deux options mutuellement exclusives.",
        "confidence_low": 0.6, "confidence_high": 0.9,
    },
]


def detect_fallacy(text: str) -> Dict[str, Any]:
    text_lower = text.lower().strip()
    detected = []

    for pattern_def in FALLACY_PATTERNS:
        m = re.search(pattern_def["pattern"], text_lower, re.IGNORECASE)
        if m:
            match_text = m.group(0)
            ratio = len(match_text) / max(len(text_lower), 1)
            confidence = pattern_def["confidence_low"] + ratio * (
                pattern_def["confidence_high"] - pattern_def["confidence_low"]
            )
            confidence = min(confidence, pattern_def["confidence_high"])

            detected.append({
                "fallacy_id": pattern_def["id"],
                "fallacy_name": pattern_def["name"],
                "confidence": round(confidence, 3),
                "matched_text": match_text.strip(),
                "explanation": pattern_def["explanation"],
            })

    seen_ids = set()
    unique_detected = []
    for d in detected:
        fid = d["fallacy_id"]
        if fid not in seen_ids:
            seen_ids.add(fid)
            unique_detected.append(d)

    if not unique_detected:
        has_premise = any(w in text_lower for w in ["because", "since", "therefore", "thus", "if", "so", "implies"])
        if has_premise:
            return {
                "valid": True,
                "fallacies_detected": [],
                "note": "Aucune fallacie classique détectée. L'argument semble formellement valide ou nécessite une analyse plus approfondie.",
                "argument_type": "conditional_reasoning" if "if" in text_lower else "deductive",
            }

    return {
        "valid": True,
        "fallacies_detected": unique_detected,
        "total_detected": len(unique_detected),
        "has_fallacy": len(unique_detected) > 0,
        "text": text,
    }


# ── Ambiguity Analyzer ───────────────────────────────────────────────────────

def analyze_ambiguity(text: str) -> Dict[str, Any]:
    text_clean = text.strip().rstrip(".")
    words = text_clean.lower().split()

    has_everyone = "everyone" in words or "everybody" in words
    has_someone = "someone" in words or "somebody" in words
    has_all = "all" in words
    has_some = "some" in words
    has_not = "not" in words
    has_double_quantifier = (has_everyone or has_all) and (has_someone or has_some)

    if has_double_quantifier:
        interp1 = {
            "reading": "∀-∃ (wide scope universal)",
            "interpretation": "Chaque X a un Y (possiblement différent pour chacun)",
            "formal": "∀x ∃y P(x,y)",
            "plausible": True,
        }
        interp2 = {
            "reading": "∃-∀ (wide scope existential / lone individual)",
            "interpretation": "Il existe un Y que tous les X ont (le/la même)",
            "formal": "∃y ∀x P(x,y)",
            "plausible": True,
        }
        return {
            "valid": True,
            "text": text_clean,
            "ambiguous": True,
            "ambiguity_type": "quantifier_scope",
            "interpretations": [interp1, interp2],
            "interpretation_count": 2,
        }

    elif has_not and len(words) > 3:
        interp1 = {
            "reading": "¬∀ — Négation du quantificateur universel",
            "interpretation": "La négation porte sur la quantification : « Pas tous/toutes »",
            "formal": "¬∀x P(x)",
            "plausible": True,
        }
        interp2 = {
            "reading": "∀¬ — Négation du prédicat",
            "interpretation": "La négation porte sur le prédicat : « Aucun/aucune »",
            "formal": "∀x ¬P(x)",
            "plausible": True,
        }
        return {
            "valid": True,
            "text": text_clean,
            "ambiguous": True,
            "ambiguity_type": "negation_scope",
            "interpretations": [interp1, interp2],
            "interpretation_count": 2,
        }

    return {
        "valid": True,
        "text": text_clean,
        "ambiguous": False,
        "ambiguity_type": None,
        "note": "Aucune ambiguïté de quantification ou de portée détectée dans cette phrase.",
    }


# ── Tool Registry ────────────────────────────────────────────────────────────

LOGIC_TOOLS: Dict[str, Dict[str, Any]] = {
    "syllogism": {"fn": lambda major, minor, conclusion: validate_syllogism(major, minor, conclusion),
                  "domain": "logic", "description": "Valide un syllogisme catégorique"},
    "fallacy": {"fn": lambda text: detect_fallacy(text),
                "domain": "logic", "description": "Détecte les fallacies logiques dans un énoncé"},
    "ambiguity": {"fn": lambda text: analyze_ambiguity(text),
                  "domain": "logic", "description": "Analyse l'ambiguïté de quantification/portée"},
}


def list_tools() -> List[Dict[str, str]]:
    return [
        {"name": name, "domain": info["domain"], "description": info["description"]}
        for name, info in sorted(LOGIC_TOOLS.items())
    ]


def execute(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a logic tool by name with kwargs."""
    if tool_name not in LOGIC_TOOLS:
        return {"valid": False, "error": f"Unknown tool: {tool_name}"}
    fn = LOGIC_TOOLS[tool_name]["fn"]
    try:
        result = fn(**kwargs)
        return result
    except Exception as e:
        return {"valid": False, "error": str(e)}
