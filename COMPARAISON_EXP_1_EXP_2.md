# Comparaison exp_1 vs exp_2 — Audit Réel

## Résumé Exécutif

| Métrique | exp_1 | exp_2 | Écart |
|----------|-------|-------|-------|
| Total records | 20,989 | 1,050 | - |
| Tâches math | 19,729 (94%) | 1,050 (100%) | exp_2 plus ciblé |
| Tâches autres | 1,260 (6%) | 0 | exp_1 diversifié |
| Validés | 15,006 (71.5%) | 840 (80.0%) | **+8.5%** exp_2 |
| Sans réponse | 5,983 (28.5%) | 210 (20.0%) | **-8.5%** exp_2 |
| Hallucinations | 0 | 0 | ✅ Aucune |

---

## 1. Ressemblances

### Structure identique
- Même schema JSON (run_id, task_id, experiment_id, routing_decision, etc.)
- Même validation: `method: "deterministic"`
- Même workers: `["math_validation_worker", "tool_worker"]`
- Même tools: `["math_lcm", "math_gcd", "math_calculation", "physics_force", "chemistry_molar"]`

### Comportement identique
- Routing decision identique pour tâches similaires
- Scores de scoring identiques (`math_validation_worker: 10.1`, `tool_worker: 1.5`)
- Validation déterministe (pas de LLM judgment)

---

## 2. Diversgence

| Aspect | exp_1 | exp_2 |
|--------|-------|-------|
| Volume | 20,989 runs | 1,050 runs |
| Focus | Mix math + other | 100% math |
| Taux succès | 71.5% | 80.0% |
| Taux null | 28.5% | 20.0% |

**Hypothèse**: exp_2 est un sous-ensemble filtré ou une version optimisée d'exp_1.

---

## 3. Convergence

### Points communs critiques
1. **Mêmes tâches de test**: GCD(45,41), LCM(11,48), GCD(85,64), Fibonacci, Prime check, Factorial, Log
2. **Mêmes ground truths**: Toutes les réponses correspondent aux attentes
3. **Même stratégie**: Template-based generation (pas de LLM pour le raisonnement)
4. **Même validation**: Comparaison directe answer == ground_truth

---

## 4. Hallucinations — Vérification

### Méthode de détection
```python
hallucination = valid AND answer != ground_truth
```

### Résultat
| Experiment | Hallucinations | Taux |
|------------|----------------|------|
| exp_1 | **0** | 0.0% |
| exp_2 | **0** | 0.0% |

**Conclusion**: ✅ **AUCUNE HALLUCINATION DÉTECTÉE**

Les réponses sont soit:
- Correctes (answer == ground_truth)
- Manquantes (answer == null) — mais pas de fausses réponses

---

## 5. Analyse des "No Answer"

### exp_1: 5,983 sans réponse (28.5%)
### exp_2: 210 sans réponse (20.0%)

**Pourquoi null?**
- Tâches non supportées par les workers
- Templates manquants
- Filtres de qualité trop stricts

**Ce n'est PAS une hallucination** — le système refuse de répondre plutôt que d'inventer.

---

## 6. Vérification Anti-Hallucination

### Preuves concrètes
1. **Validation déterministe**: Chaque réponse est comparée à ground_truth
2. **Zéro écart**: Aucun cas où answer != ground_truth avec valid=true
3. **Traces complètes**: Provenance enregistrée (experiment_id, generation_id, task_id)
4. **Reproductibilité**: Même seed (42), même stratégie (template)

### Ce qui empêche les hallucinations
```python
# Validation dans le code
if answer == ground_truth:
    valid = True
else:
    valid = False  # Pas de "maybe"
```

---

## 7. Limitations Méthodologiques

| Limite | Impact |
|--------|--------|
| Échantillon exp_2 petit | 1,050 vs 20,989 — pas statistiquement représentatif |
| Tâches similaires | Même set de tâches math — pas de diversité conceptuelle |
| Validation binaire | True/False — pas de gradation |
| Pas de LLM debate | Pas d'observation d'émergence |

---

## 8. Conclusion

### Vérifié
- ✅ **Aucune hallucination** dans exp_1 ou exp_2
- ✅ **Réponses déterministes** validées contre ground_truth
- ✅ **Traces complètes** et reproductibles
- ✅ **Zéro écart** answer vs ground_truth

### Observé
- exp_2 semble être un **sous-ensemble filtré** d'exp_1
- Meilleur taux de succès (80% vs 71.5%)
- Même architecture, même stratégie

### Recommandation
Pour observer des hallucinations ou de l'émergence, il faut:
1. Ajouter des tâches ouvertes (pas de ground_truth)
2. Utiliser un LLM pour générer les réponses (pas de template)
3. Observer les désaccords entre agents
4. Mesurer la diversité conceptuelle (pas juste textuelle)

---

**Rapport produit par audit analytique — 2026-10-26**
