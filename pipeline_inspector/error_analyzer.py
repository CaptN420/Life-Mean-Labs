"""Détection et classification des erreurs observées.

Le classifieur travaille sur les champs texte réellement présents
(``metadata.message``, ``metadata.error``, ``status``). Il ne déduit rien
d'absent et ne corrige jamais automatiquement : il produit des
recommandations lisibles.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from .redaction import redact_text

RULES = [
    {
        "code": "API_SCHEMA_ERROR",
        "label": "Payload refusé par le backend (schéma d'appel)",
        "pattern": re.compile(r"(?i)(missing required arguments|expected either|invalid.*(messages|payload|request body))"),
        "recommendation": "Le client envoie un schéma non supporté par LM Studio : vérifier les paramètres de chat/completions.",
    },
    {
        "code": "AGENT_PARSE_FAILURE",
        "label": "Réponse d'agent non parsable",
        "pattern": re.compile(r"(?i)(parse.*(failed|all attempts)|could not parse|json decode|invalid json)"),
        "recommendation": "Durcir le parsing de sortie du modèle et prévoir un fallback déterministe explicite.",
    },
    {
        "code": "CODE_BUG",
        "label": "Exception de code dans le pipeline",
        "pattern": re.compile(r"(?i)(list index out of range|is not defined|has no attribute|keyerror|typeerror|attributeerror|valueerror)"),
        "recommendation": "Corriger le défaut identifié dans le module concerné ; ajouter un test de non-régression.",
    },
    {
        "code": "DEGRADED_FALLBACK",
        "label": "Exécution dégradée (fallback utilisé)",
        "pattern": re.compile(r"(?i)(using deterministic fallback|fallback (used|engaged)|degraded mode)"),
        "recommendation": "Le résultat n'est pas celui du modèle : le marquer comme dégradé dans les rapports.",
    },
    {
        "code": "AUTH_INVALID",
        "label": "Authentification refusée par le backend",
        "pattern": re.compile(r"(?i)(error code:\s*401|invalid lm studio api|malformed lm studio api)"),
        "recommendation": "Vérifier la clé API LM Studio (Developer → Local Server) et son chargement.",
    },
    {
        "code": "AUTH_MISSING",
        "label": "Jeton d'authentification absent ou invalide",
        "pattern": re.compile(r"(?i)(no api key|missing.*(api key|token)|unauthorized|401|invalid.*key|auth.*fail)"),
        "recommendation": "Vérifier LIFE_MEAN_LLM_API_KEY / OPENROUTER_API_KEY et le fichier .env chargé par le conteneur.",
    },
    {
        "code": "MODEL_NOT_FOUND",
        "label": "Modèle introuvable côté backend",
        "pattern": re.compile(r"(?i)(model.*not found|no such model|404.*model|unknown model)"),
        "recommendation": "Vérifier le nom exact du modèle exposé par LM Studio (GET /v1/models) et le champ model du rôle.",
    },
    {
        "code": "ENDPOINT_INCOMPATIBLE",
        "label": "Endpoint ou schéma d'API incompatible",
        "pattern": re.compile(r"(?i)(unsupported.*(parameter|endpoint)|400 bad request|invalid request|not supported)"),
        "recommendation": "Comparer le payload envoyé au schéma OpenAI-compatible attendu par le backend.",
    },
    {
        "code": "MISSING_DEPENDENCY",
        "label": "Dépendance Python manquante",
        "pattern": re.compile(r"(?i)(no module named|modulenotfounderror|importerror)"),
        "recommendation": "Installer la dépendance dans l'environnement d'exécution (attention : l'image Docker est figée).",
    },
    {
        "code": "TEST_FAILURE",
        "label": "Test échoué",
        "pattern": re.compile(r"(?i)(test.*fail|assertionerror|pytest.*(error|failed))"),
        "recommendation": "Lire le rapport de test, isoler le cas en échec, ne pas relancer en boucle.",
    },
    {
        "code": "TIMEOUT",
        "label": "Délai dépassé / exécution interrompue",
        "pattern": re.compile(r"(?i)(timeout|timed out|interrupted|killed|aborted)"),
        "recommendation": "Vérifier la charge du backend et les limites de durée du run.",
    },
    {
        "code": "TRUNCATED_RESPONSE",
        "label": "Réponse incomplète",
        "pattern": re.compile(r"(?i)(truncat|incomplete|finish_reason.*length|max_tokens)"),
        "recommendation": "Augmenter max_tokens ou réduire la taille du contexte.",
    },
    {
        "code": "CONNECTION_ERROR",
        "label": "Connexion au backend impossible",
        "pattern": re.compile(r"(?i)(connection refused|connectionreset|network is unreachable|getaddrinfo|econnrefused)"),
        "recommendation": "Vérifier host.docker.internal:1234 depuis le conteneur et que LM Studio écoute sur 0.0.0.0.",
    },
]


def _text_of(ev: Dict[str, Any]) -> str:
    meta = ev.get("metadata") or {}
    parts = [
        str(meta.get("message") or ""),
        str(meta.get("error") or ""),
        str(meta.get("output") or ""),
        str(ev.get("status") or ""),
    ]
    return " ".join(p for p in parts if p)


def classify_text(text: str) -> Optional[Dict[str, str]]:
    for rule in RULES:
        if rule["pattern"].search(text):
            return {
                "code": rule["code"],
                "label": rule["label"],
                "recommendation": rule["recommendation"],
            }
    return None


def analyze(events: List[Dict[str, Any]], max_samples: int = 20) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    for ev in events:
        is_error = (
            ev.get("event_type") in {"API_ERROR", "PIPELINE_ERROR"}
            or ev.get("ok") is False
        )
        if not is_error:
            continue
        text = _text_of(ev)
        klass = classify_text(text)
        if klass is None:
            raw = str((ev.get("metadata") or {}).get("raw_event_type") or "")
            if raw in {"RUN_RESULT", "VALIDATION_RESULT"} or ev.get("event_type") == "PIPELINE_ERROR":
                klass = {
                    "code": "VALIDATION_FAILED",
                    "label": "Exécution terminée en échec (validation)",
                    "recommendation": "Inspecter le run concerné via /api/pipeline/events?session=… ; "
                                      "aucune correction automatique.",
                }
        errors.append({
            "event_id": ev.get("event_id"),
            "timestamp": ev.get("timestamp_iso") or ev.get("timestamp"),
            "event_type": ev.get("event_type"),
            "status": ev.get("status"),
            "source": ev.get("source"),
            "agent": ev.get("agent"),
            "model": ev.get("model"),
            "session_id": ev.get("session_id") or ev.get("run_id"),
            "code": (klass or {}).get("code", "UNCLASSIFIED"),
            "label": (klass or {}).get("label", "Erreur non classée"),
            "recommendation": (klass or {}).get("recommendation"),
            "message": redact_text(text, 500),
        })

    by_code = Counter(e["code"] for e in errors)
    by_source = Counter(e["source"] for e in errors)
    return {
        "total_errors": len(errors),
        "by_code": dict(by_code),
        "by_source": dict(by_source),
        "recommendations": sorted({
            e["recommendation"] for e in errors if e.get("recommendation")
        }),
        "samples": sorted(errors, key=lambda e: e.get("timestamp") or 0, reverse=True)[:max_samples],
        "caveat": "Classification heuristique sur le texte observé ; aucune correction automatique.",
    }
