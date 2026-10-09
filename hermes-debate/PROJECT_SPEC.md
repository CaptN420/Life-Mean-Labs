# AI Debate Research Laboratory — PROJECT SPEC

**Version:** 0.1.0  
**Date:** 2026-10-05  
**Status:** Phase 0 — Scientific Design  

---

## 1. Vision

Le projet est un **laboratoire expérimental modulaire** pour l'étude scientifique des systèmes de débat multi-agents basés sur des modèles de langage.

> **Le chercheur décrit l'expérience. Le laboratoire s'occupe de l'infrastructure.**

Objectif : permettre à un chercheur de définir une expérience une seule fois, puis de modifier indépendamment les variables expérimentales (personas, rôles, modèles, protocoles, orchestrateurs, decision models) sans reconstruire l'infrastructure.

---

## 2. Positionnement Scientifique

Ce projet ne prétend pas innover technologiquement. De nombreuses technologies existent déjà pour :
- Débats multi-agents
- Personas et rôles
- Orchestration LLM
- Systèmes d'audit comportemental

La contribution est l'intégration de ces concepts dans un **laboratoire expérimental unifié et reproductible**.

**Positionnement recommandé :**
> *An experimental laboratory for systematically studying how models, personas, roles, protocols, decision strategies, and orchestration architectures affect multi-agent debate dynamics and outcomes.*

Le logiciel est l'**instrument de recherche**, pas la contribution scientifique elle-même.

---

## 3. Terminologie Fondamentale

### Question
La question scientifique ou problème soumis au débat.
Exemple : *Les systèmes d'IA devraient-ils pouvoir prendre des décisions autonomes dans les domaines à haut risque ?*

### Persona
Une perspective, identité ou manière de raisonner. Ce n'est pas obligatoirement un rôle.
Exemples : Analytical Philosopher, Ethical Philosopher, Skeptic, Advocate, Scientist, Pragmatist, Humanist, Futurist, Optimist, Pessimist/Risk Analyst, Mediator, Neutral Judge.

### Role
Ce que l'agent doit faire dans une phase donnée. Une persona peut changer de rôle entre phases.
Exemples : Advocate, Critic, Skeptic, Questioner, Cross-Examiner, Researcher, Synthesizer, Judge, Moderator, Devil's Advocate, Final Evaluator.

### Model
Le modèle réellement utilisé pour produire une réponse. Un même modèle peut servir plusieurs personas ; une même persona peut utiliser différents modèles selon les phases.

### Decision Model
Modèle spécialisé pour la prise de décision structurée : routage, sélection d'agent, choix d'outil, évaluation d'options. Distinct des models génératifs.

---

## 4. Architecture Conceptuelle

```text
Question
   ↓
Personas
   ↓
Roles
   ↓
Models (Generative)
   ↓
Decision Models
   ↓
Protocol
   ↓
Orchestrator
   ↓
Experiment
   ↓
Run
   ↓
RAW
   ↓
Analysis
   ↓
Metrics
   ↓
Comparison
   ↓
Library
```

---

## 5. Decision Models

### Distinction fondamentale
```text
Models
├── Generative Models (production de contenu)
└── Decision Models (prise de décision structurée)
```

### Interface conceptuelle
```python
decision_model.decide(
    options=["agent_01", "agent_02", "agent_03"],
    context=debate_state
) -> DecisionResult
```

### Strands Decider 2B
Modèle de décision local via LM Studio. Doit fonctionner sans couplage direct avec LangGraph/CrewAI/AutoGen.

Configuration externe requise :
```yaml
provider:
  type: lm_studio
  base_url: http://localhost:1234/v1
  
model:
  id: strands-decider-2b  # ou tout identifiant exposé par LM Studio
  type: decision_model
  temperature: 0.0
```

### Mock Decision Model
Pour tests CI/CD sans modèle local. Retourne des décisions déterministes.

---

## 6. Personas de Base

### Sélectionnées par défaut
- [x] Analytical Philosopher
- [x] Ethical Philosopher
- [x] Skeptic
- [x] Advocate
- [x] Scientist
- [x] Pragmatist

### Optionnelles (non sélectionnées par défaut)
- [ ] Contrarian
- [ ] Humanist
- [ ] Futurist
- [ ] Optimist
- [ ] Pessimist / Risk Analyst
- [ ] Mediator
- [ ] Neutral Judge
- [ ] Interdisciplinary Researcher

Cette distinction permet des expériences contrôlées (ablation de Skeptic, comparaison 3/5/8 personas, etc.).

---

## 7. Protocoles

Indépendants des modèles et orchestrateurs.

### Protocoles prédéfinis
- Free Debate
- Structured Debate
- Oxford-style
- Socratic
- Cross Examination
- Multi-round Debate
- Debate + Judge
- Debate + Synthesis
- Custom Protocol

Chaque protocole est versionné et enregistrable dans la Library.

---

## 8. Mapping Persona → Role → Model

Configuration flexible par phase :

```text
Phase: Opening
  Philosopher → Advocate → Model A
  Skeptic → Critic → Model B

Phase: Cross Examination
  Philosopher → Questioner → Model C
  Skeptic → Cross Examiner → Model B
```

Le moteur ne suppose jamais qu'une persona a toujours le même rôle ou modèle.

---

## 9. Orchestrators

Interchangeables, considérés comme **variables expérimentales**.

### Adapters prévus
- Custom Orchestrator ( natif)
- LangGraph
- CrewAI
- AutoGen
- Futurs frameworks

Interface conceptuelle :
```python
orchestrator.run(experiment) -> RunResult
```

Le modèle scientifique ne dépend pas de l'implémentation interne.

---

## 10. External Ecosystem

### Séparation stricte CORE vs EXTERNAL

```text
CORE:
  Questions, Personas, Roles, Models, Decision Models,
  Protocols, Experiments, Runs, RAW, Analysis, Metrics,
  Comparison, Library

EXTERNAL:
  Petri, Agent-Leaderboard, External Frameworks,
  External Research Tools, External Benchmarks
```

### Agent-Leaderboard
Source externe de découverte (frameworks, MCP servers, agent skills, prompt libraries).  
Structure : `external/Agent-Leaderboard/`  
Conserver : URL source, commit/version, date de récupération.

### Petri
Outil externe d'audit/évaluation. Ne fait pas partie intégrante du moteur.  
Structure : `external/Petri/` + `external/Petri/SOURCE.md`

Adapter indépendant si nécessaire :
```text
backend/adapters/external/petri_adapter.py
```

---

## 11. Experiment

Configuration scientifique immuable.

```yaml
experiment_id: EXP001
question: Q001
personas: [analytical_philosopher, skeptic, advocate]
protocol: cross_examination_v1
models:
  analytical_philosopher: model_a
  skeptic: model_b
  advocate: model_a
orchestrator: langgraph
decision_model: strands_decider_2b
repetitions: 5
```

---

## 12. Run

Exécution réelle d'un Experiment. Structure hiérarchique :

```text
Study
  ↓
Experiment
  ↓
Run 001
Run 002
Run 003
...
```

Chaque Run est **immuable**.

---

## 13. RAW

Source de vérité de l'exécution. Contient :

- Configuration complète
- Question, personas, rôles, modèles
- Protocole, orchestrateur, decision model
- Transcript complet
- Événements, décisions, métriques brutes
- Erreurs, retries, timestamps
- Environnement, versions, provenance

**Règle :** RAW est immuable. Les analyses ne modifient jamais RAW.

---

## 14. Reproductibilité

Chaque expérience enregistre :

| Élément | Version |
|---------|---------|
| Question | version |
| Persona | version |
| Role | version |
| Protocol | version |
| Prompt | version |
| Model name | version |
| Model parameters | timestamp |
| Orchestrator | version |
| Decision model | version |
| External tools | versions |
| Petri | version (si utilisé) |
| Code commit | hash |
| Date | ISO |
| Environnement | specs |
| Seed | value |

---

## 15. Parametric Experiments

Génération automatique d'expériences :

```text
4 models × 3 persona sets × 2 orchestrators × 5 repetitions = 120 runs
```

Le système distingue :
- Study (collection d'expériences)
- Experiment (configuration)
- Run (exécution)

---

## 16. Ablation Studies

Support natif des ablations :

| Hypothèse | Condition contrôle | Condition expérimentale | Variable modifiée |
|-----------|-------------------|------------------------|-------------------|
| Skeptic utile | Sans Skeptic | Avec Skeptic | Persona Skeptic |
| Diversité personas | 3 personas | 5 personas | Nombre de personas |
| Routage décisionnel | Random | LLM | Decision model |
| Orchestration | LangGraph | CrewAI | Orchestrator |

Chaque ablation documente : hypothèse, conditions, variables, résultats.

---

## 17. Analysis Engine

### Quantitative
Tokens, coût, latency, durée, appels, tours, rounds, erreurs, retries, routing decisions, decision latency, succès/échec, utilisation modèles.

### Qualitative
Diversité argumentative, arguments uniques/communs, contradictions, contre-arguments, concepts récurrents, profondeur, cohérence, évolution, convergence/divergence, répétition, faiblesses logiques, influence, engagement, dynamique agents.

---

## 18. Argument Lifecycle

Suivi temporel des arguments :

```text
Introduced → Repeated → Challenged → Modified → Accepted / Rejected
```

---

## 19. Comparison Engine

Comparaisons possibles :

| Dimension | Éléments comparables |
|-----------|---------------------|
| Configuration | personas, models, roles, protocol, orchestrator, decision model |
| Performance | cost, latency, tokens, errors, calls |
| Debate Dynamics | influence, convergence, contradiction, diversity, engagement |
| Arguments | common/unique, contradictions, reasoning paths, recurring concepts |
| Conclusions | final answer, judge decision, consensus, disagreement |

Support comparaison de fichiers TXT/Markdown (RUN001.md vs RUN002.md).

---

## 20. Research Question Generator

Le laboratoire peut identifier des questions scientifiques à partir des observations :

**Observation :** *Le Skeptic introduit rarement de nouveaux arguments mais provoque davantage de contre-arguments.*  
**Question générée :** *Does the Skeptic persona increase argumentative depth without increasing argument diversity?*

---

## 21. Scientific Benchmarking

Bibliothèque versionnée : `library/benchmarks/`  
Contient : questions, protocoles, persona sets, dimensions d'évaluation attendues.

---

## 22. Library

```text
library/
├── questions/
├── personas/
├── roles/
├── protocols/
├── models/
│   └── local/
├── orchestrators/
├── decision_models/
├── experiments/
├── analyses/
├── comparisons/
├── benchmarks/
└── templates/
```

---

## 23. Interface Utilisateur

Permet au chercheur de :
1. Sélectionner une Question
2. Sélectionner les Personas (de base + optionnelles)
3. Configurer les Roles
4. Sélectionner les Models
5. Sélectionner un Protocol
6. Sélectionner un Orchestrator
7. Sélectionner éventuellement un Decision Model
8. Configurer les répétitions
9. Lancer l'expérience
10. Consulter les Runs
11. Analyser
12. Comparer
13. Archiver

---

## 24. Experiment Builder

Interface de construction :

```text
Question → Persona Set → Role Mapping → Model Mapping
         → Protocol → Orchestrator → Decision Model
         → External Instruments → Repetitions → RUN
```

Affichage clair de toutes les variables.

---

## 25. Scientific Decisions

Distinction tracée :

| Type | Exemple |
|------|---------|
| Researcher Decision | Choix du protocole |
| System Decision | Routage automatique |
| Agent Decision | Génération de réponse |
| Decision Model Decision | Sélection d'agent par Strands Decider |

---

## 26. Observability

Logs, events, traces, timestamps, errors, retries, model calls, routing decisions, external-tool calls.  
Les événements importants sont reliés au Run.

---

## 27. Architecture Technique

### Stack recommandée
| Couche | Technology |
|--------|------------|
| Frontend | Next.js + TypeScript |
| Backend | Python + FastAPI |
| Storage | SQLite (initialement) |
| Artifacts | Markdown / JSON |
| Workers | Optionnels |
| Adapters | LangGraph, CrewAI, AutoGen, Custom |
| Models | Generative + Decision |
| External | Petri, Agent-Leaderboard, Other tools |

### Modèle de données (entités indépendantes)
```
Question, Persona, Role, Model, DecisionModel, Protocol,
Orchestrator, ExternalTool, Experiment, Run, Analysis,
Metric, Comparison, Benchmark
```

---

## 28. Études Expérimentales Initiales

| # | Expérience | Description |
|---|------------|-------------|
| 1 | Persona Diversity | 3 vs 5 vs 8 personas |
| 2 | Skeptic Ablation | Sans vs Avec Skeptic |
| 3 | Model Diversity | Même modèle vs Différents modèles |
| 4 | Orchestrator Comparison | LangGraph vs CrewAI vs AutoGen |
| 5 | Decision Routing | Random vs Rule-based vs LLM vs Strands Decider 2B |
| 6 | Petri Audit | Debate A vs Debate B → Audit comportemental |
| 7 | Combined | Persona + Model + Orchestration + Decision Model + Audit |

---

## 29. Questions Scientifiques Potentielles

```
RQ1: Does persona diversity improve deliberation quality?
RQ2: Does disagreement improve reasoning?
RQ3: Does model heterogeneity improve debate quality?
RQ4: Does orchestration architecture affect debate dynamics?
RQ5: Does cross-examination improve argument quality?
RQ6: Can a decision model improve routing efficiency?
RQ7: Does Strands Decider 2B reduce computational cost?
RQ8: Does decision-based routing change agent influence?
RQ9: Does adding a Skeptic reduce problematic behaviors?
RQ10: Can external behavioral audits reveal differences that final-answer metrics fail to detect?
```

---

## 30. Roadmap

### Phase 0 — Scientific Design (COMPLÉTÉE)
- [x] Vision et positionnement
- [x] Terminologie fondamentale
- [x] Architecture conceptuelle
- [x] Validation du spec

### Phase 1 — Core Domain (COMPLÉTÉE)
- [x] Question, Persona, Role, Model, Protocol, Experiment, Run
- [x] Assignment strategies (Fixed, Random, Round-Robin)
- [x] Experiment engine with repetitions
- [x] RAW artifact management
- [x] Provenance tracking
- [x] Auto Pilot framework

### Phase 2 — Model Registry
- Cloud models, local models, configuration, versioning

### Phase 3 — Decision Models
- DecisionModel interface, Mock, Strands Decider 2B, LM Studio adapter, metrics, tests

### Phase 4 — Orchestrators
- Custom, LangGraph, CrewAI, AutoGen

### Phase 5 — Experiment Engine
- Repetitions, parametric experiments, ablations

### Phase 6 — RAW and Reproducibility
- Immutable RAW, provenance, environment, versions, traces

### Phase 7 — Analysis
- Quantitative metrics, qualitative analysis, argument lifecycle, debate dynamics

### Phase 8 — Comparison
- Run comparison, configuration comparison, argument comparison, model/persona/orchestrator comparison

### Phase 9 — External Instruments
- ExternalTool interface, Petri adapter, benchmark integration

### Phase 10 — Research Interface
- Interface complète de laboratoire

### Phase 11 — Scientific Studies
- Ablations, benchmarks, controlled experiments, reproducibility studies, comparative studies

---

## 31. Règles de Développement

1. Ne pas coder avant d'avoir défini l'architecture dans `PROJECT_SPEC.md`
2. Ne pas créer de dépendance directe vers LangGraph/CrewAI/AutoGen/Petri/LM Studio/Agent-Leaderboard
3. Tout composant externe passe par un adapter ou interface appropriée
4. Tout résultat expérimental est traçable jusqu'à sa configuration
5. RAW est immuable
6. Les analyses ne modifient jamais RAW
7. Les expériences doivent pouvoir être répétées
8. Les variables expérimentales doivent être explicites
9. Les versions doivent être enregistrées
10. Ne jamais hardcoder les modèles locaux ou endpoints
11. Les outils externes peuvent être remplacés
12. Ne jamais présenter une hypothèse comme un résultat

---

## 32. Prochaines Étapes

### Décisions à valider
- [x] Architecture technique détaillée (Phase 1)
- [ ] Priorité d'implémentation des phases
- [ ] Stack frontend/backend définitive

### Risques identifiés
- Sur-architecture prématurée
- Dépendances implicites aux frameworks
- Complexité de la reproductibilité à grande échelle

### Ambiguïtés ouvertes
- Format exact du RAW (JSON vs Markdown vs les deux?)
- Gestion des secrets et credentials
- Stratégie de testing end-to-end

---

## 33. Phase 1 — Core Domain (COMPLÉTÉE)

### Entités implémentées

#### `core/domain.py`
- **Question**: ID, texte, version, metadata, timestamp
- **Persona**: Type énuméré (6 core + 8 optionnelles), description, prompt template
- **Role**: Type énuméré (12 rôles), description
- **ModelConfig**: Generative vs Decision, provider, endpoint, paramètres
- **Protocol**: Types prédéfinis (9 protocoles), phases, versionnement
- **Experiment**: Configuration immuable, contraintes, métadonnées
- **Run**: Exécution réelle, transcript, métriques, erreurs

#### `core/experiment_engine.py`
- **ExperimentEngine**: Création, exécution, gestion des runs
- **AssignmentStrategy** (ABC): Interface pour stratégies d'attribution
  - FixedAssignment: Mapping fixe persona → model
  - RandomAssignment: Sélection aléatoire avec seed
  - RoundRobinAssignment: Rotation cyclique
- **ExperimentPlanner**: Ablations et expériences paramétriques
- **AutoPilot**: Campagnes automatisées, contrôles budgétaires

#### `core/raw.py`
- **RAWHArtifact**: Données brutes immuables
- **RAWArchive**: Stockage avec provenance
- **ProvenanceTracker**: Chaîne complète study → experiment → run → event

### Tests
- 29 tests dans `tests/test_experiment_engine.py`
- 87 tests totaux, tous verts

---

**Fin de la Phase 1 — Core Domain**  \n*Prêt pour validation avant passage à la Phase 2 (Model Registry).*
