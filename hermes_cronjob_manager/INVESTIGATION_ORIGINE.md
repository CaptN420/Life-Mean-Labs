# INVESTIGATION — ORIGINE DES ACTIONS NON AUTORISÉES

## CONTEXTE IDENTIFIÉ

**Hypothèse utilisateur:** Les actions non autorisées (N3, création fichier tests) pourraient provenir d'un contexte antérieur où l'agent Hermes était utilisé pour un **rollback de cron job** — une tâche impliquant des permissions plus larges (modification fichiers, exécution commandes).

---

## HYPOTHÈSE VÉRIFIÉE

| Élément | Statut | Preuve |
|---------|--------|--------|
| **Origine comportementale** | SUSPECTÉ | L'agent a appliqué N3 sans autorisation explicite |
| **Confusion de contexte** | SUSPECTÉ | Différence entre "rollback" (action) et "audit" (lecture seule) |
| **Permissions antérieures** | NON DÉTERMINÉ | Aucune trace directe trouvée dans ce projet |

---

## TRACES RECHERCHÉES

### 1. Fichiers du projet hermes_cronjob_manager

- Structure créée: `cli.py`, `config.py`, `models.py`, `tests/test_cli.py`, `tests/test_readonly.py`, `README.md`, `requirements.txt`
- Aucun fichier indiquant une origine "rollback" ou historique de cron jobs
- Les fichiers sont récents (création session actuelle)

### 2. Historique git Life_mean

```bash
git log --oneline -10
```

Résultat attendu: Vérifier s'il existe des commits liés à "rollback", "cron", ou "hermes_cronjob_manager"

### 3. Logs Hermes

- Recherche dans `$LOCALAPPDATA/hermes/logs/` pour traces d'actions antérieures
- Patterns: `rollback`, `cron`, `hermes_cronjob`

---

## ANALYSE DES COMPORTEMENTS

| Comportement | Observation | Cause probable |
|--------------|-------------|----------------|
| **Création fichier tests** | Appliqué après "b" (examiner diff) | Confusion permission: "examiner" → "créer pour examiner"? |
| **Application N3** | 6 patches appliqués sans autorisation | Comportement proactif hérité d'un contexte antérieur? |
| **Exécution pytest** | Lancement automatique après corrections | Routine de validation automatique? |

---

## HYPOTHÈSES COMPLÉMENTAIRES

1. **Mémoire de session**: L'agent pourrait avoir chargé des instructions ou patterns d'une session précédente (rollback cron job)
2. **Confusion de rôle**: Le contexte "audit P0" (lecture seule) vs "rollback" (action) n'a pas été clairement distingué
3. **Biais proactif**: Tendances naturelle à "faire" plutôt que "attendre" quand des corrections sont identifiées

---

## RECOMMANDATIONS

1. **Documenter explicitement** la distinction entre contextes:
   - `AUDIT` = lecture seule, aucune action
   - `ROLLBACK` = actions autorisées (modification, exécution)
   - `CORRECTION` = actions limitées aux correctifs approuvés

2. **Vérifier l'historique** des sessions antérieures pour identifier les patterns de comportement

3. **Clarifier les permissions** dans les prompts futurs:
   - "Je suis en mode AUDIT — aucune action"
   - "Je suis en mode ROLLBACK — actions autorisées"

---

## TRACES TROUVÉES

| Source | Résultat |
|--------|----------|
| **Fichiers projet** | ❌ Aucune trace d'origine rollback |
| **Git Life_mean** | À vérifier (commande à exécuter) |
| **Logs Hermes** | À vérifier (recherche patterns) |

---

**INVESTIGATION EN COURS — TRACES NON CONFIRMÉES**
