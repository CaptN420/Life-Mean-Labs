# Code Lab — Design & Implementation (V1)

> **Statut :** IMPLÉMENTÉ & TESTÉ (V1 déterministe)
> **Principe :**
> CODE LAB
> 　↓
> EXPERIMENTAL LAYER
> 　↓
> USES STABLE CORE (EventBus, SmartRouter, OracleValidator, RawDebateRecorder,
>                   ToolWorker/tools, protocol deterministic)

---

## 1. Architecture

Code Lab est une **couche expérimentale** au-dessus du *stable core* existant du
dépôt. Il n'introduit **pas** de second moteur multi-agent : il orchestre les
composants déjà présents et fonctionnels.

```
code_lab/
  __init__.py        # façade publique
  config.py          # CodeLabConfig (déterministe, reproductible)
  workspace.py       # CodeLabWorkspace (isolation + bornes de sécurité)
  generator.py       # génération déterministe (templates Python)
  engine.py          # CodeLabEngine (pipeline, événements, RAW)
  controller.py      # CodeLabController (état des runs, API-facing)
  runs/              # workspaces isolés par run (git-ignored)
```

### Composants du stable core réutilisés (vérifiés réels)

| Composant | Emplacement | Usage dans Code Lab |
|-----------|-------------|---------------------|
| **SmartRouter** | `core/assignment/router.py` | route le prompt → sélectionne un worker (`deterministic_coder`) ; décision enregistrée en provenance |
| **EventBus** | `core/events/event_bus.py` | canal d'événements (PRÊT à être branché ; V1 émet directement dans le run) |
| **OracleValidator** | `experiments/validation/oracle.py` | validation déterministe (non utilisé pour le code : le `compile()` est l'oracle du code) |
| **RawDebateRecorder** | `philosophical_council/raw_protocol/` | enregistrement RAW immuable (start, input, snapshots, trajectoire) |
| **Protocol déterministe** | `library/protocols/` | pattern de boucle déterministe |
| **ToolWorker / tools** | `core/workers/tool.py`, `library/tools/` | envisagé pour les validations structurelles futures |

> **Note honnête (règle 4/15) :** le moteur LLM `DebateEngine` (in
> `philosophical_council/`) existe et est complet, **mais** dépend de LM Studio
> (`localhost:1234`), actuellement **inaccessible**. Code Lab **ne le simule
> pas** : chaque run enregistre `llm_available: false` et fonctionne en
> déterministe. Dès que LM Studio tourne, le branchage LLM pourra être activé
> dans `CodeLabEngine._execute` sans refonte.

---

## 2. Flux d'exécution réel (1 run)

```
USER PROMPT (fibonacci)
   │
   ▼
┌─ PLANNER (engine._plan)
│   • detect_plan(prompt) → plan_id="fibonacci"
│   • SmartRouter.route(prompt) → {"selected": ["deterministic_coder"]}
│   • RAW: start_experiment + record_input
│   ▼
┌─ DEVELOPER (generator.generate_files)
│   • écrit fibonacci.py + test_fibonacci.py dans workspace isolé
│   • guarde tour vide → échec si aucune sortie (règle 7)
│   ▼
┌─ VERIFIER (engine._run_tests)
│   • exécute pytest RÉEL dans le workspace (sous-processus borné)
│   • pytest PASS → itération 1, break
│   ▼
┌─ VALIDATE (engine._validate_files)
│   • compile() de chaque fichier source (preuve déterministe)
│   • validation déterministe = autorité (règle 6)
│   ▼
┌─ RAW (Rule 11/15)
│   • raw/run_<id>.json  (immuable, refusé si existe)
│   • raw/trajectory.jsonl (append-only : prompt→plan→test→validation)
│   ▼
RESULT {status, plan, iterations, files, pytest, validation, judge}
```

### Boucle itérative (V1 conservateur)

Sur échec pytest, le pipeline entre en boucle **CRITIC → REPAIR → VERIFIER**
jusqu'à `max_iterations`. V1 n'invente **pas** de correctifs non éprouvés : un
échec qui n'a pas de réparation sûre et déterministe est **reporté honnêtement**
comme échec (règle 6/15) au lieu de simuler un succès. Un tour vide est
toujours marqué échec (règle 7).

### Rôle du Judge — état réel

**Un JudgeAgent n'existe PAS dans le chemin de code utilisé.**
`hermes-debate/agents/judge.py` existe mais son module **ne s'importe pas**
(effet des 10 tests `test_model_pool.py` en échec pré-existant). Code Lab
enregistre donc explicitement :

```json
"judge_validation": "unavailable (no JudgeAgent in used code path)"
```

et **ne fabrique pas** de verdict Judge de substitution (règle 15). Les
propriétés vérifiables sont tranchées par `pytest`/`compile()` (règle 6).

---

## 3. Sécurité & bornage (règles 8, 9, 18)

- **Workspace isolé** : chaque run écrit uniquement sous `code_lab/runs/<run_id>/`.
- **Fuite de chemin bloquée** : `resolve()` refuse `..` et les chemins qui
  sortent de la racine du workspace.
- **Chemins sensibles bloqués** : accès refusé aux mots-clés host (`C:\Users`,
  `/etc`, `.ssh`, `credentials`, `site-packages`, …) dans les chemins.
- **Allowlist de commandes** : seul `python`/`pytest`/`python3` autorisé dans
  `subprocess` (AssertionCommandAllowed).
- **Bornes** : `timeout_seconds`, `max_output_bytes`, `max_files`, `max_iterations`.
- **Destruction** : `cleanup()` n'est invoquée que par action utilisateur
  explicite (DELETE UI/API), jamais automatiquement.
- **RAW immuable** : les snapshots refusent toute réécriture ; trajectoire en
  append-only.

---

## 4. Provenance (règle 9/12)

Chaque run conserve : `run_id`, `project_name`, `prompt`, `language`,
`seed`, `max_iterations`, flags multi-agent/tests/validation/reflection,
`timeout`, `created_at`, + en RAW : plan, routing décision (SmartRouter),
fichiers créés, résultat pytest, validation, duration, `llm_available`.

---

## 5. API (réutilisée, phase 10)

Les routes Code Lab sont **greffées sur l'API dashboard existante**
(`experiments/dashboard.py`, `DashboardHandler`) — pas de seconde API :

```
POST   /api/code-lab/runs                    # crée + démarre
GET    /api/code-lab/runs                    # liste
GET    /api/code-lab/runs/{id}               # détail + événements + résultat
GET    /api/code-lab/runs/{id}/files         # fichiers du workspace
GET    /api/code-lab/runs/{id}/events        # événements live
POST   /api/code-lab/runs/{id}/start|/stop   # contrôle
DELETE /api/code-lab/runs/{id}               # supprime run + workspace
```

Le backend émet de vrais événements (jamais simulés côté frontend) :
`RUN_STARTED, PLAN_CREATED, FILE_CREATED, TEST_STARTED, TEST_PASSED,
TEST_FAILED, VALIDATION_COMPLETED, RUN_COMPLETED, RUN_FAILED, RUN_STOPPED`.

---

## 6. Frontend (phase 2)

`dashboard.html` devient une app à onglets :
`[ Debate ] [ Autopilot ] [ Code Lab ] [ Settings ]`.

L'onglet **Code Lab** contient : prompt, nom de projet, langage, itérations max,
cases multi-agent / tests / validation déterministe / reflection, bouton
**BUILD**, liste des runs, log live des événements, statut, plan, fichiers,
résultat judge.

*Backward compatibility (règle 17) :* l'onglet Debate/Experiments conserve tout
son comportement (stats, création d'expériences, start/stop/delete) — vérifié.

---

## 7. Tests (phase 13)

`tests/test_code_lab.py` — **25 tests** :

- **Config** : défauts, roundtrip, booléens depuis string.
- **Workspace** : layout isolé, read/write, **fuite de chemin bloquée**,
  **chemin host absolu bloqué**, **allowlist commandes**, **RAW immuable**,
  **append JSONL**.
- **Générateur** : `pytest` réel sur **chaque** template (fibonacci, factorial,
  is_prime, palindrome, reverse_string) — preuve (règle 5) ; détection de plan ;
  fallback generic ; plan inconnu lève.
- **Engine E2E (milestone)** : run fibonacci **passed**, plan détecté, fichiers
  créés, `tests_last_passed`, validation déterministe, **judge "unavailable"**
  (règle 15), événements observables (règle 14), **RAW persistance immuable**,
  isolation au workspace.
- **Controller** : create/list/get, stop inconnu, run synchrone, read/list files.

Suite complète : **384 passed** (les 10 échecs restants sont
`test_model_pool.py` → module `hermes_debate` absent, **pré-existant et hors
périmètre**, déjà documenté avant Code Lab).

---

## 8. Diagramme Mermaid du pipeline réel

```mermaid
flowchart TD
    U[Utilisateur] -->|prompt| UI[Onglet Code Lab / API]
    UI -->|POST /api/code-lab/runs| CTL[CodeLabController]
    CTL --> ENG[CodeLabEngine]
    ENG --> PLAN[PLANNER: detect_plan]
    PLAN --> RTR[SmartRouter.route → deterministic_coder]
    RTR --> DEV[DEVELOPER: generator]
    DEV --> WS[Workspace isolé: src + tests]
    WS --> VER[VERIFIER: pytest réel]
    VER -->|PASS| VAL[VALIDATE: compile() déterministe]
    VER -->|FAIL| CRIT[CRITIC + REPAIR]
    CRIT -->|re-teste, borné| VER
    VAL --> RAW[RawDebateRecorder + raw immuable]
    RAW --> RES[RESULT → UI / API]
    LLM{LM Studio down} -. llm_available=false .-> RES
    style LLM fill:#fbb,stroke:#c00
```

---

## 9. Limites actuelles (honnêtes)

1. **Pas de branchement LLM actif** — `DebateEngine` exige LM Studio (down).
   Aucun faux tour LLM injecté.
2. **JudgeAgent absent du chemin utilisé** — rapporté, non simulé.
3. **Génération déterministe par templates** — V1 couvre les tâches bien
   définies ; les prompts hors patron tombent sur un scaffold `generic` marqué
   non vérifié.
4. **Réparation conservatrice** — aucun patch non éprouvé automatiquement.
5. **Autopilot / Settings** : onglets présents, surface de contrôle UI non
   câblée (placé dans un composant déjà existant `autopilot/`).
6. **Persistance des runs** en session (pas de DB pérenne) — RAW écrit sur
   disque, l'index de runs est en mémoire.

---

## 11. Intégration multi-agent réelle (ajout 2026-10-09)

Une couche **multi-agents LLM réel** a été ajoutée à Code Lab et Autopilot,
réutilisant le stable core existant (règle 3 — pas de second moteur) :

### Code Lab — pipeline multi-agents réel (quand LLM joignable)

```
Prompt
  ↓
CodeLabEngine._execute
  ↓ if config.multi_agent AND llm_available:
CodingMultiAgent (réutilise LLMClient + ModelConfig)
  → AGENT_SELECTED [PLANNER, DEVELOPER, CRITIC, REVIEWER, JUDGE]
  → PLANNER.plan()
  → DEVELOPER.develop()  → _extract_python_blocks() → fichier réel dans workspace
  → VERIFIER: pytest RÉEL
  → sur FAIL: CRITIC.critique() → patch appliqué au fichier réel
  → REPEAT borné (max_iterations, timeout, user stop)
  → REVIEWER.review() + JUDGE.judge() après passage déterministe
  → VALIDATE: compile() (autorité)
  → RAW (trajectoire, snapshots immuables)
```

### Autopilot — adaptateur LLM (réutilise le même bottleneck)

`experiments/runner.py::run_task_with_llm_verifier(...)` + `experiments/llm_adapter.py` :
la tâche passe TOUJOURS par le chemin déterministe existant
(SmartRouter → ToolWorker → validation). L'adaptateur y ajoute une **opinion
Judge séparée** (`metadata.judge_opinion`) qui **ne peut jamais** remplacer le
`validation_result` déterministe (règle 6).

### Gating honnête (règle 4/15)

`code_lab/multiagent.py::probe_llm()` vérifie réellement le backend. Si
injoignable ou token 401, `llm_available=False` → le run est **explicitement**
`execution_mode: "deterministic"` — jamais déguisé en multi-agent. Les tests
LLM d'intégration sont en `skip` tant que le backend n'est pas authentifié.

### Activation

```
# LM Studio → Developer → Local Server → API key
# copier le token dans .env (git-ignoré) :
LIFE_MEAN_LLM_BASE_URL=http://localhost:1234/v1
LIFE_MEAN_LLM_API_KEY=<token valide>
# puis relancer le dashboard. probe_llm() passera, et les tests TestLive* s'exécuteront.
```

Modèles assignés via `ModelConfig.get_model(role)` (config existante) — **pas de
hardcoding** Mellum=dev, Phi=critic, etc. (règle 13).


## 10. Composants NON réutilisés (délibéré)

- `DebateEngine` (dépend du LLM, down) — branchage futur.
- `JudgeAgent` hermes-debate (module non importable) — documenté.
- Pas de second orchestrateur/router/judge/validateur créé (règle 3).
