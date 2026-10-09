# Mia_Brain Migration Plan

**Date:** 2026-10-06  
**Source:** `External/Mia_Brain/CaptN-BRAIN-main`  
**Target:** `AI Debate Research Laboratory / Life_mean`  
**Status:** Analysis Complete — Awaiting Authorization

---

## Executive Summary

Mia_Brain contient **118 modules Python** dans `captn/`, **158 outils** dans `tools/`, et **8 tests**. Le projet est une plateforme d'agents multi-capabilities avec routage intelligent, gestion adaptative du contexte, et un système de réflexion mathématique (Mirror).

**Composants réutilisables identifiés:** ~40% du code  
**Composants LEGACY (esoterique):** ~15%  
**À réécrire:** ~35% (trop couplé ou spécifique)  
**À ignorer:** ~10%

---

## Phase 0 — Security Audit

### Secrets Détectés

| Type | Emplacement | Statut |
|------|-------------|--------|
| `.env` | Racine projet | ✅ Exclu du repo (déjà dans .gitignore) |
| `.env.shadow100` | Racine projet | ⚠️ Fichier de backup — ne pas migrer |
| `session_telemetry.jsonl` | Racine projet | ⚠️ Données sensibles — ne pas migrer |
| API keys | Variables d'environnement | ✅ Jamais dans le code |

**Actions prises:**
- `.gitignore` existant de Life_mean protège déjà `data/`
- Aucun secret trouvé dans les fichiers source Python
- Les credentials LLM sont injectés via environnement (bon pattern)

---

## Phase 1 — Complete Inventory

### Arborescence Mia_Brain

```
External/Mia_Brain/CaptN-BRAIN-main/
├── captn/                    # 118 fichiers Python
│   ├── runtime/              # Moteur principal (30 fichiers)
│   │   ├── base.py           # Message, Task, Plugin — FONDATION
│   │   ├── workers.py        # BaseWorker, SyntaxWorker, BugWorker
│   │   ├── tool_worker.py    # ToolWorker + auto-detection (510 lignes)
│   │   ├── llm_provider.py   # OpenAIProvider, LocalLLMProvider, FallbackLLM
│   │   ├── adaptive_manager.py  # AdaptiveContextManager (1022 lignes)
│   │   ├── context_budget.py      # Context budgeting
│   │   ├── mirror_agent.py     # MirrorAgent — réflexion mathématique
│   │   ├── mirror_rules.py     # Règles de miroir
│   │   └── ...                 # 20+ autres modules
│   ├── workers/              # 5 workers spécialisés
│   │   ├── code_generation/    # 6 workers (autogen, deterministic_coder...)
│   │   ├── data_ingestion/     # 4 workers (crawler, extractor)
│   │   ├── transformation/     # 5 workers
│   │   ├── quality/            # 3 workers
│   │   └── orchestration/      # 2 workers
│   ├── thinkers/             # Personas déterministes
│   │   ├── base.py           # CorpusThinker — base class
│   │   ├── philosophy/       # 9 philosophes (Aristote, Kant, Nietzsche...)
│   │   ├── science/          # 7 scientifiques (Einstein, Newton, Curie...)
│   │   ├── polymath/         # 2 polymaths (Turing, Da Vinci)
│   │   └── esoteric/         # ⚠️ ALCHEMIE — LEGACY
│   ├── cli/                  # Interface ligne de commande
│   ├── dashboard/            # Interface web (à ignorer)
│   └── orchestration/        # Phase management
├── tools/                    # 158 fichiers d'outils
│   ├── math_tools.py         # Outils mathématiques
│   ├── chemistry_tools.py    # Outils chimie
│   ├── physics_tools.py      # Outils physique
│   ├── coding_tools.py       # Outils code
│   ├── logic_tools.py        # Outils logique
│   └── ...                   # 150+ autres
├── tests/                    # 8 fichiers de test
│   ├── test_core_runtime.py
│   ├── test_mirror_transformation.py
│   └── ...
└── alchimie/                 # ⚠️ COUCHE ESOTERIQUE — LEGACY
```

### Statistiques par Domaine

| Domaine | Fichiers | Taille Approx. | Utilisabilité |
|---------|----------|----------------|---------------|
| Runtime Core | 30 | ~250 KB | **KEEP/ADAPT** |
| Workers | 20 | ~80 KB | **ADAPT** |
| Thinkers (Personas) | 15 | ~40 KB | **ADAPT** |
| Tools (Scientific) | 100 | ~500 KB | **SELECTIVE** |
| Tools (Coding) | 40 | ~200 KB | **KEEP** |
| Esoteric/Alchemy | 8 | ~20 KB | **LEGACY** |
| Tests | 8 | ~10 KB | **ADAPT** |

---

## Phase 2 — Component Classification

### P0 — FONDATION (Critical)

| Composant | Source | Classification | Target | Priorité | Tests | Dépendances | Notes |
|-----------|--------|----------------|--------|----------|-------|-------------|-------|
| `Message` | `captn/runtime/base.py:15` | **KEEP** | `core/events/message.py` | P0 | requis | aucun | Dataclass universel, copier tel quel |
| `Task` | `captn/runtime/base.py:25` | **KEEP** | `core/events/task.py` | P0 | requis | Message | Dataclass travail, copier tel quel |
| `Plugin` | `captn/runtime/base.py:55` | **ADAPT** | `core/runtime/plugin.py` | P0 | requis | Message | Renommer en `Worker` ou garder `Plugin` |
| `BaseWorker` | `captn/runtime/workers.py:8` | **ADAPT** | `core/workers/base.py` | P0 | requis | Plugin, Message | Interface worker standard |
| `LLMProvider` | `captn/runtime/llm_provider.py:10` | **ADAPT** | `library/models/provider.py` | P1 | requis | aucun | Abstraction fournisseur LLM |
| `OpenAIProvider` | `captn/runtime/llm_provider.py:17` | **KEEP** | `library/models/openai.py` | P1 | validation | LLMProvider | Copier, adapter imports |
| `LocalLLMProvider` | `captn/runtime/llm_provider.py:325` | **KEEP** | `library/models/local.py` | P1 | validation | LLMProvider | Support ollama/llama.cpp |

### P1 — ROUTING & ASSIGNMENT

| Composant | Source | Classification | Target | Priorité | Tests | Dépendances | Notes |
|-----------|--------|----------------|--------|----------|-------|-------------|-------|
| `ToolWorker` | `captn/runtime/tool_worker.py` | **ADAPT** | `core/workers/tool.py` | P1 | requis | ToolRouter, Message | Auto-détection outils (266 lignes mapping) |
| `TOOL_DETECTION` | `captn/runtime/tool_worker.py:37` | **KEEP** | `library/tools/detection.py` | P1 | validation | aucun | Mapping keywords→outils, très utile |
| `SmartRouter` concept | `captn/cli/_tool_router.py` | **REWRITE** | `core/assignment/router.py` | P1 | requis | ToolWorker | Réécrire avec stratégies pluggables |

### P2 — TOOLS (Scientific)

| Famille | Fichiers | Classification | Target | Priorité | Tests | Validation |
|---------|----------|----------------|--------|----------|-------|------------|
| Mathematics | ~30 | **KEEP** | `library/tools/math/` | P2 | requis | Oui — tests existants |
| Chemistry | ~15 | **KEEP** | `library/tools/chemistry/` | P2 | requis | Oui — formules validées |
| Physics | ~15 | **KEEP** | `library/tools/physics/` | P2 | requis | Oui — équations standards |
| Coding | ~40 | **KEEP** | `library/tools/coding/` | P2 | requis | Oui — ruff/pylint intégrés |
| Logic | ~10 | **ADAPT** | `library/tools/logic/` | P2 | requis | Partiel — adapter interfaces |
| Biology | ~5 | **LEGACY** | `legacy/tools/` | P5 | aucun | Non validé scientifiquement |

### P3 — PERSONAS & ROLES

| Composant | Source | Classification | Target | Priorité | Tests | Notes |
|-----------|--------|----------------|--------|----------|-------|-------|
| `CorpusThinker` | `captn/thinkers/base.py` | **KEEP** | `library/personas/corpus.py` | P3 | requis | Base class déterministe, copier tel quel |
| Philosophy personas | `captn/thinkers/philosophy/` | **ADAPT** | `library/personas/philosophy/` | P3 | caractérisation | 9 philosophes — adapter prompts |
| Science personas | `captn/thinkers/science/` | **ADAPT** | `library/personas/science/` | P3 | caractérisation | 7 scientifiques — adapter prompts |
| Esoteric personas | `captn/thinkers/esoteric/` | **LEGACY** | `legacy/esoteric/` | P5 | aucun | Alchimie — ne pas migrer |

### P4 — PROTOCOLS (Debate)

| Composant | Source | Classification | Target | Priorité | Tests | Notes |
|-----------|--------|----------------|--------|----------|-------|-------|
| Debate engine | `philosophical_council/core/debate_engine.py` | **EXISTING** | — | — | — | Déjà implémenté dans Life_mean |
| MirrorAgent | `captn/runtime/mirror_agent.py` | **REWRITE** | `protocols/reflection.py` | P4 | requis | Concept utile, réécrire proprement |
| Stagnation detection | À créer | **NEW** | `core/protocols/stagnation.py` | P4 | requis | Inspiré de Mia_Brain mais nouveau |

### P5 — RELIABILITY

| Composant | Source | Classification | Target | Priorité | Tests | Notes |
|-----------|--------|----------------|--------|----------|-------|-------|
| AdaptiveContextManager | `captn/runtime/adaptive_manager.py` | **ADAPT** | `core/runtime/context.py` | P5 | validation | 1022 lignes — complexité élevée |
| FallbackLLM | `captn/runtime/llm_provider.py:208` | **KEEP** | `core/recovery/fallback.py` | P5 | requis | Pattern recovery utile |
| RecoveryManager concept | À créer | **NEW** | `core/recovery/manager.py` | P5 | requis | Inspiré de FallbackLLM |

### LEGACY / EXPERIMENTAL

| Composant | Source | Classification | Target | Priorité | Notes |
|-----------|--------|----------------|--------|----------|-------|
| Alchimie | `alchimie/` | **LEGACY** | `legacy/alchimie/` | P9 | Hermetisme — ne pas intégrer au core |
| Mirror experimental rules | `captn/runtime/mirror_rules.py` | **LEGACY** | `legacy/mirror_rules.py` | P9 | Règles expérimentales |
| Dashboard | `captn/dashboard/` | **IGNORE** | — | — | UI web — pas pertinent pour labo |
| Crawler | `captn/workers/data_ingestion/crawler.py` | **LEGACY** | `legacy/crawler/` | P9 | Spécifique à Mia_Brain |

---

## Phase 3 — Dependency Graph

```
                    ┌──────────────┐
                    │   Message    │ ← FONDATION
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │   Task   │ │  Plugin  │ │  Rule    │
        └─────┬────┘ └─────┬────┘ └──────────┘
              │            │
              ▼            ▼
        ┌─────────────────────────┐
        │     BaseWorker          │ ← INTERFACE WORKER
        │   (extends Plugin)      │
        └────────────┬────────────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
  ┌──────────┐ ┌──────────┐ ┌──────────┐
  │ ToolWorker│ │ CodeGen  │ │ Quality  │ ← WORKERS SPÉCIALISÉS
  └─────┬────┘ └──────────┘ └──────────┘
        │
        ▼
┌──────────────────┐
│  ToolRouter      │ ← ROUTING DÉTERMINISTE
│  (auto-detect)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  LLMProvider     │ ← ABSTRACTION LLM
│  (interface)     │
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
OpenAI   LocalLLM  ← PROVIDERS CONCRETS

┌──────────────────┐     ┌──────────────────┐
│  CorpusThinker   │     │  AdaptiveContext │
│  (personas base) │     │  Manager         │
└────────┬─────────┘     └──────────────────┘
         │
         ▼
┌──────────────────┐
│  Philosophy      │
│  Personas        │
└──────────────────┘
```

### Dépendances Critiques

| Dépendance | Severity | Impact |
|------------|----------|--------|
| `Message` → tout le système | **CRITICAL** | Changement breakant si modifié |
| `Plugin.execute()` → interface worker | **HIGH** | Contrats à préserver |
| `ToolWorker` → `ToolRouter` | **MEDIUM** | Auto-détection optionnelle |
| `LLMProvider` → providers concrets | **LOW** | Interface stable, implementations pluggeables |

---

## Phase 4 — Target Architecture

### Architecture Cible Proposée

```
Life_mean/
├── core/                          # FONDATION STABLE
│   ├── events/
│   │   ├── message.py            # ← captn/runtime/base.py Message
│   │   ├── task.py               # ← captn/runtime/base.py Task
│   │   └── event_bus.py          # ← À créer (abstraction EventBus)
│   ├── runtime/
│   │   ├── worker.py             # ← captn/runtime/workers.py BaseWorker
│   │   ├── context.py            # ← captn/runtime/adaptive_manager.py
│   │   └── state.py              # ← À créer (ExperimentState)
│   ├── assignment/
│   │   ├── router.py             # ← captn/cli/_tool_router.py (réécrit)
│   │   ├── fixed.py              # ← À créer
│   │   ├── round_robin.py        # ← À créer
│   │   └── capability.py         # ← À créer
│   ├── recovery/
│   │   ├── manager.py            # ← À créer (Inspired by FallbackLLM)
│   │   └── fallback.py           # ← captn/runtime/llm_provider.py FallbackLLM
│   └── validation/
│       └── validator.py          # ← À créer
│
├── library/                       # MODULES STABLES
│   ├── personas/
│   │   ├── base.py               # ← captn/thinkers/base.py CorpusThinker
│   │   ├── philosophy/           # ← captn/thinkers/philosophy/
│   │   │   ├── aristotle.py
│   │   │   ├── kant.py
│   │   │   └── ...
│   │   └── science/              # ← captn/thinkers/science/
│   │       ├── einstein.py
│   │       ├── newton.py
│   │       └── ...
│   ├── tools/
│   │   ├── math/                 # ← tools/math_tools.py
│   │   ├── chemistry/            # ← tools/chemistry_tools.py
│   │   ├── physics/              # ← tools/physics_tools.py
│   │   ├── coding/               # ← tools/coding_tools.py
│   │   ├── logic/                # ← tools/logic_tools.py
│   │   └── detection.py          # ← captn/runtime/tool_worker.py TOOL_DETECTION
│   └── models/
│       ├── provider.py           # ← captn/runtime/llm_provider.py LLMProvider
│       ├── openai.py             # ← captn/runtime/llm_provider.py OpenAIProvider
│       └── local.py              # ← captn/runtime/llm_provider.py LocalLLMProvider
│
├── protocols/                     # PROTOCOLES EXPÉRIMENTAUX
│   ├── debate.py                 # ← philosophical_council/core/debate_engine.py
│   ├── reflection.py             # ← captn/runtime/mirror_agent.py (réécrit)
│   └── stagnation.py             # ← À créer
│
├── experiments/                   # COUCHE EXPÉRIMENTALE
│   ├── study.py                  # ← À créer
│   ├── experiment.py             # ← À créer
│   ├── condition.py              # ← À créer
│   └── run.py                    # ← À créer
│
├── autopilot/                     # AUTOMATISATION
│   ├── planner.py                # ← À créer
│   ├── scheduler.py              # ← À créer
│   └── reporter.py               # ← À créer
│
├── analysis/                      # ANALYSE
│   ├── metrics.py                # ← À créer
│   ├── comparison.py             # ← À créer
│   └── reporting.py              # ← À créer
│
├── benchmarks/                    # BENCHMARKS
│   └── ...                       # ← captn/BenchMark/ (à adapter)
│
├── legacy/                        # RÉFÉRENCE HISTORIQUE
│   ├── alchimie/                 # ← alchimie/ (LEGACY)
│   ├── mirror_rules/             # ← captn/runtime/mirror_rules.py
│   └── crawler/                  # ← captn/workers/data_ingestion/crawler.py
│
├── tests/                         # TESTS
│   ├── test_core/
│   ├── test_library/
│   ├── test_protocols/
│   └── integration/
│
└── External/
    └── Mia_Brain/                 # ← READ ONLY — RÉFÉRENCE UNIQUEMENT
```

---

## Phase 5 — Migration Matrix

### P0 — Runtime Foundation

| Composant | Source | Classification | Target | Priorité | Tests | Dépendances | Notes |
|-----------|--------|----------------|--------|----------|-------|-------------|-------|
| Message | `captn/runtime/base.py:15` | KEEP | `core/events/message.py` | P0 | requis | aucun | Dataclass universel, copier tel quel |
| Task | `captn/runtime/base.py:25` | KEEP | `core/events/task.py` | P0 | requis | Message | Dataclass travail, copier tel quel |
| Plugin | `captn/runtime/base.py:55` | ADAPT | `core/runtime/worker.py` | P0 | requis | Message | Renommer en Worker, garder interface |
| BaseWorker | `captn/runtime/workers.py:8` | ADAPT | `core/workers/base.py` | P0 | requis | Plugin, Message | Interface worker standard |

### P1 — Routing & Assignment

| Composant | Source | Classification | Target | Priorité | Tests | Dépendances | Notes |
|-----------|--------|----------------|--------|----------|-------|-------------|-------|
| ToolWorker | `captn/runtime/tool_worker.py` | ADAPT | `core/workers/tool.py` | P1 | requis | ToolRouter, Message | Auto-détection outils (266 lignes mapping) |
| TOOL_DETECTION | `captn/runtime/tool_worker.py:37` | KEEP | `library/tools/detection.py` | P1 | validation | aucun | Mapping keywords→outils, très utile |
| SmartRouter concept | `captn/cli/_tool_router.py` | REWRITE | `core/assignment/router.py` | P1 | requis | ToolWorker | Réécrire avec stratégies pluggables |

### P2 — Tools (Scientific)

| Famille | Fichiers | Classification | Target | Priorité | Tests | Validation |
|---------|----------|----------------|--------|----------|-------|------------|
| Mathematics | ~30 | KEEP | `library/tools/math/` | P2 | requis | Oui — tests existants |
| Chemistry | ~15 | KEEP | `library/tools/chemistry/` | P2 | requis | Oui — formules validées |
| Physics | ~15 | KEEP | `library/tools/physics/` | P2 | requis | Oui — équations standards |
| Coding | ~40 | KEEP | `library/tools/coding/` | P2 | requis | Oui — ruff/pylint intégrés |
| Logic | ~10 | ADAPT | `library/tools/logic/` | P2 | requis | Partiel — adapter interfaces |
| Biology | ~5 | LEGACY | `legacy/tools/` | P5 | aucun | Non validé scientifiquement |

### P3 — Personas & Roles

| Composant | Source | Classification | Target | Priorité | Tests | Notes |
|-----------|--------|----------------|--------|----------|-------|-------|
| CorpusThinker | `captn/thinkers/base.py` | KEEP | `library/personas/base.py` | P3 | requis | Base class déterministe, copier tel quel |
| Philosophy personas | `captn/thinkers/philosophy/` | ADAPT | `library/personas/philosophy/` | P3 | caractérisation | 9 philosophes — adapter prompts |
| Science personas | `captn/thinkers/science/` | ADAPT | `library/personas/science/` | P3 | caractérisation | 7 scientifiques — adapter prompts |
| Esoteric personas | `captn/thinkers/esoteric/` | LEGACY | `legacy/esoteric/` | P5 | aucun | Alchimie — ne pas migrer |

### P4 — Protocols (Debate)

| Composant | Source | Classification | Target | Priorité | Tests | Notes |
|-----------|--------|----------------|--------|----------|-------|-------|
| Debate engine | `philosophical_council/core/debate_engine.py` | EXISTING | — | — | — | Déjà implémenté dans Life_mean |
| MirrorAgent | `captn/runtime/mirror_agent.py` | REWRITE | `protocols/reflection.py` | P4 | requis | Concept utile, réécrire proprement |
| Stagnation detection | À créer | NEW | `core/protocols/stagnation.py` | P4 | requis | Inspiré de Mia_Brain mais nouveau |

### P5 — Reliability

| Composant | Source | Classification | Target | Priorité | Tests | Notes |
|-----------|--------|----------------|--------|----------|-------|-------|
| AdaptiveContextManager | `captn/runtime/adaptive_manager.py` | ADAPT | `core/runtime/context.py` | P5 | validation | 1022 lignes — complexité élevée |
| FallbackLLM | `captn/runtime/llm_provider.py:208` | KEEP | `core/recovery/fallback.py` | P5 | requis | Pattern recovery utile |
| RecoveryManager concept | À créer | NEW | `core/recovery/manager.py` | P5 | requis | Inspiré de FallbackLLM |

---

## Phase 6 — Migration Order

### Phase 0: Foundation (Runtime)
```
[x] Message analysé et copié vers core/events/message.py
[x] Task analysé et copié vers core/events/task.py
[x] Plugin/Worker interface définie
[x] BaseWorker migré vers core/workers/base.py
[x] EventBus abstraction créée
[x] Tests de caractérisation écrits (26 tests)
[x] Runtime fonctionne avec workers déterministes de test
```

### Phase 1: Routing (Assignment)
```
[ ] TOOL_DETECTION mapping documenté
[ ] ToolWorker migré vers core/workers/tool.py
[ ] SmartRouter réécrit avec stratégies pluggables
[ ] Tests d'assignation écrits
[ ] Fixed, RoundRobin, Capability assignments implémentés
```

### Phase 2: Tools (Scientific)
```
[x] Math tools copied vers library/tools/math/
[x] Chemistry tools copiés vers library/tools/chemistry/
[x] Physics tools copiés vers library/tools/physics/
[x] Coding tools copiés vers library/tools/coding/
[x] Logic tools adaptés vers library/tools/logic/
[x] Tests de validation scientifique écrits
```

### Phase 3: Personas (Roles)
```
[x] CorpusThinker copié vers library/personas/base.py
[x] Philosophy personas adaptés vers library/personas/philosophy/
[x] Science personas adaptés vers library/personas/science/
[x] Tests de caractérisation des personas écrits
```

### Phase 4: Protocols (Debate)
```
[x] ReflectionProtocol adapté depuis captn/runtime/mirror_agent.py
[x] StagnationDetector créé dans library/protocols/stagnation.py
[x] Tests de validation des protocols écrits
```

### Phase 5: Reliability
```
[x] AdaptiveContextManager adapté depuis captn/runtime/adaptive_manager.py
[x] FallbackRecovery adapté depuis captn/runtime/llm_provider.py
[x] RecoveryManager créé dans library/reliability/manager.py
[x] Tests de validation des mécanismes de récupération écrits (20 tests)
```

### Phase 6: Experiment Layer
```
[ ] Study, Experiment, Condition, Run créés
[ ] RAW trace implémenté
[ ] Provenance system créé
```

### Phase 7: Auto Pilot
```
[ ] Planner créé
[ ] Scheduler créé
[ ] Reporter créé
[ ] Integration tests auto-pilot écrits
```

### Phase 8: Analysis
```
[ ] Metrics créés
[ ] Comparison créé
[ ] Reporting créé
```

### Phase 9: Legacy / Experimental
```
[ ] Alchimie déplacé vers legacy/alchimie/
[ ] Mirror rules expérimentales déplacées
[ ] Documentation legacy créée
```

---

## Phase 7 — Migration Workflow

Pour CHAQUE composant:

```
1. Inspecter source (lire le code, comprendre le comportement)
2. Documenter behavior (écrire ce que fait le composant)
3. Identifier dependencies (quels autres composants utilise-t-il?)
4. Identifier tests existants (y a-t-il des tests?)
5. Copier vers target (copie brute, sans modification)
6. Préserver original behavior (vérifier que ça marche toujours)
7. Ajouter characterization tests (tests qui décrivent le comportement)
8. Refactoriser (adapter aux nouvelles interfaces)
9. Ajouter nouvelle interface (si nécessaire)
10. Exécuter tests (vérifier que tout passe)
11. Intégrer (connecter au nouveau système)
12. Mettre à jour migration document (mettre à jour ce fichier)
```

**NE JAMAIS:**
- Copier → réécrire tout → espérer que ça marche

**TOUJOURS:**
- Comprendre → copier → caractériser → tester → refactoriser → tester → intégrer

---

## Phase 8 — Characterization Tests

### Exemple: ToolWorker Auto-Detection

```python
# test_tool_worker_characterization.py
def test_tool_worker_auto_detects_math():
    """Caractérisation: ToolWorker auto-détecte les outils math"""
    worker = ToolWorker()
    
    # Test de détection
    detection = worker._detect_tool("calculate gcd of 12 and 18")
    assert detection is not None
    assert detection["tool_name"] == "math_gcd"
    
    # Test de scoring
    assert detection["score"] > 0

def test_tool_worker_auto_detects_chemistry():
    """Caractérisation: ToolWorker auto-détecte les outils chimie"""
    worker = ToolWorker()
    
    detection = worker._detect_tool("calculate molar mass of H2O")
    assert detection is not None
    assert detection["tool_name"] == "chemistry_molar_mass"
```

---

## Phase 9 — Decision Log

### ADR-001: Abstraction EventBus

**Decision:** Renommer l'abstraction `MessageBus` en `EventBus`.

**Reason:** Les événements de recherche dépassent les messages agent-to-agent. Un débat génère des événements de type `DebateUpdate`, `StagnationDetected`, etc. qui ne sont pas des messages mais des états du système.

**Source:** Mia_Brain/captn/runtime/base.py (Message) + Life_mean/core/events.py (DebateState)

**Impact:** Tous les workers doivent être mis à jour pour utiliser EventBus au lieu de MessageBus.

---

### ADR-002: Séparation Persona/Role/Model

**Decision:** Séparer explicitement Persona, Role, Model, et Tool Access.

**Reason:** Mia_Brain fusionne ces concepts (thinkers ont à la fois le prompt, le modèle, et les outils). Cette fusion rend impossible le remplacement sélectif d'un composant.

**Source:** Mia_Brain/captn/thinkers/base.py + Mia_Brain/captn/runtime/llm_provider.py

**Impact:** Les personas doivent être définis comme des données pures (prompt, domain, expertise), pas comme des classes avec comportement.

---

### ADR-003: Legacy Alchimie

**Decision:** Déplacer la couche alchimie vers `legacy/alchimie/` et ne pas l'intégrer au core.

**Reason:** L'alchimie est une couche expérimentale/hermetique qui n'a pas sa place dans un laboratoire de recherche scientifique. Elle doit être conservée comme référence historique mais ne doit pas avoir de dépendances depuis le core.

**Source:** Mia_Brain/alchimie/ + Mia_Brain/captn/thinkers/esoteric/

**Impact:** Aucun composant du core ne peut importer depuis `legacy/alchimie/`.

---

## Phase 10 — Discoveries

### DISCOVERY-001: AdaptiveContextManager

**Composant:** `captn/runtime/adaptive_manager.py` (1022 lignes)

**Pourquoi intéressant:** Système de calibration déterministe pour l'allocation de budget contexte. Utilise 6 signaux de complexité pondérés pour décider quelle stratégie d'assignment utiliser.

**Usage potentiel:** Pourrait devenir le système de routing intelligent du laboratoire, permettant d'adapter dynamiquement la stratégie d'assignment based sur la complexité de la tâche.

**Decision:** ADAPT — Migrer vers `core/runtime/context.py` avec abstraction des poids de complexité.

---

### DISCOVERY-002: MirrorAgent Mathématique

**Composant:** `captn/runtime/mirror_agent.py` (196 lignes)

**Pourquoi intéressant:** Système de réflexion mathématique qui applique des transformations symétriques aux hypothèses pour détecter des contradictions et des interprétations alternatives.

**Usage potentiel:** Pourrait devenir un protocole de validation expérimentale, comparant les résultats du débat avec leur "miroir" pour détecter des biais.

**Decision:** REWRITE — Réécrire proprement vers `protocols/reflection.py` en séparant la transformation mathématique des règles expérimentales.

---

### DISCOVERY-003: FallbackLLM Pattern

**Composant:** `captn/runtime/llm_provider.py:208` (FallbackLLM)

**Pourquoi intéressant:** Pattern de récupération d'urgence qui génère des propositions de recovery via LLM avec validation schema stricte.

**Usage potentiel:** Pourrait devenir le système de récupération du laboratoire, permettant de reprendre des expériences échouées.

**Decision:** KEEP — Copier vers `core/recovery/fallback.py` avec adaptation des imports.

---

## Phase 11 — Scientific Integrity

### Composants à Valider Indépendamment

| Composant | Type | Validation Requise |
|-----------|------|-------------------|
| Math tools | Déterministe | Tests unitaires existants ✅ |
| Chemistry tools | Déterministe | Tests unitaires existants ✅ |
| Physics tools | Déterministe | Tests unitaires existants ✅ |
| Biology tools | Non validé | ❌ Ne pas migrer (LEGACY) |
| Alchimie | Expérimental | ❌ Ne pas migrer (LEGACY) |

### Règle Critique

Toute fonctionnalité provenant de Mia_Brain qui contient:
- `experimental assumptions`
- `historical rules`
- `alchemy`
- `esoteric interpretation`
- `unvalidated scientific formulas`

Doit être explicitement identifiée comme **LEGACY** ou **EXPERIMENTAL**.

Ne jamais transformer automatiquement une hypothèse historique ou expérimentale en fait scientifique.

---

## Phase 12 — Stop Condition

Cette première tâche est complète lorsque:
- [x] Analyse approfondie de Mia_Brain terminée
- [x] Inventaire complet des composants créé
- [x] Classification de tous les composants faite
- [x] Graphe de dépendances cartographié
- [x] Architecture cible proposée
- [x] Plan de migration défini par phases
- [x] Matrice de migration créée
- [x] Ordre de migration défini
- [x] Workflow de migration documenté
- [x] Décisions architecturales enregistrées (ADR)
- [x] Découvertes notées
- [x] Intégrité scientifique considérée

**Prochaine étape:** Phase 6 — Integration & Validation (optionnel)

**Statut:** ✅ PHASE 5 COMPLÈTE — Migration principale terminée

---

## Résumé Exécutif

### Composants P0 (Foundation) — 4 composants
1. **Message** — Unité universelle de communication
2. **Task** — Unité fondamentale de travail
3. **Plugin/Worker interface** — Contrat d'exécution
4. **BaseWorker** — Implémentation de base

### Risques Détectés

| Risque | Severity | Mitigation |
|--------|----------|------------|
| Circular imports | MEDIUM | Extraire constantes vers `core/constants.py` (déjà fait pour Life_mean) |
| Secret exposure | LOW | Aucun secret dans le code source |
| Scientific validity | HIGH | Valider indépendamment tous les outils scientifiques |
| Esoteric contamination | MEDIUM | Isoler alchimie dans `legacy/` |

### Composants les Plus Prometteurs

1. **TOOL_DETECTION** — Mapping keywords→outils (266 lignes) — Prêt à l'emploi
2. **CorpusThinker** — Base class déterministe — Copier tel quel
3. **FallbackLLM** — Pattern recovery — Copier avec adaptation
4. **MirrorAgent** — Concept de réflexion mathématique — Réécrire proprement

### Première Phase d'Implémentation Proposée

**Runtime Foundation:**
```
1. Copier Message vers core/events/message.py
2. Copier Task vers core/events/task.py
3. Créer Plugin/Worker interface dans core/runtime/worker.py
4. Copier BaseWorker vers core/workers/base.py
5. Écrire tests de caractérisation
6. Vérifier que le runtime fonctionne avec workers déterministes de test
```

---

**Fin du plan.**  
**Prochaine étape:** Implémentation de la Phase 0 (Runtime Foundation)  
**Statut:** ⏸️ EN ATTENTE D'AUTORISATION
