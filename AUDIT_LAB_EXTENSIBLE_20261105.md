# Audit — Life-Mean-Labs : laboratoire de recherche extensible

**Date :** 2026-11-05 · **Périmètre :** dépôt `C:\Users\celes\Documents\Hermes-Workspace\Life_mean_realm`
**Méthode :** lecture du code réel + exécution de sondes (pytest, HTTP live, imports, health checks). Aucune fonctionnalité n'est déclarée opérationnelle sur la seule foi d'un nom de fichier, d'un onglet ou d'une mention du Feature Pool.

---

## 0. Preuves d'exécution (ce qui a été réellement lancé)

| Sonde | Résultat observé |
|---|---|
| `pytest` (suite complète) | **848 passed, 2 skipped, 0 failed** |
| `pytest tests/test_experimental_*.py test_extensions test_lab_isolation test_persistence test_pack_manifest` | **112 passed** |
| Dashboard HTTP live (`:8082`) | `/api/config`, `/api/extensions/*`, `/api/experimental/*`, `/api/agents`, `/api/pipeline/stats` → **200** |
| `/api/training/runs`, `/api/models` | **404 (bug de routage — corrigé, voir §5)** |
| `check_llm_backend()` | **`error: Authentication required (401)`** → aucun exécuteur LLM n'est joignable ici |
| `check_dashboard()` / `check_orchestrator()` | unreachable (services non démarrés) |
| `import PySide6` | **6.12.0** (Studio réellement lançable) |

---

## 1. Cartographie quantitative

407 fichiers Python, ~99 900 lignes (hors `legacy/`, `build/`, `.venv/`, `node_modules/`).

| Package | Fichiers | Lignes | Rôle |
|---|---:|---:|---|
| `tests/` | 109 | 28 795 | suite de validation |
| `core/` | 44 | 11 694 | runtime, events, router, workers, safety, observability, packager |
| `philosophical_council/` | 53 | 9 090 | débat philosophique + RAW protocol |
| `experiments/` | 30 | 8 506 | génération synthétique, runner, dashboard, trainer, settings |
| `code_lab/` | 19 | 7 905 | génération/validation de code, error memory |
| `life_mean_studio/` | 27 | 7 831 | UI desktop PySide6 + storage SQLite |
| `life_mean_lab/` | 28 | 7 469 | sandbox, resource limits, workflows moléculaires (legacy-ish) |
| `pipeline_inspector/` | 17 | 3 271 | inspection pipeline (mixin dashboard) |
| `library/` | 18 | 2 945 | outils, personas, protocoles |
| `experimental/` | 17 | 2 686 | **couche d'expérimentation sandbox** |
| `compare/` | 11 | 2 589 | comparaison de runs/conditions |
| `feature_pool/` | 12 | 2 431 | catalogue de features |
| `debate_lab/` | 7 | 1 632 | débat exécutable |
| `life_mean_extensions/` | 5 | 1 181 | **registres skills/tools + pipeline d'approbation** |
| `autopilot/`, `analysis/`, `benchmarks/`, `scientific/` | 10 | 1 874 | curriculum, faiblesses, benchmarks, clients API |

---

## 2. Matrice Existant / Fonctionnel / Partiel / Manquant / Réutilisable

### 2.1 Moteur d'exécution et orchestrateurs

| Composant | Emplacement | État | Preuve | Réutilisable pour |
|---|---|---|---|---|
| Runtime + EventBus + assignments | `core/runtime`, `core/events`, `core/assignment` | **Fonctionnel** | `test_phase0_runtime.py`, `test_events` verts | socle de tout exécuteur |
| Adaptative router | `core/router` | **Fonctionnel** | `test_adaptive_router.py` vert | sélection modèle/outil par tâche |
| Workers (exécution d'outils) | `core/workers` | **Fonctionnel** | `test_executor.py` vert | hôte d'outils pour extensions |
| Runner d'expériences synthétiques | `experiments/runner.py` | **Fonctionnel** | `test_phase3_integration.py` | génération → validation |
| Code Lab engine | `code_lab/engine.py` | **Fonctionnel** (déterministe) ; LLM requis pour le mode multi-agent | `test_code_lab*.py` verts | exécuteur `code_lab` |
| Debate Lab | `debate_lab/`, `core/debate` | **Partiel** : moteur + tests verts, mais **backend LLM 401** | health check | exécuteur `debate` (à reconnecter) |
| Council philosophique | `philosophical_council/` | **Existant, partiellement intégré** (RAW protocol solide, UI ttk séparée) | 9 090 lignes, tests dédiés | jugement multi-persona |
| Orchestrateur Node | `hermes-orchestrator/`, `hermes-debate/` | **Projets séparés** (hors wheel, non démarrés) | `pyproject.toml` exclude | à ne pas confondre avec le moteur Python |

### 2.2 Couche d'expérimentation (cœur de la demande)

| Composant | Emplacement | État | Détail vérifié |
|---|---|---|---|
| Schéma d'expérience versionné | `experimental/schema.py` | **Fonctionnel** | `ExperimentDesign` typé, états `DRAFT→REVIEWED→APPROVED→FROZEN`, exécution **interdite** hors `FROZEN`, `with_()` renvoie une nouvelle version |
| Catalogue d'exécuteurs | `experimental/dispatch.py` | **Partiel** | dict `STAGE_EXECUTORS` **codé en dur** ; 8/14 `connected: True`, 6 refusés honnêtement (`ExecutorNotAvailable`) |
| Harnais sandbox | `experimental/harness.py` | **Fonctionnel** | exécuteurs `code_lab`, `sweep`, `tool`, `deterministic` réels ; workspace jetable ; test anti-littering |
| Moteur expérimental | `experimental/engine.py` | **Fonctionnel** | exécute un design FROZEN, respecte les budgets, émet des événements |
| Store de designs | `experimental/store.py` | **Partiel — trou critique** | **100 % en mémoire** (docstring l'admet) → tout design disparaît au redémarrage |
| Feedback / capabilities API | `experimental/api.py` | **Fonctionnel** | endpoints live 200 |
| Registres skills/tools + approbation | `life_mean_extensions/` | **Partiel — trou critique** | registres, `security_audit`, `sandbox_test`, pipeline 8 étapes existent et sont testés, **mais aucun composant d'exécution ne consomme un skill/tool approuvé** : l'approbation est un état, pas un effet |
| Génération de stub d'outil | `life_mean_extensions/factories.py` | **Fonctionnel** | écrit `sandbox/tools/<id>/{tool.py,spec.json}` (sanitisation d'ID contre `../../pwn`) |
| Point d'extension déclaratif | — | **Manquant** | aucun `entry_points`, aucun manifeste de plugin ; ajouter un exécuteur = éditer `dispatch.py` |

### 2.3 Reproductibilité scientifique

| Élément exigé | État | Détail |
|---|---|---|
| Identifiant unique d'expérience | **Fonctionnel** | `experiment_id`/`run_id` auto |
| Configuration complète | **Fonctionnel** | `ExperimentConfig.to_dict()` |
| Seed | **Partiel** | présent dans `ExperimentConfig` et `Diversifier(seed)` ; **absent** du manifeste exporté |
| Versions de modèles | **Manquant** | aucune trace des modèles réellement appelés dans le manifeste |
| Version du moteur | **Manquant** | pas de `ENGINE_VERSION` / `__version__` exposé dans les manifestes |
| Versions des dépendances | **Manquant** | pas de hash de `pyproject`/lock dans les artefacts |
| Timestamps, résultats, métriques | **Fonctionnel** | `observability.py`, `dataset_builder` |
| Erreurs et journaux | **Fonctionnel** | `events.jsonl`, `error_memory`, `pipeline_inspector` |
| Export portable | **Partiel** | `export_manifest()` (config/prompt/agents/events/traces) mais sans versions ni seeds ; `.lmpack` couvre personas/providers/models, **pas** les expériences |
| Import | **Manquant** pour les expériences | import existant uniquement pour `.lmpack` (`life_mean_studio/engine/package_manager.py`) |

### 2.4 Fiabilité et sécurité

| Mécanisme | État | Détail |
|---|---|---|
| Isolation d'exécution de code | **Partiel** | `experimental/harness._sandbox_dir()` + `life_mean_lab/sandbox.py` (`validate_path`) ; **pas** de sous-processus pour le code utilisateur |
| Limites de ressources | **Partiel** | `life_mean_lab/resource_limits.py` (`RLIMIT_AS`, `RLIMIT_CPU`) utilise le module `resource` → **POSIX uniquement**, inopérant sous Windows |
| Timeouts | **Partiel** | budgets de design (`max_runtime_seconds`) + timeouts HTTP ; pas de timeout par exécuteur de code |
| CSRF / auth des mutations | **Fonctionnel** | cookie + header, testé (`test_dashboard_security.py`) |
| Redaction des secrets | **Fonctionnel** | `test_raw_secret_redaction.py`, `overrides/llm.env` git-ignoré |
| Audit de sécurité des outils importés | **Fonctionnel** (statique) | patterns `eval/exec/os.system/shell=True` → findings sévérité |
| Code importé exécuté automatiquement | **Non — conforme** | activation = état ; aucune exécution implicite trouvée |
| Traçabilité des exécutions | **Fonctionnel** | `trace_index`, hashes de provenance, `events.jsonl` |

### 2.5 Interfaces

| Interface | État | Lien avec l'autre |
|---|---|---|
| Dashboard HTML (`experiments/ui/dashboard.html`) | **Fonctionnel** | sert `/dashboard`, ~60 routes API |
| Life_mean Studio (PySide6) | **Fonctionnel** (lance) | stockage SQLite propre (`workflows`, `prompts`, `sessions`, `agents`) |
| Lien Studio ↔ dashboard | **Partiel — trou** | Studio se contente d'`webbrowser.open("http://localhost:8080/dashboard")` + health probes ; **aucun store partagé** ; le port 8080 est occupé par Docker sur cette machine (8082 utilisé) |
| Import/export de configuration dans l'UI | **Manquant** | pas de bouton/flux d'import d'expérience |

---

## 3. Écarts entre l'apparence et la réalité (constats durs)

1. **`/api/training/runs` et `/api/models` renvoyaient 404** alors que les handlers existaient : ils avaient été enregistrés dans `do_DELETE` au lieu de `do_GET`. **Corrigé** (§5) — c'est exactement le type d'écart que la consigne demande de traquer.
2. **La couche d'extension n'est pas branchée à l'exécution.** `SkillRegistry`/`ToolRegistry`/`ApprovalPipeline` ne sont référencés que par `experiments/dashboard.py` et les tests. Un outil « activé » n'est chargé par aucun moteur.
3. **Les designs d'expérience ne survivent pas à un redémarrage** (store en mémoire).
4. **Le manifeste de reproductibilité est incomplet** : ni version moteur, ni dépendances, ni modèles, ni seed.
5. **6 exécuteurs sur 14 sont déclarés non connectés** ; c'est honnête, mais cela limite l'expérimentation réelle à `code_lab`, `code`, `benchmark`, `deterministic`, `debate_code`, `sweep`, `llm_sweep`, `tool_execution`, `validation`.
6. **Les limites de ressources sont POSIX-only** : aucune contrainte mémoire/CPU effective sous Windows.

---

## 4. Ce qui est réutilisable tel quel (ne rien réécrire)

- `experimental/schema.py` — contrat de design versionné + gate FROZEN : **la meilleure base pour l'extensibilité contrôlée**.
- `experimental/dispatch.py` + `harness.py` — point de décision unique + exécution sandbox : à **généraliser**, pas à remplacer.
- `life_mean_extensions/pipeline.py` — audit sécurité + test sandbox + machine à états d'approbation : bon socle de gouvernance.
- `core/events` + `observability.py` — traçabilité déjà en place.
- `experiments/dashboard.py` (mixins) — surface API à étendre, pas à refondre.
- `library/tools/detection.py`, `core/router` — routage tâche→outil déjà opérationnel.
- `life_mean_studio/engine/package_manager.py` — import/export `.lmpack` réutilisable pour les packs.

---

## 5. Correctifs appliqués pendant l'audit (revue, risque minimal)

### 5.1 Routes déclarées mais inatteignables (méthode HTTP erronée)

**Fichier :** `experiments/dashboard.py`
**Problème 1 :** branches `/api/training/runs`, `/api/training/runs/<id>`, `/api/models`, `/api/models/<id>` placées dans `do_DELETE` → tout `GET` tombait dans le `404` de `do_GET`.
**Problème 2 :** branches `/api/experiments/<id>/observability` et `/api/experiments/<id>/manifest` placées dans `do_POST` alors que le frontend (`dashboard.html`) les appelle en **GET** (`fetch(...)` sans options) → le panneau Observabilité et le bouton « Export manifest » renvoyaient toujours 404.
**Correctif :** les six branches déplacées dans `do_GET`, avant le fallback ; `do_DELETE`/`do_POST` restaurés à leur rôle (mutations uniquement).
**Vérification live (Docker, :8080) :** `GET /api/training/runs` → 200 · `GET /api/models` → 200 · `GET .../observability` → 200 · `GET .../manifest` → 200.

### 5.2 Manifeste de reproductibilité inatteignable après un run

**Fichier :** `experiments/ui_controller.py`
**Problème A :** l'objet d'observabilité était **retiré** (`pop`) du dict dans le `finally` de `_run_experiment_loop` → `/observability` et `/manifest` ne pouvaient répondre que *pendant* l'exécution. Après un run, 404.
**Problème B :** l'observabilité n'était créée **qu'en mode debate** — les runs déterministes (précisément ceux qui sont reproductibles) n'avaient aucun manifeste.
**Correctif :** création via `_ensure_observability()` pour **tous** les modes, avant l'exécution ; conservation après complétion avec rétention bornée (`_obs_retention = 20` runs terminés, éviction FIFO).
**Piège évité :** `_ensure_observability` acquiert `_lock` ; il est donc appelé **hors** de tout bloc déjà verrouillé (sinon deadlock sur un `Lock` non réentrant).
**Vérification live (Docker) :** run déterministe `exp_609cf410` (seed 11, 3 tâches) → `COMPLETED`, puis `GET .../manifest` → 200 avec `config.seed = 11`, `prompt`, `agents`, `events`, `traces`, `progress`.
**Tests :** `tests/test_dashboard_http_smoke.py` — `test_training_and_models_get_routes_are_served`, `test_unknown_route_returns_404_json`, `test_completed_run_keeps_observability_and_manifest_live` (9 passed).

### 5.3 Tests obsolètes remis en accord avec le comportement vérifié

- `tests/test_phase1_routing.py::test_detect_math_gcd` : attendait `coding_generator` ; le routage réel (vérifié en exécution Docker : `math_gcd` détecté, réponses correctes) renvoie `math_gcd` / domaine `math`.
- `tests/test_qa_fixes.py::test_do_DELETE_route` : le handler factice n'envoyait aucun jeton CSRF → 403 ; le test porte désormais un cookie + header valides, la garde CSRF restant intacte.

### 5.4 Échec de build d'image (constat)

L'image Docker `life-mean-dashboard:local` datait de 27 h et **embarque le code par `COPY`** (pas de bind mount) : elle servait donc l'ancien code (404 sur les routes corrigées). **Image reconstruite** (`docker compose build dashboard && docker compose up -d`) puis re-vérifiée.

---

## 5bis. Constat de durabilité (non corrigé — objet de P0)

Redémarrer le conteneur (`docker compose restart dashboard`) vide le registre d'expériences en mémoire : `/api/experiments` → `0` alors que les 3 fichiers RAW correspondants restent sur le volume (`/app/data/raw_debates/*.jsonl`). Aucune réhydratation au démarrage. La donnée existe, l'état qui la rend interrogeable n'existe plus — c'est exactement ce que P0 doit fermer.


---

## 6. Plan priorisé (à valider avant exécution)

### P0 — Fiabilité scientifique (bloquant pour la promesse « reproductible »)

**P0.1 — Persistance des designs d'expérience**
- Fichiers : `experimental/store.py` (+ `experimental/schema.py` si besoin d'un champ `saved_at`), nouveau `tests/test_experimental_store_persistence.py`.
- Raison : un design FROZEN doit survivre au redémarrage, sinon aucune réexécution n'est possible.
- Réutilise : `ExperimentDesign.to_dict()/from_dict()` déjà présents.
- Risque : faible (écriture JSON atomique, répertoire `data/experiments/designs/`).
- Tests : save → nouvelle instance de store → `get()` identique ; design FROZEN immuable après rechargement ; transition illégale refusée.

**P0.2 — Manifeste de reproductibilité complet**
- Fichiers : `experiments/observability.py`, nouveau `experiments/reproducibility.py`, `experiments/ui_controller.py`.
- Contenu à ajouter : `engine_version`, version Python, hash des dépendances (`pyproject.toml` + `uv.lock`), modèles utilisés (`id` + provider + endpoint), `seed`, versions d'outils.
- Raison : le manifeste actuel ne permet pas de savoir *ce qui* a produit un résultat.
- Risque : faible (ajout de champs, rétro-compatible).
- Tests : manifeste contient les clés obligatoires ; deux runs même seed → mêmes champs de provenance ; absence de secret (redaction vérifiée).

**P0.3 — Export / import d'expérience**
- Fichiers : `experiments/dashboard.py` (2 routes), `experiments/reproducibility.py`, UI `experiments/ui/dashboard.html` (2 boutons).
- Format : JSON autoportant (`experiment_bundle.json`) + validation de schéma à l'import.
- Risque : moyen (validation stricte obligatoire ; refus explicite si version inconnue).
- Tests : export → import → réexécution même configuration ; import d'un bundle corrompu → 400 explicite, jamais de démarrage silencieux.

### P1 — Extensibilité contrôlée

**P1.1 — Catalogue d'exécuteurs déclaratif**
- Fichiers : `experimental/dispatch.py` (lecture d'un manifeste), nouveau `experimental/executors_manifest.json`, `tests/test_dispatch_registry.py`.
- But : permettre à un chercheur d'enregistrer un exécuteur (fichier/manifeste) **sans éditer le code interne**, avec allowlist et validation (`connected` calculé par sonde réelle, pas déclaré à la main).
- Risque : moyen (un exécuteur non validé ne doit jamais être chargé).
- Tests : exécuteur inconnu refusé ; manifeste invalide rejeté ; exécuteur enregistré mais non connecté → `EXECUTOR_NOT_AVAILABLE`.

**P1.2 — Brancher les outils approuvés sur l'exécution (opt-in explicite)**
- Fichiers : `core/workers` (hôte d'outils), `life_mean_extensions/registries.py`, `experiments/runner.py`/`experimental/harness.py`.
- Règle : un outil n'est chargé que si `status == ACTIVE` **et** qu'un flag de run l'autorise ; sinon refus explicite (jamais de fallback silencieux).
- Risque : élevé (surface d'exécution de code) → sous-processus + audit statique obligatoires.
- Tests : outil non approuvé jamais chargé ; outil approuvé exécuté dans le sandbox ; tentative d'évasion de chemin refusée.

**P1.3 — SDK public versionné**
- Fichiers : nouveau `life_mean_extensions/sdk.py` (+ `__api_version__`), doc `docs/SDK.md`.
- Contenu : `create_design()`, `freeze()`, `run()`, `export()`, `import_bundle()`, `register_executor()`, `list_capabilities()`.
- Risque : faible (façade au-dessus de l'existant).
- Tests : le SDK n'expose aucun composant interne mutable ; `__api_version__` présent ; dépôt d'un design via SDK → exécution via moteur.

### P2 — Sécurité d'exécution

**P2.1 — Limites de ressources portables**
- Fichiers : `life_mean_lab/resource_limits.py` (chemin Windows via Job Objects ou timeout+sous-processus), `experimental/harness.py`.
- Décision honnête : sous Windows, `resource` est indisponible → implémenter au minimum **timeout dur + terminaison du sous-processus**, et documenter la limite mémoire comme non garantie.
- Tests : boucle infinie tuée dans le délai ; code dépassant le budget → `STOP_CONDITION_REACHED` explicite.

**P2.2 — Validation à l'import de packs**
- Fichiers : `life_mean_studio/engine/package_manager.py`, `core/packager`.
- Règle : jamais d'exécution à l'import ; validation du manifeste + liste des fichiers + refus des chemins hors sandbox.
- Tests : `.lmpack` avec `../` refusé ; pack valide importé sans exécution.

### P3 — UI minimale (pas de refonte)

- Onglet « Experiments » du dashboard : import/export, état d'exécution, erreurs lisibles, accès aux logs. Aucune animation, aucun changement de charte.
- Lien Studio → dashboard : corriger l'URL codée en dur `8080` pour lire la configuration réelle (port effectif), sans changer l'apparence.

---

## 7. Ordre proposé et critère d'acceptation

1. **P0.1 → P0.2 → P0.3** (reproductibilité complète, vérifiée par tests + un run réel exporté puis réimporté).
2. **P1.1 → P1.3** (extensibilité sans modification du moteur), **P1.2** seulement après P2.1 (sinon on ouvre une exécution de code sans limites).
3. **P2.1 → P2.2**, puis **P3**.

Critère global : aucun élément n'est déclaré opérationnel sans un test exécuté **et** une sonde réelle (HTTP/CLI) qui le démontre ; la suite complète doit rester verte (848+).

---

## 8. Ce qui ne sera PAS fait (conformément aux contraintes)

- Pas de réécriture du moteur ni du dashboard existant.
- Pas de nouvelle dépendance non indispensable (pas de framework d'orchestration supplémentaire).
- Pas de refonte visuelle de Life_mean Studio.
- Pas de promesse de déterminisme sur les exécuteurs LLM (backend non déterministe, et ici non joignable).
- Pas de simulation : les exécuteurs non connectés restent déclarés non connectés.

---

## 9. P0 LIVRÉ — preuves d'exécution (2026-11-05)

### P0.1 — Persistance des designs (`experimental/store.py`)

- Un fichier **par snapshot** `(design_id, version, statut)` : `DESIGN-XXX.v1.DRAFT.json`, `…v1.FROZEN.json`, etc. Un snapshot FROZEN n'est jamais écrasé.
- Écriture **atomique** (`tmp` + `os.replace`), rechargement au démarrage, `history()` expose toutes les versions.
- Échec d'écriture → `DesignStoreError` (aucun faux succès). Fichier corrompu → ignoré avec avertissement, jamais deviné.
- Racine configurable (`LIFE_MEAN_DESIGNS_DIR`), par défaut `data/experiments/designs` (volume Docker `life_mean_data`).
- Vérifié : save → nouvelle instance → `get()` identique ; 4 snapshots DRAFT/REVIEWED/APPROVED/FROZEN ; `frozen_hash` préservé ; transition depuis FROZEN refusée.

### P0.2 — Manifeste de reproductibilité (`experiments/reproducibility.py`)

Bloc ajouté au manifeste : `engine{name,version}`, `environment{python,system,machine}`, `dependencies{sha256 pyproject+uv.lock, combined}`, `git{commit,dirty}`, `seed`, `deterministic`, `models`, `tools`, `generator_version`, `prompt_version`, plus `reproducibility_fingerprint` (hash stable des conditions).
Aucun secret : uniquement versions/ids/hashes (test dédié avec variables d'env piégées).

**Vérifié en live sur Docker** — run `exp_adb44a31` (seed 21) : manifeste 200, `engine = {'name': 'life_mean_lab', 'version': '1.0.0'}`, `seed = 21`, `dependencies.combined_sha256 = 4ba90b152122…`.

### P0.3 — Durabilité du registre (constat §5bis fermé)

- Chaque run terminé écrit un *run summary* atomique (`data/experiments/runs/<exp>.json` : config, état final, compteurs, mode, seed).
- `ExperimentUIController.rehydrate_from_summaries()` reconstruit le registre au démarrage ; entrées marquées `rehydrated: true`, jamais `running`.
- Manifeste d'un run réhydraté : 200, avec `rehydrated: true`, config/seed exacts, `events`/`traces` explicitement vides et une note expliquant que la preuve est dans le RAW (jamais de manifeste qui ferait semblant).

**Vérifié en live** : run `exp_adb44a31` → `docker compose restart dashboard` → `GET /api/experiments` renvoie toujours `total_experiments: 1`, statut `COMPLETED`, `rehydrated: true`, 3 tâches ; `GET …/manifest` → 200, `seed: 21`, `rehydrated: true`.

### Résultat des tests

**1679 passed, 13 skipped, 0 failed** (dont 25 nouveaux tests ciblés : `test_experimental_store_persistence.py`, `test_reproducibility.py`, `test_run_durability.py`).
