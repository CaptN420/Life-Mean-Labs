# PROTOCOL_TERMINOLOGY_AUDIT — Life_mean Lab

**Date : 2026-10-09**
**Cadre :** passe d'audit sémantique du mot « protocol » (« PROTOCOL TERMINOLOGY + RESPONSIBILITY AUDIT », spec `f224c0`). PAS un pass feature. Aucune fonctionnalité ajoutée.

---

## 1. EXECUTIVE SUMMARY

Le mot « protocol » n'est **pas gravement abusé** dans le code source vivant de Life_mean. La recherche exhaustive (code, tests, docs, config, UI) ne trouve **aucun composant nommé `CodingProtocol`, `TurnProtocol`, `RetryProtocol`, `RoutingProtocol` ou `EscalationProtocol`** qui exécuterait un workflow en étant mal étiqueté « protocol ». Les occurrences réelles se répartissent en trois catégories **sémantiquement correctes** :

1. **PROTOCOLES LÉGITIMES DE TRANSPORT / SÉRIALISATION / RECORDING** — à ne pas renommer (`window.location.protocol`, `self.protocol("WM_DELETE_WINDOW")`, le paquet `raw_protocol/` qui est un *RAW recording data protocol*).
2. **PROSE / DOCSTRINGS SÉMANTIQUEMENT VRAIES** — le mot « protocol » y décrit correctement un workflow/mécanisme déterministe (`library/protocols/`, `fallback.py: protocol_stalled`, docstrings `role_templates`). Faux amis dans les commentaires anglais, mais pas de champ de données mal nommé.
3. **CHAMPS DE DONNÉES CORRECTEMENT NOMMÉS** — `validator_protocol` (« code-lab-v2-freeform/known », un identifiant de stratégie de validation reproductible) et `executor_type` (déjà correctement nommé WORKFLOW/EXECUTOR, seuls les *commentaires* disent « protocol » par habitude).

**Verdict global : aucun renommage comportemental nécessaire.** Renommer `ReflectionProtocol` → autre chose casserait `test_phase4_protocols.py` (le seul plausible candidat) pour un gain sémantique marginal et violerait la règle §18 (« do not perform speculative renames ») : le nom est une capacité, mais il n'a **aucun appelant productif** — c'est de la doc _, le renommage n'améliore aucune lisibilité réelle du runtime.

**P0 CONFIRMÉ pour l'écosystème du mot :** aucun vrai modèle `ExperimentProtocol` n'existe (§6) — documenté ci-dessous comme **MISSING_TRUE_EXPERIMENT_PROTOCOL_MODEL**, à implémenter dans le futur, pas maintenant.

---

## 2. DEFINITIONS (carte terminologique cible)

| Terme | Définition | Exemple Life_mean |
|---|---|---|
| **PROTOCOL** | Conditions contrôlées ET reproductibles d'une expérience | (absent — modèle à créer) |
| **WORKFLOW** | Séquence d'étapes qui exécute une tâche | Planner→Developer→pytest→Critic→Repair→Reviewer |
| **PROCEDURE** | Recette opérationnelle concrète | lire fichier → parser config → valider → retry |
| **PIPELINE** | Composition runtime de stages + flux de données | research→debate→validation→analysis |
| **SKILL** | Instructions réutilisables / expertise | pytest-debugging, secure-coding |
| **TEMPLATE** | Configuration de départ réutilisable | `CODING_STANDARD`, `PHILOSOPHICAL_DEBATE` |
| **POLICY** | Règles runtime / comportement autorisé | retry, escalation, routing policy |
| **SCHEMA** | Structure/validation des données | JSON schema raw_protocol |
| **TRANSPORT_PROTOCOL** | HTTP/MCP/WebSocket/window | `window.location.protocol`, tkinter `WM_DELETE_WINDOW` |
| **TOOL** | Capacité déterministe exécutable | `ReflectionProtocol` (mechanisme), 59 tools |
| **RUN** | Occurrence réelle d'exécution | un run_id |
| **EXPERIMENT** | Unité scientifique contenant ≥1 run | un experiment_id |

---

## 3. TOUTES LES OCCURRENCES IMPORTANTES DE « protocol » (fichiers source vivants uniquement, hors `.venv`, `build/`, `legacy/`, `hermes-debate`, `storage`, `data/`, `__pycache__`)

### Fichiers de code

| Fichier | Occurrences | Lignes clés |
|---|---|---|
| `library/protocols/__init__.py` | 4 | `ReflectionProtocol`, `reflect`, `StagnationDetector` (exports) |
| `library/protocols/reflection.py` | 9 | `class ReflectionProtocol`, `name="reflection_protocol"` |
| `library/protocols/stagnation.py` | (impl.) | `class StagnationDetector` |
| `library/reliability/fallback.py` | 2 | `"protocol_stalled"` (clé de diagnostic stagnation) |
| `role_templates/core.py` | 5 | docstring `agent team / protocol` ; commentaires `executor_type` appelé « protocol » |
| `role_templates/registry.py` | 4 | docstrings « protocol definitions/registration » (= templates) |
| `code_lab/engine.py` | 5 | `validator_protocol = "code-lab-v2-freeform"/"code-lab-v2-known"` (+`_version`) |
| `code_lab/__init__.py` | 1 | docstring « deterministic protocol » (= pipeline déterministe) |
| `philosophical_council/raw_protocol/__init__.py` | 3 | « RAW Debate Data Protocol », `SCHEMA_VERSION="1.0.0"` |
| `philosophical_council/core/debate_engine.py` | 1 | import `RawDebateRecorder` (seul usage réel) |
| `philosophical_council/ui/app.py` | 1 | `self.protocol("WM_DELETE_WINDOW", ...)` = **TRANSPORT/window** |
| `experiments/ui/dashboard.html` | 1 | `window.location.protocol === 'file:'` = **TRANSPORT/URL** |
| `tests/test_phase4_protocols.py` | 26 | tests ReflectionProtocol/StagnationDetector (nom de fichier « phase4_protocols » historique) |
| `tests/test_code_lab_freeform.py` | 4 | assert `validator_protocol == "code-lab-v2-..."` |
| `tests/test_phase5_reliability.py` | 1 | `protocol_stalled` dans la liste des error_types |
| `tests/test_model_pool.py` | (via hermes_debate) | hors périmètre (projet séparé) |

### Fichiers docs / completion (prose historique `*.md`)

`PHASE_4_COMPLETION.md` (17), `MIA_BRAIN_MIGRATION_PLAN.md` (14), `AUTONOMOUS_SYNTHETIC_DATA_GENERATOR.md` (10), `PHASE_5_COMPLETION.md` (6), `docs/ARCHITECTURE*.md` (5), `CODE_LAB.md` (3), `DESIGN_UPDATE_SUMMARY.md` (3), `README.md` (1), phases 0-3/7 (1 chacun). Toutes ces mentions décrivent **des workflows/pipelines/mécanismes historiques** — pas des protocoles expérimentaux. Docs immuables/historiques, non réécrites (le nettoyage des `.md` est hors périmètre d'un pass de terminologie de code).

---

## 4. CLASSIFICATION (tableau détaillé)

| Objet actuel | Chemin | Responsabilité réelle | Catégorie sémantique | Renommage requis ? | Risque si renommage | Notes |
|---|---|---|---|---|---|---|
| `ReflectionProtocol` (classe) | `library/protocols/reflection.py:16` | Mécanisme déterministe de transformations miroir (parse hypothèse → miroir → valider → score) | **TOOL** (capacité déterministe) ; parfois **WORKFLOW** (séquence d'étapes) | **NON** (deux raisons : 0 appelant productif, et §18 interdit renommage spéculatif) | Élevé pour ~0 gain | Nom historiquement « protocole de réflexion » ; réf. par `test_phase4_protocols.py` + `__init__`. Ne pas renommer. |
| `StagnationDetector` (classe) | `library/protocols/stagnation.py:15` | Détecteur de stagnation (répétition de tours) | **POLICY / TOOL** (règle de détection) | NON | — | Nom déjà correct (« detector »). |
| paquet `library/protocols/` | `library/protocols/` | Regroupe reflection + stagnation deterministes | nom de paquet = WORKFLOW/TOOL layer, pas « protocol » | NON (renommage de paquet fou, aucun runtime ne l'importe) | — | Seul `test_phase4_protocols.py` l'importe ; `registry.py` ne l'utilise pas dans le runtime. |
| `"protocol_stalled"` (clé) | `library/reliability/fallback.py:134` | Clé de diagnostic : « debate or reflection **mechanism** detected stagnation » | **POLICY** (stratégie de récupération) | NON | Cassera `test_phase5_reliability.py:132` | La string est référencée dans un test ; c'est une étiquette de policy, pas un protocole. §10 : « do not call runtime behavior rules protocol » — mais ici `protocol_stalled` ≠ nom de classe Policy ; acceptable. |
| docstring `RoleTemplate : agent team / protocol` | `role_templates/core.py:94` | Le tout = une équipe d'agents / un profil d'exécution | **TEMPLATE** (+ WORKFLOW via `executor_type`) | NON (commentaire) | — | Faux ami EN : « protocol » employé pour dire « team/workflow ». Le *champ* s'appelle déjà `executor_type` (correct). Corriger la docstring = doc cleanup optionnel. |
| commentaires `role_templates/core.py:100-104, registry.py` | idem | `executor_type: code_lab/philosophical_debate/general_reasoning` | en réalité **WORKFLOW/EXECUTOR** | NON (commentaires) | — | Le nom du champ est correct ; seuls les commentaires l'appellent « protocol ». |
| `result["validator_protocol"]` | `code_lab/engine.py:565,703,828` | Identifie la stratégie de validation utilisée (freeform vs known oracle) | **SCHEMA / VALIDATION-PROTOCOL** (identifiant reproductible) | NON | — | §11 : `validator_protocol` légitime car c'est un identifiant reproductibilité-relevant. Valeurs figées dans RAW (immuable). |
| `validator_protocol_version` | `code_lab/engine.py:829` | Version de la stratégie de validation | **SCHEMA version** | NON | — | « _version » pas « protocol version » : correct. |
| paquet `raw_protocol/` | `philosophical_council/raw_protocol/` | Recording format des debate RAW pour ML training | **RAW_FORMAT / transport-serialization** | NON (explicitement protégé §5/§12) | — | `RawDebateRecorder` réellement utilisé par `debate_engine.py:33` et `code_lab/engine.py:155`. Ne jamais renommer. |
| `self.protocol("WM_DELETE_WINDOW")` | `philosophical_council/ui/app.py:51` | Handler de fenêtre tkinter | **TRANSPORT_PROTOCOL** (window protocol) | NON | — | API Tk standard. §Transport-protocol exempté. |
| `window.location.protocol === 'file:'` | `experiments/ui/dashboard.html:646` | Schéma d'URL du navigateur | **TRANSPORT_PROTOCOL** (URL scheme) | NON | — | JS standard. Exempté. |
| `tests/test_phase4_protocols.py` | — | Nom de fichier historique (phase 4 du design doc) | **LEGACY_NAME** | NON | — | Phase 4 = « protocols » dans le doc de design d'origine. Sémantique historique, pas runtime. |
| `code_lab/__init__.py:8` docstring | — | « deterministic protocol » = pipeline déterministe | **WORKFLOW/PIPELINE** (prose) | NON (prose) | — | Docstring. |

---

## 5. CONFIRMED MISNOMERS

Aucun **misnomer de champ de données** ou de composant runtime n'a été confirmé au sens strict (§18 : nom objectivement trompeur **et** améliorant la clarté **et** à faible risque). Les seuls « faux amis » sont :

1. **Commentaires/docstrings** où « protocol » est employé pour dire « workflow/team/mechanism » :
   - `role_templates/core.py:94` (« team / protocol »)
   - `role_templates/core.py:100-104` (« which protocol a template may drive » — il s'agit en réalité de `executor_type` )
   - `role_templates/registry.py:10,41,54` (« protocol definitions » — ce sont des **templates**)
   - `code_lab/__init__.py:8` (« deterministic protocol » — pipeline déterministe)
   - `library/protocols/__init__.py:1` et `reflection.py:1` (« deterministic debate and reflection mechanisms » — des tools)

   → Prose seulement ; **zéro champ de données mal nommé**. Correctibles en doc cleanup si désiré (hors scope d'un pur audit, aucune nécessité).

2. **`ReflectionProtocol`** : qualité « reflection mechanism » ≠ « scientific protocol ». **Sans appelant productive**, donc sans gravité runtime. Ne pas renommer.

---

## 6. RENAMES PERFORMED

**Aucun renommage de composant effectué.**

Justification conforme §18 et 25 :
- La seule classe plausible (`ReflectionProtocol`) n'a **aucun utiliste productif** — uniquement `test_phase4_protocols.py` et son propre `__init__`. Un renommage = gros diff (`library/protocols/*.py` + `__init__` + tests) pour 0 bénéfice runtime → renommage **spéculatif** (interdit).
- Tous les autres usages sont soit légitimes (transport, RAW, URL, window), soit de la docstring.
- Le pass ne doit **pas cacher des changements de comportement dans un refactor de terminologie** (§25). Aucun changement de comportement n'est justifié ici.
- Les docs historiques `*.md` ne sont pas nettoyées (prose immuable, hors périmètre ; un nettoyage de doc serait un pass séparé).

---

## 7. LEGACY COMPATIBILITY

Sans renommage → aucune compatibilité à maintenir. Les identifiants existants (`validator_protocol`, `raw_protocol`, `ReflectionProtocol`, `executor_type`) restent stables, ce qui préserve :
- les imports existants,
- les payloads API,
- les assertions de tests (`test_code_lab_freeform`, `test_phase4_protocols`, `test_phase5_reliability`),
- les exports de paquets.

---

## 8. HISTORICAL RAW IMPLICATIONS

- `result["validator_protocol"]` (= "code-lab-v2-freeform" | "code-lab-v2-known") est **écrit dans le RAW JSON** (`code_lab/engine.py`). C'est un identifiant de stratégie de validation reproductible — sémantiquement correct, **ne pas toucher**. Le RAW est immuable (§12) : aucune réécriture.
- Le RAW debate (`raw_protocol/`) stocke `EventType` + `schema_version="1.0.0"` : c'est un format de données, pas un faux protocole. Aucun champ RAW n'est mal nommé.
- Aucun champ RAW ne contient de mot « protocol » abusif (vérifié : le RAW enregistre `execution_mode` (deterministic/debate), `validator_protocol` — tous deux légitimes).

---

## 9. DB / API IMPLICATIONS

Aucune migration DB ni changement d'API. Les champs sérialisés exposés sont `validator_protocol`, `validator_protocol_version`, `executor_type`, `role_template` — tous correctement nommés. Aucun endpoint `/api/*` ne s'appelle « protocol ». (Vérifié par la revue des routes compare/code-lab/experimental/settings.)

---

## 10. REMAINING AMBIGUITIES & OVERLOADED WORDS (§21 — signalés, non refactorés)

Champs observés dans le RAW/provenance, à surveiller sans agir :

| Terme | Signalé ? | Détail |
|---|---|---|
| `agent` | OUI | `DesignAgent`, `CodingAgent`, agents « role X » — overloadé entre « rôle de team » et « appel LLM ». |
| `worker` | OUI | `ToolWorker` = tool exécuté via bus ; `math_validation_worker` = tool détecté. Écart naming sémantique. |
| `template` | OUI | `role_template` (RoleTemplate) vs `validator_protocol` (template de validation). Ne pas fusionner. |
| `executor` | OUI | `executor_type` (workflow kind) vs `executors=` du `ExperimentalEngine` (adaptateurs). Usage cohérent. |
| `run` | OUI | `run_id` vs `Run` (quel journal) — cohérent. |
| `validator` | OUI | validator déterministe vs SemanticCodeJudge (opinion LLM) — déjà séparés (rule 6). |
| `judge` | OUI | `SemanticCodeJudge` (CodeLab) vs `JudgeAgent` (hermes-debate, module non importable → ABSENT). Déjà documenté. |

Aucun de ces termes n'exige d'action dans ce pass (uniquement signalement).

---

## 11. TESTS EXECUTED

`python -m pytest -q` depuis la racine (config pyproject → pythonpath=["."]).

- **Baseline : 607 passed, 10 skipped** (skips = deps `model_pool`/`hermes_debate`, projet séparé), 0 collection error. Warnings : cosmétiques `datetime.utcnow()` deprecation (`raw_protocol`), sans effet.
- Après refactor de robustesse P0/P1 (hors périmètre de CET audit, cf. note) : les tests concernés passent — `tests/test_code_lab_multiagent.py` (3 unit + live skip) et `tests/test_p1_agent_terminal_event.py` (4) + `tests/test_p0_raw_finalization.py` (3).
- Aucun test n'a été modifié pour cet audit terminologique (aucun renommage → rien à casser).

Les skips : `test_model_pool.py` (skipif import_lib hermes_debate absent), `TestLiveMultiAgentIntegration` (skipif probe backend down) — connus, inchangés.

---

## 12. FINAL TERMINOLOGY MAP (exigé §23)

| Concept | Terme canonique | Présent dans Life_mean ? |
|---|---|---|
| Conditions scientifiques reproduisibles d'une expérience | **PROTOCOL** | ⚠️ **MISSING** (docs seulement, modèle `ExperimentDesign` partiel) |
| Configuration de départ réutilisable | **TEMPLATE** | ✅ `RoleTemplate`, `CODING_STANDARD`… |
| Séquence d'étapes exécutant une tâche | **WORKFLOW** | ✅ Planner→Developer→pytest→Critic→Reviewer (Code Lab) ; debate pipeline |
| Composition runtime stages + data flow | **PIPELINE** | ✅ (par fragmented) |
| Recette opérationnelle | **PROCEDURE** | ✅ (fragmented) |
| Instructions réutilisables / expertise | **SKILL** | ✅ (externe à ce repo) |
| Capacité déterministe exécutable | **TOOL** | ✅ 59 tools + `ReflectionProtocol` (tool de facto) |
| Exécuteur borné spécialisé | **WORKER** | ✅ `ToolWorker`, workers outil |
| Stratégie de raisonnement | **THINKER** | ✅ (Skeptic/Statistician…) |
| Contrainte de comportement runtime | **POLICY** | ✅ retry/escalation/routing |
| Forme des données | **SCHEMA** | ✅ raw_protocol schema, JSON |
| Occurrence réelle d'exécution | **RUN** | ✅ run_id |
| Unité scientifique contenant ≥1 run | **EXPERIMENT** | ✅ experiment_id |
| Protocole de transport (HTTP/MCP/WS/window) | **TRANSPORT_PROTOCOL** | ✅ (URL, tkinter) — légitime |

### MISSING_TRUE_EXPERIMENT_PROTOCOL_MODEL

**État : MAUQUANT.** Il n'existe **aucun** modèle `ExperimentProtocol` dans le repo. Le plus proche est `experimental/schema.py::ExperimentDesign` (research_question, validators, budgets, stop_conditions — déjà **non** nommé « protocol »), mais il lui manque `hypothesis`, `controlled_variables`, `independent_variables`, `dependent_metrics`, `seeds`, `provenance_requirements`, `reproducibility_requirements` en tant que champs explicitement séparés.

**Décision (§6) : ne PAS construire ce modèle pendant ce pass.** Documenté ici pour implémentation future (IDEA PARKING LOT). Un futur `ExperimentProtocol` devrait obtenir les champs §7 et **traiter le workflow comme une VARIABLE** à l'intérieur du protocole (WORKFLOW != PROTOCOL), comme l'exige le spec.

---

## 13. RECOMMANDATIONS (hors périmètre de ce pass, à planifier séparément)

1. [IDEA_PARKING_LOT] Implémenter `ExperimentProtocol` (modèle scientifique complet §7) au-dessus d'`ExperimentDesign`.
2. [IDEA_PARKING_LOT si souhaité] Si un jour `library/protocols/` est réactivé, le renommer en `library/mechanisms/` (et `ReflectionProtocol`→`ReflectionMechanism`) avec alias de compatibilité + mise à jour `test_phase4_protocols.py`. Non requis aujourd'hui (0 utiliste).
3. [doc cleanup optionnel] Clarifier les docstrings `role_templates` (« protocol »→« executor/workflow ») quand une passe de doc aura lieu. Aucun impact runtime.
4. Conserver `raw_protocol/`, `transmets` intacts et ne jamais renommer : ils sont des sémantiques légitimes.

---

## 14. RÉSUMÉ GIT

Aucun fichier source modifié par cet audit de terminologie. (Les seules modifs dans l'arbre sont les réparations de robustesse P0/P1 d'une mission **séparée** — RAW finalization + terminal agent events — rapportées ailleurs, non mêlées à ce pass conformément §25.)