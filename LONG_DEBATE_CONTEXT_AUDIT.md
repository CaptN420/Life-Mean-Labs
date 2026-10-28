# LONG_DEBATE_CONTEXT_AUDIT.md

## Audit des limites de tours actuelles

### Fichiers modifiés

| Fichier | Limite actuelle | Nouveau comportement |
|---------|-----------------|---------------------|
| `debate_lab/config.py` | `MAX_TURNS_CEILING = 10000` | `MAX_TURNS_CEILING = 1500` |
| `experiments/autopilot.py:372` | `_execute_debate_turns(engine, max_turns=5)` | Utilise maintenant `config.max_turns` |
| `ui/dashboard.html:718` | `max="10000"` | `max="1500"` + contrôle compression |

### Chemin de construction du contexte

```
User/UI (dashboard)
    ↓
ExperimentConfig / DebateLabConfig
    ↓
DebateLabController._run_once()
    ↓
DebateEngine.step_once()
    ↓
TurnManager.get_all_turns()
    ↓
ContextCompressor.compress() [si enabled]
    ↓
LLM
```

### Comportement de la mémoire

| Type | Avant | Après |
|------|-------|-------|
| RAW history | Append-only, complet | Identique — jamais modifié |
| Active context | Tous les tours | Tours récents + résumé compressé |
| Compressed memory | N/A | Nouveau — historique des tours compressés |

### Risques d'échelle estimés

| Scénario | Tokens estimés | Risque |
|----------|---------------|--------|
| 20 tours (default) | ~10K | Faible |
| 100 tours | ~50K | Moyen — compression recommandée |
| 500 tours | ~250K | Élevé — compression nécessaire |
| 1500 tours | ~750K | Critique sans compression |

### Fichiers à modifier

1. `debate_lab/config.py` — champs compression + validation
2. `debate_lab/compression.py` — nouveau module (créé)
3. `debate_lab/controller.py` — propagation config (à faire)
4. `ui/dashboard.html` — contrôles UI (à faire)
5. `tests/test_long_debate.py` — tests (créé)
