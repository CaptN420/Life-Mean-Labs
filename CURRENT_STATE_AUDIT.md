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
| Tests de référence | **1 736 passed, 13 skipped, 0 failed** (après P1/P2/P3) |

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
| 11 | Aucune route HTTP pour les packages LM | `FIXED_AND_VERIFIED` | `experiments/packages_api.py` : `GET /api/packages`, `GET /api/packages/inspect`, `POST /api/packages/validate`, `POST /api/packages/import` — sondes live 200 |
| 12 | Aucune UI pour charger un package | `FIXED_AND_VERIFIED` | onglet **Packages** : catalogue, détail + double verdict, boutons Inspecter / Valider / **Importer** |
| 13 | Registres Skills/Tools vides | **`CONFIRMED_BROKEN`** | `/api/extensions/skills` et `/tools` → `total: 0` |
| 14 | `continue_experiment` ne reprend pas | `FIXED_AND_VERIFIED` | checkpoint par tâche ; 3/8 arrêtées → reprise exécute **5** tâches, RAW 3→8, métriques cumulées ; terminée/absente → refus motivé |
| 15 | Aucun timeout moteur | **`CONFIRMED_BROKEN`** | aucune occurrence de `timeout` dans `core/runtime`, `core/workers`, `core/events` |
| 16 | « Concurrence » du scheduler | `NOT_APPLICABLE` (simulation assumée) | ni thread ni asyncio : horloge virtuelle |
| 17 | GPU / inférence locale | `BLOCKED_EXTERNAL` | `torch`, `llama_cpp`, `transformers`, `onnxruntime` absents |
| 18 | Collecteurs Windows (Defender, Event Log) | `BLOCKED_EXTERNAL` | `psutil`, `win32evtlog`, `win32service` absents |
| 19 | Feature Pool à 987/989 non observées | `PARTIAL` | usage observé ≠ validation, statuts inchangés |
| 20 | Pipeline Inspector | `FIXED_AND_VERIFIED` | `a719f12` — 392 151 événements, idempotent, 28 tests |
| 21 | `/api/agents` en dur + création non persistée | `FIXED_AND_VERIFIED` | registre réel (12 agents), toggle vérifié par relecture, doublon → 409 |

### 4bis. Défaut découvert pendant P1 : import qui dupliquait le registre

`PackageManager.import_package()` vérifiait les conflits avec `storage.get_agent(agent_id)`, alors que
`create_agent()` attribue un **UUID**. Le test ne pouvait donc jamais correspondre :

- import #1 → 11 agents ; import #2 du **même** pack → **22 agents**, `success: true`, `conflicts: 0`.

Reproduit sur base temporaire avant correction, puis corrigé :

- détection par **nom** (identité réelle d'un agent dans un pack), insensible à la casse ;
- ré-import → `success: false`, `"Nothing new: 11 item(s) already present"`, 11 conflits, **11 agents** en base ;
- le message d'échec à zéro import ne dit plus « No content imported » quand la vérité est « déjà présent ».

Persistance vérifiée : `LIFE_MEAN_STUDIO_DB=/app/studio_data/life_mean_studio_data.db` + volume nommé
`life_mean_studio_data` (l'image est `read_only: true`, sans volume l'import échouait). Contrôle réel :
11 agents en base, puis `docker compose restart` → **toujours 11**.

### 4ter. Agent Builder : deux faux succès, corrigés

`GET /api/agents` renvoyait **4 templates codés en dur** ; `POST /api/agents` fabriquait un id
(`agent_xxxx`), répondait `status: "created"` et **n'écrivait rien**. L'UI alertait « Agent created ».
Rien n'affichait donc les 11 agents importés.

Corrigé et vérifié sur le conteneur :

```
GET  /api/agents        -> 200 | source: studio_registry | total: 12 | actifs: 12
                              base: /app/studio_data/life_mean_studio_data.db
POST /api/agents/{id}/toggle {enabled:false} -> 200 enabled=False verified=True
                              actifs 12 -> 11, puis retour à 12
POST /api/agents/inconnu/toggle -> 404 agent_not_found
POST /api/agents (doublon)      -> 409 agent_exists
POST /api/agents (nouveau)      -> 200 persisted=True verified=True (UUID réel en base)
```

L'import conserve désormais le `role` du pack (ex. « Transformation ») dans `description` : il était
jeté, ce qui laissait 11 cartes identiques « general ». Réserve honnête : les 11 agents déjà importés
avant cette correction gardent une description vide — aucun rattrapage silencieux n'a été fait.

### 4quater. Reprise réelle (P3) — ce que « Continue » fait maintenant

`continue_experiment` appelait `start_experiment` (nouvelle exécution depuis la tâche 0) et, pour une
expérience terminée, `restart_experiment` en silence. Le bouton « Continue » ne continuait rien.

Désormais chaque tâche terminée écrit **sa preuve RAW puis sa ligne de checkpoint** (dans cet ordre :
on ne saute que ce qui a laissé une trace). Les identifiants de tâches étant des UUID aléatoires, la
reprise s'appuie sur l'**index + empreinte du contenu** (domaine, difficulté, description, vérité
terrain) : si le contenu régénéré diffère, la reprise est **refusée** au lieu de mélanger deux
exécutions.

Mesure réelle (script hors pytest, `LIFE_MEAN_RUNS_DIR` temporaire) :

```
APRÈS ARRÊT (8 tâches prévues, stop après la 3e)
  checkpoint : {'total': 8, 'seed': 42, 'domain': 'math'}
  entrées    : 3   indices: [0, 1, 2]
  lignes RAW : 3
APRÈS CONTINUE
  tâches réexécutées : 5      ← les 3 premières ne sont pas relancées
  entrées checkpoint : 8      indices: [0..7]
  lignes RAW         : 8
  état UI : completed=8 valid=8 pass_rate=1.000
REFUS
  sans checkpoint     : False — « aucune progression enregistrée »
  expérience terminée : False — « déjà terminée (2/2 tâches) »
```

L'API renvoie 409 `resume_refused` avec la raison (avant : 500 générique « Failed to continue »), et
l'UI affiche ce message. Un checkpoint antérieur est **archivé** (`.jsonl.bak`), jamais supprimé.

Mesure réelle en HTTP contre le conteneur (expérience de 4 000 tâches, arrêtée en cours de route) :

```
POST /api/experiments/{id}/stop   -> 200
après stop   : completed=975/4000   checkpoint=976 lignes   RAW=975 lignes
POST /api/experiments/{id}/continue -> 200 {"status": "resumed"}
après reprise: completed=4000/4000  checkpoint=4001 lignes  RAW=4000 lignes
POST continue (2e fois) -> 409 resume_refused
```

Exactement une ligne RAW et une ligne de checkpoint par tâche, aucune tâche exécutée deux fois.

### 4quinquies. Transparence — un test existant a été adapté (sans être affaibli)

La boucle déterministe exécute désormais **tâche par tâche** (`run_task`) au lieu d'un `run_batch` :
c'est la condition d'un checkpoint par tâche. `tests/test_qa_fixes.py::test_runner_loop_sets_valid_counts`
simulait un `run_batch` renvoyant deux résultats ; le simulacre a été déplacé sur `run_task`.

- assertions **conservées** : `tasks_valid == 1`, `tasks_invalid == 1`, `tasks_completed == 2`,
  `pass_rate == 0.5` ;
- assertion **ajoutée** : `run_task.call_count == 2` (une exécution par tâche, aucune reprise).

Aucun seuil abaissé, aucun test supprimé.

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

---

## 6. Observation à ne pas masquer — un test instable

Lors d'un passage complet, `tests/test_dashboard_security.py::…::test_state_changing_with_wrong_token_is_403`
a échoué une fois, puis :

- passe seul (23/23 dans son fichier) ;
- passe dans le lot `dashboard_security + http_smoke + packages_api + experimental_api` (55/55) ;
- passe sur les passages complets ultérieurs : **1717**, **1720**, **1728**, puis **1736 passed, 13 skipped, 0 failed**.

Classé `UNVERIFIED_FLAKE` : non reproduit, cause non identifiée, assertion **non modifiée**. À traiter en
phase 9 (isolation des serveurs in-process) plutôt qu'à être ignoré.
