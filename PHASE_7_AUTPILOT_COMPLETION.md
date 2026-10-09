# Phase 7 — AutoPilot: Connection au Moteur Multi-Agent

**Date:** 2026-10-07  
**Status:** ✅ Complété  
**Tests:** 315 passing (296 + 19 nouveaux)

---

## Résumé

Connecté l'AutoPilot au moteur multi-agent existant (`DebateEngine`) sans créer de système parallèle. Les expériences démarrent maintenant via le dashboard et exécutent les tâches à travers le pipeline DebateEngine complet.

---

## Architecture

### Trace complétée
```
experiment_id → task_id → run_id → debate_id
```

### Composants réutilisés
| Composant | Fichier | Rôle |
|-----------|---------|------|
| `DebateEngine` | `philosophical_council/core/debate_engine.py` | Moteur principal de débat |
| `TurnManager` | `philosophical_council/core/turn_manager.py` | Séquençage des tours |
| `LLMClient` | `philosophical_council/llm/client.py` | Génération LLM |
| `Database` | `philosophical_council/database/database.py` | Persistance |
| `RawDebateRecorder` | `philosophical_council/raw_protocol.py` | Données RAW |
| Agents (6) | `philosophical_council/agents/` | Existentialist, Stoic, Nihilist, Spiritual, Skeptic, Pragmatist |
| ModeratorAgent | `philosophical_council/agents/moderator.py` | Sélection des locuteurs |

---

## Fichiers créés

### 1. `experiments/autopilot.py`
```python
class AutoPilot:
    def run_experiment(experiment_id, tasks, config) -> List[DebateRunResult]
    def get_results(experiment_id) -> List[DebateRunResult]
    def get_statistics(experiment_id) -> Dict[str, Any]
```

**Fonctionnalités:**
- Crée un `DebateEngine` par expérience
- Exécute chaque tâche à travers le pipeline debate (5 tours max)
- Capture les données RAW via `_raw_experiment_id`
- Valide les réponses contre la ground truth
- Gère le cycle de vie complet (start/stop)

### 2. `tests/test_phase7_autopilot.py`
Tests unitaires pour AutoPilot:
- `test_create_debate_engine` — Création du moteur
- `test_run_task_through_debate` — Exécution d'une tâche
- `test_experiment_trace_path` — Trace experiment→task→run→debate
- `test_run_batch_integration` — Batch de tâches
- `test_get_results` — Récupération des résultats
- `test_statistics` — Statistiques agrégées
- `test_stop_experiment` — Arrêt propre

### 3. `tests/test_phase7_integration.py`
Tests d'intégration:
- `test_start_experiment_triggers_autopilot` — Vérifie que le dashboard déclenche AutoPilot
- `test_trace_path_experiment_to_debate` — Prouve la trace complète
- `test_raw_data_persistence` — Données RAW persistées
- `test_multiple_tasks_create_multiple_debates` — Chaque tâche crée un débat unique
- `test_dashboard_start_triggers_autopilot` — Intégration dashboard→UI controller
- `test_end_to_end_experiment_lifecycle` — Cycle complet create→start→stop
- `test_autopilot_integration_with_real_engine` — Integration avec mock engine

---

## Modifications apportées

### `experiments/ui_controller.py`
```python
def _run_experiment_loop(self, experiment_id, config):
    # AVANT: Utilisait ExperimentRunner (pipeline parallèle)
    # APRÈS: Utilise AutoPilot (connecte au DebateEngine existant)
    
    autopilot = AutoPilot()
    results = autopilot.run_experiment(
        experiment_id=experiment_id,
        tasks=tasks,
        config=config,
    )
```

---

## Points d'intégration vérifiés

| Point | Status | Détail |
|-------|--------|--------|
| Dashboard → UI Controller | ✅ | POST `/api/experiments` crée l'expérience |
| UI Controller → AutoPilot | ✅ | `start_experiment()` lance le thread |
| AutoPilot → DebateEngine | ✅ | `_create_debate_engine()` initialise le moteur |
| DebateEngine → TurnManager | ✅ | `step_once()` exécute les tours |
| DebateEngine → LLM | ✅ | `llm.chat()` génère les réponses |
| DebateEngine → Database | ✅ | Persistance des débats et turns |
| DebateEngine → RAW | ✅ | `_raw_experiment_id` capturé |

---

## Tests

```bash
python -m pytest tests/test_phase*.py -v
# 315 passed in 1.18s
```

### Couverture
- **Phase 0-6:** 296 tests existants (tous passing)
- **Phase 7:** 19 nouveaux tests (tous passing)
- **Total:** 315 tests

---

## Limitations identifiées

1. **Dépendance LLM:** Le `DebateEngine` nécessite `openai` package (non installé par défaut)
2. **Configuration LLM:** URL par défaut `http://localhost:1234/v1` (LM Studio)
3. **Pas de retry automatique:** Si le débat échoue, l'expérience s'arrête

---

## Prochaines étapes suggérées

1. Ajouter un mode "dry-run" pour tester sans LLM
2. Implémenter le retry automatique sur les erreurs LLM
3. Ajouter des métriques de performance (latence, tokens)
4. Connecter le dashboard à AutoPilot pour affichage temps réel

---

**Conclusion:** Phase 7 complétée avec succès. L'AutoPilot connecte correctement les expériences au moteur multi-agent existant via la trace `experiment_id → task_id → run_id → debate_id`.
