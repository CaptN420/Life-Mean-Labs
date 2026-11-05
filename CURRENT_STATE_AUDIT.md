# CURRENT STATE AUDIT — 2026-11-05

**Mandat** : correction intégrale, non-régression et validation réelle — phase 0 (« état réel du projet »).
**Méthode** : état Git, image Docker, sondes HTTP réelles contre le serveur démarré, lectures ciblées du code, comparaison avec les rapports existants.
**Aucun code modifié par cet audit. Aucun `git push`.**

---

## 0. Instantané

| Élément | Valeur |
|---|---|
| HEAD | `4779743` fix(R2) — lmpack Studio layout |
| Commits de la session | `f381c35` (P0), `b9602bb` (trig/log), `9b43f45` (README), `a719f12` (L0/L1), `5e66cc0` (R0), `4779743` (R2) |
| Fichiers suivis modifiés | `captn_runtime/captn_experiences.jsonl` (+4 397 lignes de journal runtime), `sandbox/tools/tool-2/spec.json` (1 ligne) |
| Non suivis | sondes de debug (`_*.py`, `_*.js`), `feature_pool_*.json/csv`, `artifacts/`, `Life_mean/results/` (1 Ko) |
| Conteneur | `life_mean_realm-dashboard-1` **Up (healthy)** |
| Image | construite il y a ~1 h, **antérieure à R2** |
| Tests de référence | **1 702 passed, 13 skipped, 0 failed** |

### Constat opérationnel n°1 — l'image Docker ne contient pas le code courant

```
docker exec life_mean_realm-dashboard-1 grep -c PackageFormatError /app/core/packager/__init__.py
→ 0        (la correction R2 est absente de l'image)
```

`docker-compose` copie le code dans l'image (pas de bind mount) : tant que l'image n'est pas reconstruite,
le dashboard sert une révision antérieure. **Toute validation bout-en-bout faite maintenant testerait
l'ancien code.**

---

## 1. Classification des problèmes connus

| # | Problème | État | Preuve |
|---|---|---|---|
| 1 | Runs perdus au redémarrage | `FIXED_AND_VERIFIED` | `f381c35` — run `exp_adb44a31` revu après `docker compose restart` : `rehydrated: true`, 3 tâches |
| 2 | Manifeste sans version moteur/deps/git | `FIXED_AND_VERIFIED` | manifeste live : engine 1.0.0, seed 21, `dependencies.combined_sha256`, `reproducibility_fingerprint` |
| 3 | Designs d'expérience non persistants | `FIXED_AND_VERIFIED` | un fichier atomique par `(id, version, statut)` ; `history()` ; FROZEN non écrasé |
| 4 | Événements et traces absents après restart | `PARTIAL` | assumé et signalé : `events: []`/`traces: []` + note renvoyant au RAW (pas d'invention) |
| 5 | `core/packager` incapable de lire les packs livrés | `FIXED_AND_VERIFIED` | `4779743` — `valid: True`, 11 personas sur les 2 packs (avant : `False`, 0) |
| 6 | Format de pack inconnu accepté en silence | `FIXED_AND_VERIFIED` | `PackageFormatError` explicite + test sur archive bidon |
| 7 | Tâches `sin`/`log` → `None` silencieux | `FIXED_AND_VERIFIED` | `b9602bb` — seed 21 : `pass_rate 0.333 → 1.0` |
| 8 | Jetons `hf_`/`xoxb-`/`AIza`/`glpat-` en clair | `FIXED_AND_VERIFIED` | `a719f12` — 4 motifs + test de régression |
| 9 | **Image Docker obsolète** | `FIXED_AND_VERIFIED` | reconstruite : `grep -c PackageFormatError` dans le conteneur → **5** (avant : 0), conteneur healthy |
| 10 | LM Studio renvoie 401 | `NOT_APPLICABLE` — artefact de sonde | voir §2bis : l'appel réel aboutit avec le token du `.env` |
| 11 | **Aucune route HTTP pour les packages LM** | **`CONFIRMED_BROKEN`** | `/api/packages`, `/api/lmpack`, `/api/workflows` → 404 |
| 12 | **Aucune UI pour charger un package** | **`CONFIRMED_BROKEN`** | `dashboard.html` : **0** occurrence de « package » |
| 13 | Registres Skills/Tools vides | **`CONFIRMED_BROKEN`** | `/api/extensions/skills` et `/tools` → `total: 0` |
| 14 | `continue_experiment` ne reprend pas | **`CONFIRMED_BROKEN`** (statique) | relance `start_experiment`/`restart_experiment`, aucun curseur de reprise |
| 15 | Aucun timeout moteur | **`CONFIRMED_BROKEN`** | aucune occurrence de `timeout` dans `core/runtime`, `core/workers`, `core/events` |
| 16 | « Concurrence » du scheduler | `NOT_APPLICABLE` (simulation assumée) | ni thread ni asyncio : horloge virtuelle |
| 17 | GPU / inférence locale | `BLOCKED_EXTERNAL` | `torch`, `llama_cpp`, `transformers`, `onnxruntime` absents |
| 18 | Collecteurs Windows (Defender, Event Log) | `BLOCKED_EXTERNAL` | `psutil`, `win32evtlog`, `win32service` absents |
| 19 | Feature Pool à 987/989 non observées | `PARTIAL` | usage observé ≠ validation, statuts inchangés |
| 20 | Pipeline Inspector | `FIXED_AND_VERIFIED` | `a719f12` — 392 151 événements, idempotent, 28 tests |

---

## 2. Sondes HTTP réelles (serveur démarré)

| Route | Code | Charge utile |
|---|---|---|
| `/api/experiments` | 200 | 813 o (registre réel) |
| `/api/training/runs` | 200 | `{"runs": [], "total": 0}` — route fonctionnelle, aucune exécution |
| `/api/models` | 200 | `{"models": [], "total": 0}` — registre vide |
| `/api/agents` | 200 | 439 o |
| `/api/role-templates` | 200 | 3 999 o |
| `/api/experimental/capabilities` | 200 | 2 374 o (exécuteurs + `connected`) |
| `/api/experimental/designs` | 200 | 15 o (`[]`) |
| `POST /api/experimental/harness/start` | **400** `missing_executor` | validation réelle d'entrée — pas de faux `200` |
| `/api/extensions/skills` · `/tools` | 200 | `total: 0` — registres vides |
| `/api/pipeline/stats` | 200 | 664 o |
| `/api/sentinel/status` | 200 | `enabled: true`, `llm_available: false` |
| `/api/settings` | 200 | 18 608 o (clé OpenRouter configurée : `true`) |
| `/api/packages` · `/api/workflows` · `/api/lmpack` | **404** | **absentes** |

Aucune route ne renvoie `200` avec un contenu mensonger : `harness/start` refuse explicitement une
requête incomplète, et les registres vides le disent (`total: 0`) au lieu d'inventer des entrées.

---

## 3. Providers et modèles

### 2bis. Correction d'un constat de cet audit — LM Studio fonctionne

Le §3 initial classait LM Studio en `CONFIRMED_BROKEN` sur la base d'un `401`. **Ce constat était faux** :
il provenait d'une sonde lancée **depuis l'hôte**, sans en-tête d'authentification, sur un nom
(`host.docker.internal`) qui ne résout que depuis le conteneur.

Vérification faite dans l'environnement réel de l'application (`.env` chargé par `env_file`) :

```
GET  {LIFE_MEAN_LLM_BASE_URL}/models   →  HTTP 200, 29 modèles
POST {…}/chat/completions  model=qwen3.5-2b  →  HTTP 200 en 6.59 s
    model renvoyé : qwen3.5-2b   usage : 24 tokens (8 de raisonnement)
GET /api/settings → provider_models[lm_studio].key_configured = true, 26+ modèles
```

Le backend local est donc **opérationnel et authentifié**. Réserve honnête : le modèle `qwen3.5-2b`
consomme des tokens de raisonnement, donc un `max_tokens` trop court renvoie un contenu vide — ce n'est
pas une panne mais un paramétrage à surveiller côté appels.

### 3. Providers déclarés

| Élément | Constat |
|---|---|
| Providers déclarés | `lm_studio`, `openrouter` |
| Clé OpenRouter | configurée (`openrouter_key_configured: true`) |
| Modèles disponibles | liste peuplée (`available_models`, 10+ entrées) |
| LM Studio | **opérationnel** — 29 modèles servis, complétion réelle en 6.59 s (§2bis) |
| Provider par défaut | `general.provider: null` — aucun provider sélectionné explicitement |

**Aucune intervention nécessaire** : le `.env` contient déjà `LIFE_MEAN_LLM_BASE_URL`,
`LIFE_MEAN_LLM_API_KEY` et `OPENROUTER_API_KEY`, et `docker-compose` les injecte via `env_file`.
Le `401` observé venait d'une sonde hors conteneur (voir §2bis) — pas d'une configuration manquante.

---

## 4. Priorisation (phases suivantes)

| Priorité | Problème | Phase |
|---|---|---|
| **P0** | Image Docker obsolète (toute validation porte sur du vieux code) | 8 |
| **P1** | Aucune route/UI de chargement de package LM | 3 / 4 / 8 |
| **P1** | LM Studio 401 (backend indisponible) | 5 |
| **P1** | Événements/traces non persistés (décision à trancher, sans invention) | 1 |
| **P2** | `continue` qui ne reprend pas | 1 / 6 |
| **P2** | Aucun timeout moteur | 6 |
| **P2** | Registres Skills/Tools vides | 7 |
| **P3** | Feature Pool 987/989 non observées | 7 |
| **Externe** | GPU, collecteurs Windows | 6 / hors périmètre |

---

## 5. Ce que cet audit ne fait pas

- Il ne re-corrige aucun des problèmes déjà marqués `FIXED_AND_VERIFIED` (règle explicite du mandat).
- Il ne présente pas `total: 0` comme une panne : ce sont des registres réellement vides.
- Il ne touche ni aux packages, ni aux datasets, ni aux historiques.
- Il n'exécute aucun `git push` : les commits restent locaux jusqu'à autorisation explicite.
