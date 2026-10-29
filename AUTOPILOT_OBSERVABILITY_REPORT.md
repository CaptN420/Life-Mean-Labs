# Autopilot Observability Report

## 1. Architecture Autopilot Découverte

### Points d'entrée
- **`experiments/ui_controller.py`** : `create_experiment()` → `start_experiment()` → `_run_experiment_loop()`
- **`experiments/autopilot.py`** : `AutoPilotOrchestrator` — moteur de débat existant, non modifié
- **`experiments/dashboard.py`** : endpoints HTTP `/api/experiments/*`

### Moteur déterministe
- `core/debate/router.py` : `RoundRobinRouter`, `WeightedRouter`, `ContextAwareRouter`
- Règles de sélection : stratégie configurée dans `ExperimentConfig.router.method`
- Ordre de passage : contrôlé par le router, observable via les traces

### Sélection des agents
- Déterminée par `ExperimentConfig.agents` (liste de dicts avec `agent_id`, `persona`, `role`, `model`, `provider`)
- Les personas sont chargés depuis `core/personas/` et validés avant exécution

### Événements d'exécution
| Événement | Kind | Source |
|-----------|------|--------|
| Agent sélectionné | `agent_selected` | Orchestrator → observability |
| Tour commencé | `turn_started` | Orchestrator → observability |
| Tour terminé | `turn_completed` | Orchestrator → observability |
| Règle appliquée | `rule_applied` | Router → observability |
| Transition d'état | `transition` | Orchestrator → observability |
| Erreur | `error` | Tout handler d'erreur |
| Expérience démarrée | `experiment_started` | UIController |
| Expérience terminée | `experiment_completed` | UIController |

### Stockage des résultats
- **Transcript** : `experiments/observability.py` → `AutopilotObservability.get_events()`
- **Traces déterministes** : `AutopilotObservability.get_traces()`
- **Manifeste** : `AutopilotObservability.export_manifest()` — JSON complet pour reproductibilité

## 2. Fonctionnalités Existantes Réutilisées

| Composant | Usage | Modifications |
|-----------|-------|---------------|
| `core/debate/router.py` | Lecture seule — stratégie de sélection | Aucune |
| `core/personas/manager.py` | Chargement des personas | Aucune |
| `life_mean_lab/orchestrator/` | Exécution du débat | Instrumentation ajoutée |
| `experiments/ui_controller.py` | Cycle de vie des expériences | Ajout `_observability` |
| `experiments/dashboard.py` | API HTTP | Endpoints observability ajoutés |

## 3. Modifications Effectuées

### Fichiers créés
- **`experiments/observability.py`** : Module d'observabilité complet
  - `AgentRecord` : état par agent (status, round, errors)
  - `DebateEvent` : événement de transcript (turn, rule, error)
  - `DeterministicTrace` : décision déterministe (rule, state_before/after)
  - `ExperimentProgress` : métriques de progression
  - `AutopilotObservability` : contrôleur thread-safe

### Fichiers modifiés
- **`experiments/ui_controller.py`** :
  - Ajout `self._observability: Dict[str, AutopilotObservability]`
  - Initialisation dans `create_experiment()` et `_run_experiment_loop()`
  - Mise à jour des statuts agents via `update_agent_status()`
  - Enregistrement des tours via `record_turn()`
  - Traçage des règles via `record_rule_application()`
  - Complétion observability dans `finally`
  - Méthodes `get_observability()` et `export_experiment_manifest()`

- **`experiments/dashboard.py`** :
  - Endpoint `GET /api/experiments/{id}/observability`
  - Endpoint `GET /api/experiments/{id}/manifest`

- **`experiments/ui/dashboard.html`** :
  - Panneau "Observability" avec 6 sous-sections
  - Bouton "View" sur chaque expérience
  - Fonctions JS : `loadObservability()`, `renderObservability()`, `exportTranscript()`, `exportManifest()`, `replayExperiment()`

### Fichiers de test créés
- **`tests/test_observability.py`** : 20 tests couvrant tous les cas

## 4. Points d'Instrumentation Ajoutés

| Point | Méthode | Information enregistrée |
|-------|---------|------------------------|
| Début expérience | `start_experiment()` | Config, prompt, agents, timestamp |
| Sélection agent | `_select_next_agent()` | Règle appliquée, agent sélectionné |
| Tour terminé | `_run_task()` | Agent, round, réponse, règle |
| Erreur modèle | `_run_task()` | Message d'erreur, agent concerné |
| Transition état | `_advance_round()` | State before/after, règle |
| Fin expérience | `_run_experiment_loop()` | Status final, durée |

## 5. Tests Exécutés

| Test | Résultat |
|------|----------|
| `tests/test_observability.py` (20 tests) | ✅ 20 passed |
| `tests/test_phase7_autopilot.py` (8 tests) | ✅ 8 passed |
| `tests/test_dashboard_http_smoke.py` (6 tests) | ✅ 6 passed |
| `tests/test_phase0_config.py` (13 tests) | ✅ 13 passed |
| `tests/test_sentinel.py` (31 tests) | ✅ 31 passed |
| **Total** | **78 passed** |

## 6. Résultats Vérifiés

### API Observability
```json
GET /api/experiments/{id}/observability
{
  "config": {...},
  "prompt": "...",
  "agents": {
    "agent1": {
      "agent_id": "agent1",
      "persona": "researcher",
      "role": "analyst",
      "model": "model_a",
      "provider": "local",
      "status": "Completed",
      "current_round": 3,
      "errors": []
    }
  },
  "events": [...],
  "traces": [...],
  "progress": {
    "status": "COMPLETED",
    "current_round": 3,
    "total_rounds": 5,
    "active_agent": "agent1",
    "elapsed_seconds": 42.5,
    "tasks_completed": 15,
    "tasks_total": 20
  }
}
```

### Export Manifest
```json
GET /api/experiments/{id}/manifest
{
  "experiment_id": "...",
  "prompt": "...",
  "config": {...},
  "agents": {...},
  "events": [...],
  "traces": [...],
  "progress": {...},
  "exported_at": 1234567890.0
}
```

## 7. Limites et Problèmes Ouverts

| Limitation | Impact | Solution potentielle |
|------------|--------|---------------------|
| Polling toutes les 3s | Légère surcharge CPU | WebSockets pour temps réel |
| Traces non disponibles si moteur ne les émet pas | Information manquante | Instrumenter le router existant |
| Pas de support pause/resume | Expérience non interrompible | Ajouter `_pause_event` dans orchestrator |
| UI ne détecte pas déconnexion serveur | Données obsolètes | Ajouter heartbeat check |

## 8. Critère de Réussite Vérifié

✅ Un utilisateur peut :
1. Écrire un prompt expérimental
2. Lancer Autopilot
3. Voir les vrais agents travailler (panneau Active Agents)
4. Lire le dialogue complet (Live Debate Transcript)
5. Comprendre les règles appliquées (Deterministic Decision Trace)
6. Retrouver l'expérience plus tard (Export Manifest + Replay)
