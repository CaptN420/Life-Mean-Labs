# Life-Mean-Labs 🧠

## Adaptive Router v1.1 — Evidence, Benchmark & Architecture Validation Engine

**Question fondamentale :** Combien de tokens peut-on retirer avant que l'agent cesse de prendre la bonne décision ?

---

### Mission

Transformer le routeur adaptatif en un moteur mesurable, reproductible et vérifiable, capable de :

- **Valider** les résultats avec traçabilité complète
- **Benchmark** les stratégies (Déterministe, Computationnel, LLM, Cache)
- **Optimiser** le routage basé sur la fiabilité vs coût
- **Résister** aux pannes et erreurs via fallback intelligent

---

### Architecture

```
CACHE → DETERMINISTIC → COMPUTATIONAL → LLM → ERROR
       ↑___________________________________|
                  Fallback Chain
```

### Classification des Tâches

| Type | Description | Moteur Privilégié |
|------|-------------|-------------------|
| `DETERMINISTIC` | Calcul exact, règles explicites | Déterministe |
| `COMPUTATIONAL` | Simulation, optimisation, numérique | Computationnel |
| `REASONING` | Analyse complexe, multi-étapes | LLM |
| `AMBIGUOUS` | Données insuffisantes, multiples interprétations | LLM + Validation |
| `UNKNOWN` | Indéterminé | Fallback progressif |

### Validation des Résultats

| Statut | Signification |
|--------|---------------|
| `VERIFIED` | Résultat confirmé par les critères de vérification |
| `PARTIAL` | Vérification partielle ou couverture insuffisante |
| `UNVERIFIED` | Aucune vérification indépendante concluante |
| `INVALID` | Résultat contradictoire ou incorrect |

### Moteurs Disponibles

| Moteur | Usage | Coût Relatif |
|--------|-------|--------------|
| `CACHE` | Résultat mis en cache | 0 (gratuit) |
| `DETERMINISTIC` | Calcul exact Python | Faible |
| `COMPUTATIONAL` | Simulation numérique | Moyen |
| `LLM` | Raisonnement langage | Élevé |
| `ERROR` | Aucune stratégie disponible | N/A |

---

### Quick Start

```python
from core.router.adaptive import AdaptiveRouter, EngineType, CostConfig
from core.router.evidence import EvidenceValidator, EvidenceCollector

# Configuration optimisée
router = AdaptiveRouter(
    cost_config=CostConfig(
        reliability_weight=2.0,
        compute_weight=1.0,
        token_weight=0.01,
        latency_weight=0.5,
    ),
    max_fallbacks=3,
)

# Validator avec collecte d'évidence
validator = EvidenceValidator()

# Router une tâche
decision = router.route(
    task_id="task-001",
    description="Calculate gcd of 48 and 180",
    tool_name="math_gcd",
    kwargs={"a": 48, "b": 180},
    llm_available=True,
)

# Analyser les résultats
print(f"Classification: {decision.classification}")
print(f"Moteur sélectionné: {decision.selected_engine}")
print(f"Validation: {decision.validation}")
print(f"Coût estimé: {decision.compute_cost} tokens")
```

---

### Benchmarks

Comparer les stratégies sur tâches identiques :

```python
from core.router.evidence import BenchmarkEngine

benchmark = BenchmarkEngine()

# Exécuter avec différentes stratégies
result_det = benchmark.run_benchmark("task-001", "DETERMINISTIC", deterministic_worker, task)
result_llm = benchmark.run_benchmark("task-001", "LLM", llm_worker, task)

# Comparaison
comparison = benchmark.get_comparison("task-001")
```

---

### Structure du Projet

```
core/router/
├── __init__.py          # Export publics
├── adaptive.py          # Routeur adaptatif v1.1
├── evidence.py          # Couche validation + benchmarks
└── README.md            # Cette documentation

tests/
├── test_adaptive_router.py    # Tests existants (23 pass)
└── test_evidence_layer.py     # Nouveaux tests v1.1
```

---

### Règles de Développement

1. **Ne pas inventer une preuve** — Mesurer, ne pas estimer
2. **Ne pas confondre succès des tests et preuve d'optimalité**
3. **Préserver la reproductibilité** — Chaque benchmark doit être re-exécutable
4. **Distinguer simulation et exécution réelle**
5. **Ne jamais masquer une régression**

---

### Résultats

Les rapports de validation, benchmarks et analyses d'architecture sont enregistrés dans :

```
results/
├── README.md
├── validation/          # Décisions de routage validées
├── benchmarks/          # Comparaisons de stratégies
├── architecture/        # Analyses structurelles
└── traces/              # Journaux d'exécution
```

---

**Principe fondamental :** Une expérience observée n'est pas une preuve de causalité, et un test réussi n'est pas une validation complète de l'architecture.

---

# Life_mean Lab 🧠

*A multi-agent system & synthetic-data laboratory — where machines argue to think, and think to generate.*

**STATUS:** Experimental / active development

**Current milestone:**
✓ Code Lab provenance
✓ reproducible event traces
✓ validators
→ collecting prospective trajectories

**Next research milestone:**
Canonical Context Experiment

**Research question:**
How much context can an agent lose
before it loses the ability to make
the correct next decision?

Life_mean is an exploratory research lab that combines **philosophical multi-agent debate** with a **deterministic synthetic-data pipeline**. At its heart sits a *philosophical council* — agents shaped after real schools of thought — working together on the question of how an AI can build its own training data with both creativity and honesty.

---

## ⚠️ Historique réécrit (2026-10-20) — resynchronisation obligatoire

Une chaîne ressemblant à une clé présente dans l'historique a été purgée via `git filter-repo`.
**Tous les SHAs postérieurs au commit fautif ont changé.** Si vous avez déjà cloné le repo, votre historique local diverge désormais et doit être resynchronisé :

```bash
# Option 1 — resynchroniser le clone existant
git fetch origin main
git reset --hard origin/main

# Option 2 — re-cloner proprement (recommandé si vous avez des branches locales)
#   cd ..
#   rm -rf Life_mean
#   git clone https://github.com/CaptN420/Life_Mean_Labs.git
```

Règles pour tous :
- **Ne jamais** `git push --force` une ancienne branche locale (basée sur un SHA d'avant le rewrite) vers ce repo — elle réintroduirait le secret dans l'historique distant.
- Ne réutilisez **aucun** ancien SHA (ex. `6383e19`, `95d7d01`) dans vos commandes, scripts ou documentation.

---

## 📖 How it came to be

It started with a simple itch: *most synthetic datasets are generated by a single model, in one pass, with no second opinion.*

What if a group of agents — each with a genuinely different worldview — could **debate** each sample before it is accepted? The skeptic pokes holes, the pragmatist asks *"does this actually work?"*, the stoic questions whether it is worth generating at all, the nihilist asks what it even means for a task to be "good". Out of that collision of views, a more rigorous dataset could emerge.

That thought grew into a **lab** rather than a script: a place to experiment with the pipeline end-to-end — generate, solve, validate, fail, learn, revise — while keeping the process *auditable* and the results *reproducible*. Nothing is taken on faith: every claim a model makes must pass a **deterministic check**, and the LLM is treated as an opinion, never as an oracle.

## 🎯 Vision

> **A self-improving data factory**: multi-agent reasoning generates the tasks, a deterministic engine verifies them, and the feedback loop keeps getting sharper — all with a human in the loop, never a black box.

Two principles hold the whole thing together:

- **Deterministic authority** — the machine's verdict is grounded in code and tests, not in a language model's confidence. An LLM can *suggest*; it cannot override a failing check.
- **No silent fallback** — if the LLM backend is down, the system says so honestly. It never quietly pretends to reason.

The philosophical agents are not a gimmick: they exist to *diversify the reasons a task can be difficult*, so the generated data covers failure modes a single "smart" generator would never imagine.

## 🚀 Long-term objective

The endgame is a **data factory** (the `AUTONOMOUS_SYNTHETIC_DATA_GENERATOR` design doc) that, from a prompt, produces a large corpus of vetted tasks across many domains — math today, physics, chemistry and reasoning as the extraction layer matures — with each task:

1. **Generated** by multi-agent synthesis,
2. **Solved** through the existing SmartRouter / ToolWorker core,
3. **Validated** deterministically (tests + compilation),
4. **Exported** in a clean, versioned dataset for training — *keeping generation and training strictly separate, so the lab never pollutes the learner's data*.

The long game is **self-improvement**: the weakness analyzer and curriculum controller (`analysis/` + `autopilot/`) decide *what* to generate next based on where the model is failing, with an **explicit human approval gate** before any model change is promoted. The ambition is a loop that gets better at helping minds grow — its own and others'.

---

## 🧩 What's inside

| Layer | Purpose |
|---|---|
| `philosophical_council/` | Stable multi-agent core: `DebateEngine`, agents (existentialist, nihilist, pragmatist, skeptic, stoic, …), `SmartRouter`, `EventBus`, RAW storage |
| `experiments/` | Deterministic generation / validation / runner layer, `ExperimentConfig`, settings API |
| `code_lab/` | Experimental code-generation layer: PLANNER → generator → real `pytest` → compile validation |
| `role_templates/` | Role & model mapping that *configures* the core — it never replaces it |
| `library/` + `core/` | Tools, personas, protocols, reliability managers |
| `analysis/` + `autopilot/` | Weakness analysis, curriculum controller, model lifecycle (stable / candidate / rejected) |

**Status:** phases 0–9 complete · **713 tests passing** · 12 skipped (external deps) · 2 known failures (`test_runtime_restore.py` — subprocess path issue, pre-existing) · dashboard with Autopilot, Settings & Code Lab tabs.

## 🧪 Provenance & Integrity

The system enforces **deterministic audit trails** for every LLM call:

- **`AGENT_STARTED` → `AGENT_RESPONSE` / `AGENT_FAILED`**: Every agent turn is tracked with a monotonically increasing `trace_index`, ensuring no orphaned events.
- **Provenance hashes**: Each event records `system_prompt_hash`, `sampling_settings_hash`, `input_context_hash`, and `response_hash` — enabling deterministic replay and verification.
- **Model provenance**: Records both `configured_model` (what was asked for) and `actual_model` (what was used), plus `selection_mode` (`configured` / `dynamic` / `backend_default`).
- **Retry integrity**: Failed attempts get their own `trace_index`; successful retries are distinct events.

**Proof**: `tests/test_code_lab_event_provenance.py` validates:
- Balanced event pairs (STARTED = RESPONSE + FAILED)
- Unique trace indices across retries
- Schema completeness (`schema_version`, `collection_contract_version`)
- Real engine runs write valid `events.jsonl`

Run the provenance tests:
```bash
python -m pytest tests/test_code_lab_event_provenance.py -v
# 12 passed — every agent event is accounted for with full metadata
```

## ⚙️ Install & run

Requires Python ≥ 3.10.

```bash
# 1. create a fresh environment and install the package + deps
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -e .

# 2. import check
python -c "import philosophical_council, experiments, code_lab; print('OK')"

# 3. run the deterministic test suite
python -m pytest -q
```

`pyproject.toml` sets `[tool.pytest.ini_options] pythonpath = [".]`, so a fresh environment collects the same tests with no `sys.path` hacks.

## 🔑 LLM / debate notes

- **Deterministic paths run with no live backend.** `openai` (OpenAI-compatible client) is a runtime dependency for LM Studio / OpenRouter, but LLM calls are gated on `probe_llm()` and report availability *honestly* — no fake runs, no silent deterministic fallback under a "Debate" label.
- **Debate mode** requires a live LLM backend (e.g. LM Studio). When it is down, entering Debate mode fails explicitly rather than pretending.
- LLM credentials live in **`.env`** (git-ignored) — see `.env.example`.
- `hermes-debate/` is a **separate project** (`hermes_debate` package) and is intentionally not part of this package.
- RAW evidence is append-only / immutable under `data/` and run workspaces.

## 📜 License

[MIT](LICENSE) © 2026 CaptN420