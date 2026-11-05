# RESEARCH READINESS AUDIT — 2026-11-05

**Projet** : `Life_mean_realm` / Life-Mean-Labs
**Portée** : phase 0 du cahier des charges « Research Readiness & Product Validation »
**Méthode** : inspection du code réel et **exécution** (imports, tests, chargement des packages, appels HTTP).
**Aucun fichier de code modifié par cet audit.**

## Verdict global : `PARTIAL`

Le noyau scientifique (Pipeline → Worker, expériences, provenance, validation déterministe) fonctionne et
est traçable, mesuré sur 392 151 événements réels et 1 694 tests. Deux défauts sont confirmés sur les
packages LM. **Trois capacités citées par le cahier des charges n'existent pas dans le code** (Skills,
Evolve, Émulation) et ne doivent pas être annoncées comme opérationnelles.

---

## 1. Composants

| Composant | Classe | Preuve exécutée | Chemin |
|---|---|---|---|
| **Pipeline → Worker** | `OPERATIONAL` | `Worker`, `BaseWorker`, `DeterministicWorker` importent ; chaîne exercée à chaque run ; 59 tests collectés sur `worker`/`compression` | `core/runtime/worker.py`, `core/workers/tool.py` |
| **Orchestrateur / moteur d'exécution** | `OPERATIONAL` | `experiments.runner.ExperimentRunner.run_task` exécuté ; 392 151 événements dont 43 407 `ROUTING_DECISION` | `experiments/runner.py` |
| **Génération de données synthétiques** | `OPERATIONAL` | runs réels `COMPLETED`, `pass_rate` mesuré (0.333 → 1.0 après correction d'un défaut réel) | `experiments/generation/` |
| **Provenance & validation** | `OPERATIONAL` | manifeste reproductible servi en 200 (engine 1.0.0, seed, sha256 des deps, git) ; runs survivants au restart | `experiments/reproducibility.py`, `experimental/store.py` |
| **Model Router / providers** | `OPERATIONAL` | `core.assignment.router` importe ; `core.providers` + `captn_runtime.captn.providers` importent | `core/assignment/`, `core/providers/` |
| **Agent Builder** | `OPERATIONAL` | `life_mean_studio.engine.agent_manager` importe ; `/api/agents` GET+POST ; table `agents` en base | `life_mean_studio/engine/agent_manager.py` |
| **Workflow Builder** | `PARTIAL` | `workflows/manager.py` importe + tests, **aucune route HTTP dédiée** | `life_mean_studio/workflows/manager.py` |
| **Packages LM — lecture** | `PARTIAL` | `life_mean_studio.engine.package_manager` lit les 2 packs livrés : 11 agents, 1 workflow, 0 erreur | `life_mean_studio/engine/package_manager.py` |
| **Packages LM — `core/packager`** | **`BROKEN`** | les 2 packs livrés sont déclarés **invalides** (`persona_count: 0`) — voir D1 | `core/packager/__init__.py` |
| **Compression de contexte** | `PARTIAL` | 5 modules + `adaptive_manager` (sélection adaptative, budget, canary) ; tests `tests/compression_validation/` ; **aucun benchmark comparatif mesuré** | `code_lab/compression/` |
| **Feature Pool** | `PARTIAL` | 989 features chargées, **987 non observées**, intégration `NOT_STARTED` | `feature_pool/` |
| **Pipeline Inspector** | `OPERATIONAL` | 15 modules, 28 tests, 11 routes, 392 151 événements ingérés (idempotent) | `pipeline_inspector/` |
| **Life-Mean Studio** | `PARTIAL` | moteurs et base présents ; interface **non lancée** dans cette session | `life_mean_studio/` |
| **Sentinel** | `PARTIAL` | 31 tests passent, 4 routes ; `llm_available: false` en live ; aucun collecteur OS | `core/safety/sentinel*.py` |
| **Skills** | `PLANNED` | **aucun module hors `legacy/MIA-LABS-main/SKILL.md`** | — |
| **Evolve** | `PLANNED` | **aucune fonction/classe `evolve` dans le code actif** | — |
| **Émulation des expériences** | `PLANNED` | **aucun module d'émulation** ; seul un stub LLM de test (`tests/_debate_stub_llm.py`) | — |
| **Télémétrie** | `PLANNED` | aucun module de ce nom ; l'observabilité passe par Event Bus + Pipeline Inspector | — |

---

## 2. Défauts confirmés

### D1 — `core/packager` déclare invalides des packs valides

```
LLMPackager.from_package('lmpack/ALCHEMY_SCIENCE_experimental.lmpack')
  → validate() = {'valid': False, 'errors': ['At least one persona is required'],
                  'persona_count': 0, 'provider_count': 0, 'model_count': 0}
```

Or le même fichier contient **11 agents** :

```
manifest.json : {name: ALCHEMY_SCIENCE, version: 0.1.0, format_version: 1.0,
                 agents: [11 noms], workflows: ['scientific_council']}
agents/paracelsus.json : {id, name, persona, role, provider, system_prompt, config}
```

Cause : `from_package` ne lit que `personas/personas.json`, `providers/providers.json`,
`models/models.json`. Le format réellement livré (et écrit par Studio) est `agents/<id>.json`.
La lecture échoue silencieusement (`except KeyError: pass`) → 0 persona → `valid: False`.

### D2 — Deux implémentations de packages, formats incompatibles

| Implémentation | Format lu/écrit | État |
|---|---|---|
| `core/packager` | `personas/personas.json` + `providers/` + `models/` | incompatible avec les packs livrés |
| `life_mean_studio/engine/package_manager.py` | `manifest.json` + `agents/<id>.json` + workflows | lit les 2 packs, 0 erreur, `_strip_secrets` à l'export |

Deux gestionnaires pour un même concept, dont un seul parle le format du dépôt. C'est exactement le
« no duplication of existing components » que le cahier des charges interdit.

**Preuve que la capacité existe malgré tout** :

```
PackageManager(storage=None).get_package_info(...)
  → PackageInfo(name='ALCHEMY_SCIENCE', format_version='1.0', agents_count=11,
                workflows_count=1, errors=[])
```

### D3 — L'`except KeyError: pass` masque l'incompatibilité

Le chargement ne signale rien : il retourne un packager vide qui échoue *plus tard*, à la validation.
Un lecteur honnête doit dire « format non reconnu », pas « pack sans personas ».

---

## 3. Blocages d'environnement (à documenter, pas à contourner)

| Blocage | Constat | Impact |
|---|---|---|
| **Aucun moteur d'inférence local** | `torch` MISSING · `llama_cpp` MISSING · `transformers` MISSING · `onnxruntime` MISSING | Phase 5 : les profils `SINGLE_GPU`/`MULTI_GPU` ne sont **pas** testables ici. Seuls `CPU_ONLY` (outils déterministes) et `REMOTE_PROVIDER` (LM Studio / OpenRouter via HTTP) le sont |
| **Backend LLM indisponible** | `probe_llm()` → `llm_available: false` (Sentinel, live) | Phases 4/6 : les mesures de qualité LLM ne peuvent pas être produites ; seules les parties déterministes sont mesurables |
| **Pas d'accès système Windows** | `psutil`, `win32evtlog`, `win32service` MISSING | Hors périmètre de ce mandat (concerne Sentinel OS/Network Guard) |

Conséquence directe : **toute mesure annoncée dans les rapports 4, 5 et 6 devra préciser le profil
matériel** (`CPU_ONLY` + `REMOTE_PROVIDER` ici). Aucun chiffre GPU ne sera produit.

---

## 4. Plan de correction (minimal, ordonné)

| Lot | Phase | Correction proposée | Test de preuve |
|---|---|---|---|
| **R0** | 0 | ce document + décomposition en lots | — |
| **R1** | 1 | Stabilisation moteur : exercer la chaîne Pipeline → Worker avec erreurs/timeouts/retries, documenter ce qui n'existe pas (reprise après interruption) | tests ciblés + rapport `ENGINE_VALIDATION_REPORT.md` |
| **R2** | 2 | **D1/D2/D3** : `core/packager.from_package` reconnaît `agents/*.json` et lève une erreur explicite si le format est inconnu ; aucun second gestionnaire supprimé (pas de suppression) | test : les 2 packs livrés se chargent et se valident ; un zip bidon échoue avec un message clair |
| **R3** | 3 | Provenance : vérifier qu'un résultat permet de retrouver package/version/workers/modèle/seed ; ajouter les étiquettes `OBSERVED/SYNTHETIC/COMPUTED/INFERRED/VERIFIED/UNVERIFIED/INVALID` là où elles manquent | export relu et reconstruit, rapport `DATA_PROVENANCE_VALIDATION.md` |
| **R4** | 4 | Compression : benchmark comparatif mesuré (original vs compressé vs baseline), tokens avant/après, taux, temps, variabilité — **sans LLM** (partie déterministe) | `CONTEXT_COMPRESSION_BENCHMARK.md` avec chiffres réels |
| **R5** | 5 | Accessibilité : matrice de profils avec ce qui est réellement exécutable ici ; documenter `CPU_ONLY` + `REMOTE_PROVIDER`, marquer GPU `UNAVAILABLE` | `HARDWARE_ACCESSIBILITY_REPORT.md` |
| **R6** | 6 | Expérience de référence **déterministe** (pas de LLM requis), rejouable par un tiers, avec package LM si R2 est vert | `REFERENCE_EXPERIMENT.md` + sortie recollable |
| **R7** | 7 | Polish Studio : lisibilité, statuts fiables, aucun bouton sans handler | `STUDIO_POLISH_REPORT.md` |
| **R8** | 8 | Documentation chercheur : installation, provider, expérience, provenance, diagnostic | `RESEARCHER_QUICKSTART.md` |
| **R9** | 9 | Tests et validation finale, non-régression sur les 11 sous-systèmes | `TEST_RESULTS.md`, `IMPLEMENTATION_STATUS.md`, `KNOWN_LIMITATIONS.md`, `NEXT_STEPS.md` |

**Ordre imposé** : R0 → R9. Une phase bloquée est documentée (`BLOCKED` + raison) avant de passer à la suivante.

---

## 5. Ce que cet audit refuse de faire

- Annoncer Skills, Evolve ou Émulation comme existants : ils n'existent pas.
- Corriger `core/packager` en supprimant l'autre implémentation.
- Produire des chiffres GPU ou LLM alors qu'aucun moteur n'est installé.
- Présenter 989 features comme disponibles alors que 987 ne sont observées nulle part.
- Modifier les formats de packages sans migration testée (R2 conserve la compatibilité des deux layouts).

## 6. Portes de non-régression

```bash
.venv/Scripts/python -m pytest tests/ -q                    # 1 694 passed, 13 skipped (état de référence)
.venv/Scripts/python -m pytest pipeline_inspector/tests -q  # 28 passed
.venv/Scripts/python -m pytest tests/compression_validation -q
```

État de référence mesuré aujourd'hui : **1 694 passed, 13 skipped, 0 failed**.
