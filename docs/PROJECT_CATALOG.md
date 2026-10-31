# Life_mean Lab — Catalogue Complet du Projet

**Version:** 1.0  
**Date:** 2026-10-30  
**Status:** Active Development  
**Auteur:** CaptN420

---

## TABLE DES MATIÈRES

1. [Histoire et Origines](#1-histoire-et-origines)
2. [Architecture Globale](#2-architecture-globale)
3. [Couche Philosophique — Le Conseil](#3-couche-philosophique--le-conseil)
4. [Cœur du Système](#4-cœur-du-système)
5. [Couche Expérimentale](#5-couche-expérimentale)
6. [Couche Code Lab](#6-couche-code-lab)
7. [Interface Utilisateur](#7-interface-utilisateur)
8. [Couche Données](#8-couche-données)
9. [Sécurité et Intégrité](#9-sécurité-et-intégrité)
10. [Recherche et Contexte Canonique](#10-recherche-et-contexte-canonique)
11. [Héritage — Les Deux Échecs](#11-héritage--les-deux-échecs)
12. [Architecture Decision Records](#12-architecture-decision-records)
13. [Tests et Validation](#13-tests-et-validation)

---

## 1. Histoire et Origines

### 1.1 Le Contexte Initial

Life_mean Lab est né d'une question simple mais profonde :

> *« Et si un groupe d'agents — chacun avec une vision du monde genuinely différente — pouvait débattre de chaque échantillon avant qu'il ne soit accepté ? »*

L'idée originale venait d'un constat : la plupart des datasets synthétiques sont générés par un seul modèle, en un seul passage, sans second avis. Ce qui produit des biais systémiques invisibles.

### 1.2 Les Deux Échecs Incorporés

Le projet porte en lui les leçons de deux échecs précédents, dont l'essence a été intégrée dans l'architecture :

#### Échec 1 — Mia_Brain / CaptN-BRAIN (Legacy)

**Problème identifié :** Le système précédent (CaptN-BRAIN) était un runtime multi-agent déterministe-first avec ~800 outils, mais il souffrait de :

- **Couplage fort** entre le routeur et les agents — remplacement difficile
- **Absence de traçabilité complète** — les échecs n'étaient pas instrumentés
- **Dépendance implicite** au backend LLM — fallback silencieux plutôt que déclaration explicte
- **Pas de séparation claire** entre code stable et zone expérimentale

**Leçon intégrée :** La séparation stricte Stable/Experimental, les interfaces explicites, et la règle "no silent fallback".

#### Échec 2 — Herme-debate / Orchestrateur TypeScript (Legacy)

**Problème identifié :** L'itération précédente utilisait un orchestrateur TypeScript séparé qui :

- Créait une dépendance implicite entre le système Python et l'orchestrateur
- Ne produisait pas de traces RAW immuables
- Manquait de validation déterministe des résultats

**Leçon intégrée :** L'architecture RAW-first, la séparation données/code, et la validation déterministe comme autorité finale.

### 1.3 L'Émergence du Projet Actuel

Life_mean est né de la synthèse de ces échecs :

- **Principe fondamental :** Les modèles proposent, le système de permission (déterministe) dispose
- **Isolation :** La zone expérimentale est physiquement séparée du stable
- **Traçabilité :** Chaque résultat peut être retracé jusqu'à son code, sa configuration, et ses inputs

---

## 2. Architecture Globale

```
Life_mean/
│
├── philosophical_council/     # [STABLE] Moteur de débat multi-agent
│   ├── core/                  #   Cœur: orchestration, état, événements
│   ├── agents/                #   Agents philosophiques (6 écoles)
│   ├── llm/                   #   Abstraction provider LLM
│   ├── memory/                #   Mémoire multi-niveau
│   ├── database/              #   Persistence SQLite
│   ├── ui/                    #   Couche présentation
│   └── config.py              #   Configuration
│
├── experiments/               # [STABLE] Couche génération/validation
│   ├── engine/                #   Pipeline déterministe
│   └── runner.py              #   Exécution d'expériences
│
├── code_lab/                  # [EXPERIMENTAL] Génération de code
│   ├── multiagent.py          #   Orchestration multi-agent
│   └── compression/           #   Outils de compression
│
├── life_mean_studio/          # [STABLE] Interface GUI PySide6
│   ├── engine/                #   Moteur d'exécution
│   ├── launcher/              #   Démarrage application
│   └── workflows/             #   Workflows UI
│
├── data/                      # [DATA] Couche données séparée
│   ├── raw/                   #   Outputs immuables (JSONL)
│   ├── processed/             #   Résultats dérivés
│   ├── metrics/               #   Mesures quantitatives
│   └── reports/               #   Rapports lisibles
│
├── research/                  # [RESEARCH] Contexte canonique
│   └── canonical_context/     #   Seeds, runs, audits
│
├── tests/                     # [TESTS] Suite complète
│   └── 70+ fichiers de test
│
└── docs/                      # [DOCS] Architecture et ADR
```

### Principes Architecturaux

| Principe | Description |
|----------|-------------|
| **Haute cohésion, faible couplage** | Chaque module a une responsabilité claire |
| **Remplaçabilité** | Tout composant peut être swapé via contrat explicite |
| **Traçabilité** | Chaque résultat trace vers code, config, inputs |
| **Déterministe quand possible** | Cœur déterministe, agents bornés par contrats |
| **Gouvernance humaine** | Promotion expérimentale = décision humaine explicite |

---

## 3. Couche Philosophique — Le Conseil

### 3.1 Les Six Philosophes

Chaque agent implémente `BaseAgent` avec un `AgentConfig` contenant :
- `role`: identifiant unique
- `name`: nom affiché
- `system_prompt`: persona philosophique
- `model`: modèle LLM assigné (optionnel)
- `color`: couleur UI (#RRGGBB)

#### Existentialist (`#9370DB`)
```
Focus: Existence précède l'essence
Liberté, authenticité, absurdité, angoisse comme chemin
"Nous sommes condamnés à être libres"
```

#### Stoic (`#4169E1`)
```
Focus: La vertu comme seul bien vrai
Contrôle vs non-contrôle, memento mori, amor fati
Raison comme principe directeur
```

#### Nihilist (`#DC143C`)
```
Focus: Investigation rigoureuse du sens
Nihilisme passif vs actif, limites épistémologiques
"Explorer ce qui suit du nihilisme, pas juste le déclarer"
```

#### Spiritual (`#228B22`)
```
Focus: Métaphysique et conscience
Possibilités au-delà du matérialisme, mystery of existence
Distinction spéculation vs assertion
```

#### Skeptic (`#FF8C00`)
```
Focus: Challenge des contradictions et hypothèses cachées
Distinguer scepticisme et cynisme
Objectif: vérité, pas victoire
```

#### Pragmatist (`#FFD700`)
```
Focus: Truth as what works in practice
Conséquences pratiques, pont théorie/pratique
"Quelle différence cela ferait-il ?"
```

### 3.2 Le Modérateur

`ModeratorAgent` est un agent spécial qui :
- Ne participe PAS au débat comme débateur
- Sélectionne stratégiquement le prochain locuteur
- Génère des challenges spécifiques
- Produit une sortie JSON structurée

**Modes de parsing (spec §16) :**
1. `DIRECT_JSON` — parse direct réussi
2. `EXTRACTED_JSON` — JSON extrait de markdown code fence
3. `PATTERN_FALLBACK` — recovery par pattern matching
4. `DETERMINISTIC_FALLBACK` — fallback déterministe (échec total)

**Critique importante :** Le modérateur ne rotates PAS simplement — il choisit stratégiquement basé sur :
- Qui peut mieux répondre à l'objection la plus forte
- La détection de répétitions
- L'équilibre de participation (max 2 tours consécutifs)

### 3.3 Agent Configurable (`ConfigurableDebateAgent`)

Générateur générique pour templates RoleTemplate non-philosophiques :
- Role / Persona / Objectives / Constraints
- Jamais de langage "philosophical position" forcé
- Spéc §6.H: wording generic uniquement

---

## 4. Cœur du Système

### 4.1 DebateEngine

Orchestrateur principal du cycle de débat :

```python
class DebateEngine:
    def __init__(self, config, database, llm_client, lab_event_handler=None)
    
    # Cycle de vie
    start_debate() -> None
    run_turn() -> TurnResult
    select_next_speaker() -> str
    complete_turn(agent, response, model, provider) -> None
    
    # Mémoire
    short_term_memory: Any
    mid_term_memory: Any
    long_term_memory: Any
```

**Gestion des événements :**
- `AGENT_STARTED` → `AGENT_RESPONSE` / `AGENT_FAILED`
- Trace index monotonicement croissant
- Provenance hashes (system_prompt, sampling_settings, input_context, response)

### 4.2 TurnManager

Gestion des tours et rounds :
- Séquençage des tours
- Suivi des rounds
- Détection de répétition (`has_repeated_argument`)
- Extraction d'arguments clés

### 4.3 SmartRouter (Core)

Routeur adaptatif v1.1 :
```
CACHE → DETERMINISTIC → COMPUTATIONAL → LLM → ERROR
       ↑___________________________________|
                  Fallback Chain
```

**Classification des tâches :**
| Type | Description | Moteur Privilégié |
|------|-------------|-------------------|
| `DETERMINISTIC` | Calcul exact, règles explicites | Déterministe |
| `COMPUTATIONAL` | Simulation, optimisation, numérique | Computationnel |
| `REASONING` | Analyse complexe, multi-étapes | LLM |
| `AMBIGUOUS` | Données insuffisantes | LLM + Validation |
| `UNKNOWN` | Indéterminé | Fallback progressif |

### 4.4 LLM Client

Abstraction provider :
```python
class LLMClient:
    def chat(messages, model, temperature, max_tokens) -> tuple[str, str]
    def get_models() -> list[str]
    last_model_used: Optional[str]
```

**Provenance tracking :**
- `configured_model` vs `actual_model`
- `selection_mode`: `configured` / `dynamic` / `backend_default`
- `_derive_provider()`: infère "lm-studio", "openai", "anthropic", etc.

---

## 5. Couche Expérimentale

### 5.1 ExperimentConfig

```python
@dataclass
class ExperimentConfig:
    topic: str
    max_rounds: int = 10
    max_turns_per_round: int = 6
    agents: list[str] = field(default_factory=list)
    model_mapping: dict[str, str] = field(default_factory=dict)
    provider: str = "lm-studio"
```

### 5.2 Runner

Exécution d'expériences :
- Isolation des runs
- Finalisation RAW
- Gestion des échecs
- Tracking de provenance

### 5.3 Events System

Types d'événements :
- `DebateStarted`, `DebateFinished`
- `TurnCompleted`, `TurnFailed`
- `ModeratorDecision`
- `MemoryConsolidated`
- `ErrorOccurred`

Format JSONL :
```json
{
  "event_id": "uuid",
  "experiment_id": "EXP-001",
  "run_id": "RUN-001",
  "event_type": "model_call_completed",
  "timestamp": "2026-10-05T18:30:00Z",
  "component_id": "stoic",
  "component_version": "1.0.0",
  "payload": { ... }
}
```

---

## 6. Couche Code Lab

### 6.1 Multi-Agent Code Generation

Pipeline :
```
PLANNER → DEVELOPER → CRITIC → REVIEWER → JUDGE
```

**Rôles :**
- `PLANNER`: Génère le plan d'implémentation
- `DEVELOPER`: Écrit le code
- `CRITIC`: Analyse la qualité
- `REVIEWER`: Revue de code
- `JUDGE`: Validation finale

### 6.2 Compression & Validation

Outils de compression :
- Réduction de contexte
- Extraction de patterns
- Validation déterministe

### 6.3 Provenance Events

Tests : `test_code_lab_event_provenance.py`
- Balanced event pairs (STARTED = RESPONSE + FAILED)
- Unique trace indices across retries
- Schema completeness
- Real engine runs write valid events.jsonl

---

## 7. Interface Utilisateur

### 7.1 Life_mean Studio (PySide6)

Architecture :
```
launcher/app.py          # Point d'entrée
engine/runner.py         # Moteur d'exécution
engine/storage.py        # Persistence
workflows/manager.py     # Orchestration workflows
prompts/collection.py    # Collection de prompts
```

### 7.2 Pages UI

- **Autopilot**: Dashboard contrôleurs
- **Settings**: Configuration système
- **Code Lab**: Interface génération code
- **Debate**: Visualisation débat en temps réel

### 7.3 Workflows

Manager de workflows :
- Création de sessions
- Exécution de pipelines
- Collecte de résultats
- Export de données

---

## 8. Couche Données

### 8.1 Structure RAW

```
data/raw/EXP-{id}/RUN-{id}/
├── events.jsonl      # Log d'événements structuré
├── config.json       # Configuration expérimentale
└── metadata.json     # Versions composants, timestamps
```

### 8.2 Règles RAW

- **Immutable** après écriture
- Erreur d'analyse → nouvelle analyse, pas modification RAW
- Dérivé reconstruisable depuis RAW
- Représente ce qui s'est réellement passé

### 8.3 Base de Données SQLite

Tables :
- `debates` — Métadonnées débat
- `turns` — Historique complet des tours (RAW)
- `memory_short/mid/long` — Stockage mémoire
- `moderator_decisions` — Choix modérateur
- `agents` — Définitions agents
- `events` — Événements cycle de vie

---

## 9. Sécurité et Intégrité

### 9.1 Secret Hygiene Audit

Script : `scripts/release_audit.py`

**Fichiers interdits :**
- `.env` (fichier credentials)
- `overrides/llm.env` (override credentials)
- `hermes-orchestrator/.env` (legacy)

**Dossiers interdits :**
- `node_modules/`
- `code_lab_runs/`, `code_lab/runs/`
- `build/`, `dist/`
- `__pycache__/`, `*.egg-info/`

### 9.2 Provenance Hashing

Chaque événement enregistre :
- `system_prompt_hash`
- `sampling_settings_hash`
- `input_context_hash`
- `response_hash`

Permet replay déterministe et vérification.

### 9.3 Security Audit Points

**Vulnerabilités identifiées (historique) :**
- Zombiefication via injection de prompt
- Fuites de credentials dans l'historique git
- Dépendances non-auditées

**Mitigations :**
- Purge historique via `git filter-repo`
- Credentials dans Windows Credential Manager
- Audit source avant release

---

## 10. Recherche et Contexte Canonique

### 10.1 Canonical Context Experiment

**Question de recherche :**
> *Combien de contexte un agent peut-il perdre avant de perdre la capacité de prendre la bonne décision suivante ?*

### 10.2 Structure de Recherche

```
research/canonical_context/
├── ab_runs/                 # Runs expérimentaux
│   ├── ab_experiment_audit.md
│   ├── developer_failure_diagnostic.md
│   └── preflight_report.md
├── historical_cases/        # Audits cas historiques
│   └── codelab_554fc20975_audit.md
├── prospective_runs/        # Runs prospectifs
└── seeds/                   # Seeds de contexte
```

### 10.3 Études de Cas

**codelab_554fc20975 :**
- Status: failed
- Root cause: Model unavailability (VRAM insuffisant)
- Lesson: Need model pool with fallback sizes

---

## 11. Héritage — Les Deux Échecs

### 11.1 Mia_Brain / CaptN-BRAIN

**Architecture originale :**
```
User → CLI / Dashboard / MIA
    ↓
SmartRouter (keyword-based routing)
    ↓
ToolRouter → ~800 deterministic tools
    ↓
LLM Fallback (optional, --llm-fallback)
    ↓
Validation → Output
```

**Problèmes :**
- Couplage fort SmartRouter ↔ Thinkers
- Pas de séparation Stable/Experimental
- Fallback LLM silencieux plutôt qu'explicite
- Traçabilité incomplète des échecs

**Leçons appliquées à Life_mean :**
- Séparation stricte des zones
- Interfaces explicites
- "No silent fallback" comme principe
- Instrumentation complète des événements

### 11.2 Herme-debate / Orchestrateur TypeScript

**Architecture originale :**
```
TypeScript Orchestrator ↔ Python Debate Engine
         ↓
    Raw Data Output
```

**Problèmes :**
- Dépendance implicite entre systèmes
- Pas de validation déterministe
- Absence de séparation données/code
- Difficulté de reproduction

**Leçons appliquées :**
- Architecture RAW-first
- Séparation physique data/code
- Validation déterministe comme autorité
- Traçabilité complète code→résultat

---

## 12. Architecture Decision Records

### 12.1 ADR Template

Chaque décision majeure documentée dans `docs/adr/` :
- Origin
- Contexte
- Décision
- Conséquences
- Alternatives considérées

### 12.2 Décisions Majeures

| ADR | Sujet | Statut |
|-----|-------|--------|
| ADR-001 | Séparation Stable/Experimental | Adopté |
| ADR-002 | Architecture RAW immuable | Adopté |
| ADR-003 | Provenance hashing | Adopté |
| ADR-004 | No silent fallback | Adopté |

---

## 13. Tests et Validation

### 13.1 Suite de Tests

**Total:** 713 tests passing, 12 skipped (external deps), 2 known failures

**Catégories :**
- `test_debate_engine*.py` — Logic moteur débat
- `test_code_lab*.py` — Génération code
- `test_autopilot*.py` — Lifecycle autogestion
- `test_providers*.py` — LLM providers
- `test_schemas*.py` — Validation schemas
- `test_persistence*.py` — Storage/restore
- `test_security*.py` — Security audits

### 13.2 Tests Spécifiques

**Provenance :**
```bash
python -m pytest tests/test_code_lab_event_provenance.py -v
# 12 passed — every agent event is accounted for
```

**Model provenance :**
```bash
python -m pytest tests/test_turn_model_provenance.py -v
# 11 passed — model/provider round-trip verified
```

### 13.3 Known Failures

| Test | Cause | Status |
|------|-------|--------|
| `test_runtime_restore.py` | Subprocess path issue | Pre-existing, not blocking |

---

## ANNEXE: Glossaire

| Terme | Définition |
|-------|------------|
| **RAW** | Données brutes immuables post-expérience |
| **Provenance** | Traçabilité code→config→résultat |
| **Canonical Context** | État canonique pour réplication expérimentale |
| **RoleTemplate** | Template générique pour participants non-philosophiques |
| **No Silent Fallback** | Principe: échec LLM = échec explicite, pas substitution cachée |
| **SmartRouter** | Routeur adaptatif cache→déterministe→LLM |

---

*Ce catalogue est vivant. Mettre à jour avec chaque décision architecturale majeure.*
