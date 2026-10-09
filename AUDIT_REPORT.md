# LIFE_MEAN LAB — TOTAL INTEGRATION AUDIT + EMERGENCY INTEGRITY REPAIR — FINAL REPORT

**Dates des specs :** 2026-10-09 (TOTAL INTEGRATION AUDIT `407f56` → EMERGENCY INTEGRITY REPAIR `905a04` → HYBRID EXECUTION `5f3e3c` → PROTOCOL TERMINOLOGY `f224c0`).
**FEATURE FREEZE actif** : aucune feature ajoutée. Réparations limitées aux P0/P1 confirmées par preuves (code + runtime + expériences).

---

## 0. CORE RULE RESPECTÉE

**REAL FAILURE > FAKE SUCCESS.** Hiérarchie de vérité appliquée : **ACTUAL BACKEND ACTION → CANONICAL EVENT → RAW → UI/LOGS**. Le frontend ne fabrique jamais l'état runtime. Tout statut absent est `NOT_RECEIVED`/`UNAVAILABLE`/`NOT_REACHED`, jamais `COMPLETED` inventé.

---

## 1. INVENTORY COMPLET (feature freeze — aucune feature ajoutée)

| Couche | Composants | Statut |
|---|---|---|
| **Stable core** | EventBus, SmartRouter, LLMClient, Settings, RAW recorder, OracleValidator, ToolWorker (59 tools), tool detection, personas | ✅ opérationnel |
| **Exécution** | CodeLabEngine, DebateEngine, Autopilot, ExperimentalEngine, deterministic ExperimentRunner, workers/thinkers | ✅ câblés |
| **Expérimentations** | Experiment/Run, stages, templates, RoleTemplates, model pools, personas, roles, validators, provenance, lifecycle | ✅ |
| **Analyse** | Compare (browser index, comparability, analyzer, subjects) | ✅ 53 tests |
| **UI/API** | dashboard, Settings, Compare (3 colonnes), Code Lab, Debate, Autopilot, experimental | ✅ routes câblées |
| **Données** | RAW `data/raw_debates/*.jsonl` (172), Code Lab RAW snapshots `code_lab_runs/<id>/raw/` (278), subject tree, compare_index.json | ✅ |

- **Legacy** : `hermes-debate/` et `hermes-orchestrator/` = projets git **séparés**, `legacy/` git-ignoré + hors wheel. Aucun câblage vers le core actif.

---

## 2. WIRING MAP (chaîne complète, validée par lecture de code E2E)

```
dashboard (HTTP POST /api/experiments, /api/code-lab/*)
  → ExperimentUIController._run_experiment_loop   (mode: debate | deterministic)
       ├─ debate=True  → probe_llm ? unavailable ⇒ raise RuntimeError + add_error ⇒ FAILED (honnête, PAS de fallback silencieux)
       │                     available ⇒ AutoPilot → DebateEngine (real DB, real agents, real moderator)
       │                                          → _validate_response (deterministic validator = autorité) → RAW data/raw_debates
       └─ deterministic → TaskGenerator → ExperimentRunner → SmartRouter → ToolWorker → OracleValidator
                                      → RAW data/raw_debates/<experiment_id>.jsonl (execution_mode: deterministic)
Dashboard Code Lab:
  → CodeLabConfig(role_models ← coding_pool, template_id ← role_templates)
  → CodeLabEngine.run() → _plan (template detect) → _execute (DEVELOPER/VERIFIER/CRITIC loop)
  → pytest (isolated workspace) + OracleValidator ⇒ det_status: PASS/FAIL
  → _persist_raw → code_lab_runs/<run_id>/raw/run_<run_id>.json  (RAW immuable, git-ignoré)
  → _emit → view.events → GET /api/code-lab/runs/<id>/events (polling — PAS via EventBus)
Compare:
  → compare.loader (lit RAW uniquement, écrit ~jamais) → comparability → analyzer → browser index (sidecar)
```

Classification honnête des connexions :
- **Config** : Settings → pool → RoleTemplate → `CodeLabConfig.role_models` → agents. **Connexion réelle et testée.**
- **EventBus → dashboard** : `event_history` interne ; le bus global n'est PAS lu par l'UI (voir §4 — `YELLOW`, architectural, aucune fabrication d'état).
- **RAW** : écrire = data + workspace ; lire = Compare. **Bidirectionnelle saine.**

---

## 3. EVIDENCE TABLE (problèmes que les expériences ont réellement démontrés + vérifs runtime)

| # | Preuve | Type A/B/C | Verdict |
|---|---|---|---|
| E1 | `_persist_results_to_raw` avalait un échec d'écriture RAW (`except` vide) alors que l'expérience se marquait COMPLETED | A (code) + démontré | **P0 — CONFIRMÉ + RÉPARÉ** (voir R1) |
| E2 | `CodingMultiAgent` émettait AGENT_STARTED puis appelait `turn()` **sans try/finally** → un LLM qui lève laisse un STARTED orphelin (phantom de timeline) | A (code `multiagent.py:307-345`) | **P1 — CONFIRMÉ + RÉPARÉ** (voir R2) |
| E3 | `ReflectionProtocol`/`StagnationDetector` nommés « protocol » = mécanismes | A (code) | YELLOW doc — aucun appelant productif, pas de renommage (spec §18) |
| E4 | Code Lab `recorder_experiment_id` jamais exposé dans le résultat ; `RawDebateRecorder` reste en mémoire (start/record_input jamais `save_experiment`) | A (code `engine.py:412-424`, `raw_protocol`) + runtime | **YELLOW exposition** — la provenance RÉELLE est le snapshot workspace `_persist_raw`, qui est écrit et sain ; l'écart est de visibilité, pas de fabrication (voir R3, non bloquant) |
| E5 | **Evidence expérimentale majeure** : `data/raw_debates` — toutes les erreurs enregistrées = « No answer computed » | C (RAW miné) | **GREEN "honnête"** : c'est un REAL FAILURE (limitation d'extraction de paramètres coding/logic), pas un phantom. Mis en évidence, non masqué |
| E6 | Domaines : physics=100 %, chemistry=100 %, math≈60 %, **coding=0 %, logic=0 %** (10 200 tâches chacun, `no_answer`) | C (RAW) | Surcharge la note périmée du skill (« physics/chem 0 % ») ; le skill a été corrigé |
| E7 | EventBus « fantôme » : 3 instances privées, `CodeLabEngine.event_bus` jamais publié, dashboard lit `view.events` | A (audit EventBus subagent) | **YELLOW architectural** — pas de phantom de sortie (l'UI lit une chaîne callback backend-réelle) |
| E8 | Sujets débats inutilisables quand backend LLM down | B (runtime, gate probe) | **GREEN** : fake success impossible — l'utilisateur voit FAILED explicite |

---

## 4. CONFIRMED FAILURES + INTEGRITY STATUS (GREEN / YELLOW / RED)

### P0 — CONFIRMED + FIXED (verts)

**R1. RAW finalization (P0) — PHANTOM ÉLIMINÉ.**
- **Avant :** `_persist_results_to_raw` catchait l'échec d'écriture RAW et le loggueait ; l'expérience finissait **COMPLETED** sans *aucune* preuve RAW. = exactement ce que le spec §10 interdit (« experiment says COMPLETED but finalization failed »).
- **Réparé :** la méthode prend désormais `raw_root` (injectable pour tests) et, sur échec, appelle `add_error(experiment_id, "finalization_failure: RAW persistence failed (...)")` → statut dérivé **FAILED**, jamais COMPLETED sans preuve.
- **Preuve :** `tests/test_p0_raw_finalization.py` (3 tests) — succès écrit `execution_mode` + `settings_snapshot` ; échec (répertoire bloqué) → FAILED ; traversal `/` → `_`.
- **Statut :** `CONFIRMED_FIXED`.

**R2. Terminal AGENT events (P1).**
- **Avant :** AGENT_STARTED orphelin si l'inférence lève.
- **Réparé :** les 5 rôles passent par `_turn()` qui garantit un terminal AGENT_RESPONSE/AGENT_FAILED sur toute exception, puis re-lève. Retour inchangé (`{"agent": role, **res}`).
- **Preuve :** `tests/test_p1_agent_terminal_event.py` (4 tests) + `test_code_lab_multiagent.py` (3) — non-régression vérifiée (`p["agent"]=="PLANNER"`).
- **Statut :** `CONFIRMED_FIXED`.

### YELLOW — documentés, non bloquants, à traiter hors ce pass (IDEA PARKING LOT)

**Y1. EventBus ghost layer.** `CodeLabEngine.event_bus` assigné mais jamais publié ; dashboard lit `view.events` (callback-réel) — cohérent, mais le bus global voulu par le spec ne porte pas les événements Code Lab. *(Réactiver la publication `event_bus.publish` dans `_emit` + un vrai `.subscribe()` côté dashboard = feature câblage, interdite en freeze ; documenté pour un pass ultérieur.)*

**Y2. Code Lab provenance visible.** `recorder_experiment_id` n'est pas exposé dans `to_dict()`, et `RawDebateRecorder` ne persiste que si `save_experiment` est appelé — il ne l'est pas dans `_plan` (stay in-memory). La *vraie* preuve disque est `_persist_raw` (workspace snapshot) — celle-ci est **écrite et correcte** (voir E4). Amélioration suggestionnée : exposer `raw_path`/`recorder_experiment_id` dans le résultat. *(Doc, pas un phantom — la preuve existe et correspond au disque. À confirmer par l'utilisateur avant de brancher un champ API.)*

**Y3. Limitation realizare : « No answer computed » sur coding/logic.** Échec honnête (l'extraction n'extrait que math/force/molar). Pas un phantom — c'est un REAL FAILURE que nous rendons visible. Étendre l'extraction aux outils coding/logic = feature, hors freeze → IDEA PARKING LOT.

### RED — aucun

### Status d'intégrité global

| Axe | Statut |
|---|---|
| CODE LAB OUTPUT INTEGRITY | **GREEN** (pas de phantom : fichiers==disque, judge UNAVAILABLE honnête, RAW snapshot persiste) |
| DEBATE RUNTIME | **GREEN** (s'exécute réellement avec backend ; échec backend → FAILED explicite, jamais fallback) |
| RAW PROVIDENCE | **GREEN** après R1 (échec RAW → FAILED ; historique immuable) |
| PHANTOM OUTPUT FORBIDDEN | **GREEN** (R1+R2 + verdicts E7/E4=visibilité, pas fabrication) |
| FEATURE FREEZE | **RESPECTÉ** |

---

## 5. REPAIRS SOMMAIRES (liens)

- `experiments/ui_controller.py` — `_persist_results_to_raw(..., raw_root=)` + échec → `add_error` → FAILED.
- `code_lab/multiagent.py` — helper `_turn()` garantit un événement terminal ; les 5 rôles l'utilisent ; import `Callable` ajouté ; retour `{"agent": role, **res}` préservé.
- `skill life-mean` — mis à jour (R1, R2, E6, trajectoire de stub LLM `chat()` vs `turn()`).
- **PROTOCOL_TERMINOLOGY_AUDIT.md / .json** — rapport terminologique (deliverable spec f224c0).

---

## 6. TESTS

- `python -m pytest -q` : **608 passed, 10 skipped** (skips = deps `model_pool`/`hermes_debate` projet séparé), 0 erreur. Warnings = `utcnow()` cosmétiques (`raw_protocol`).
- Bloc réparation : 3 + 4 + 3 = **10 tests verts dédiés**.
- E2E runtime vérifiés (cette session) :
  - Code Lab déterministe : det_status PASS, `files_created` réels == workspace disque, judge `UNAVAILABLE`, snapshot RAW persisté. **SAIN.**
  - Debate avec stub LLM : 11 tours réels, réponse vraie, raw id assigné, db créée. **SAIN** (le gate probe empêche toute exécution fantôme sans backend).

---

## 7. RÉSUMÉ GIT (rien commité)

Modifiés : `code_lab/multiagent.py`, `experiments/ui_controller.py`. Rapports : `PROTOCOL_TERMINOLOGY_AUDIT.md`, `protocol_terminology_audit.json`. Nouveaux tests : `test_p0_raw_finalization.py`, `test_p1_agent_terminal_event.py`. Travaux antérieurs Compare (non commités non plus) : `compare/`, `dashboard.py/html`, `pyproject.toml`, etc.

**Attente feu vert utilisateur avant tout commit/push.**

---

## 8. THINGS LEFT (IDEA PARKING LOT / prochains pass proposés, PAS implémentés)

1. [Y2] Exposer `raw_path`/`recorder_experiment_id` dans le résultat Code Lab (visibilité provenance).
2. [Y1] Brancher l'EventBus code-lab + un abonnement dashboard (observabilité unifiée).
3. [Y3] Étendre l'extraction de paramètres aux outils coding/logic (pour lever « No answer computed »).
4. [Y3] Implémenter `ExperimentProtocol` (modèle scientifique complet §7) au-dessus d'`ExperimentDesign` — MISSING_TRUE_EXPERIMENT_PROTOCOL_MODEL documenté.
5. Conserver `raw_protocol/`, `transmets`, `ReflectionProtocol` intacts (terminologie légitime / sans appelant productif).