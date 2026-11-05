# ENGINE VALIDATION REPORT — 2026-11-05

**Lot** : R1 (phase 1) — stabilisation du moteur Pipeline → Worker
**Méthode** : exécution réelle des composants (`EventBus`, `Worker`/`BaseWorker`, `TaskScheduler`), plus lecture du chemin de code quand l'exécution n'est pas concluante.
**Code modifié par ce lot** : aucun (les écarts constatés sont des absences de fonctionnalité, pas des bugs à corriger ici).

## Verdict : `PARTIAL`

Le chaînage réel, la transmission de données et la gestion d'erreur fonctionnent. En revanche, **trois
capacités attendues n'existent pas** : pas de timeout, pas d'exécution réellement concurrente, pas de
reprise après interruption. Elles sont documentées ici plutôt que présentées comme acquises.

| Point du mandat | Verdict | Preuve |
|---|---|---|
| Enchaînement des étapes | `OK` | chaîne `fetch → parse → report` respectée |
| Transmission des données entre workers | `OK` | payload traversé et transformé (21 → 42) |
| Gestion des erreurs | `OK` | échec ⇒ `failed`, dépendant `blocked`, indépendant `completed` |
| Timeouts | **`ABSENT`** | aucune occurrence de `timeout` dans `core/runtime`, `core/workers`, `core/events` |
| Retries | `OK` (simulé) | `attempts: 2`, événements `started → retry → started → completed` |
| Exécution concurrente | **`SIMULÉE`** | aucun `thread`/`asyncio` dans le scheduler : horloge virtuelle |
| Persistance des états | `PARTIEL` | runs d'expériences : oui (résumés atomiques) · scheduler : non |
| Reprise après interruption | **`ABSENT`** | `continue_experiment` relance, ne reprend pas (voir §6) |
| Isolation des expériences | `OK` | répertoires par run + manifeste par expérience |
| Journalisation | `OK` | `events.jsonl` (RAW) + Event Bus + logs structurés |
| Compatibilité des providers | `PARTIEL` | fabrique et adaptateurs présents ; **aucun moteur local installé** |

---

## 1. Chaînage et transmission de données — OK

Deux workers branchés sur un vrai `EventBus`, abonnés au type `response` :

```
stage_1.execute(payload={task_id: "t-1", value: 21})
  → bus publie {task_id, value: 21, seen_by: "stage_1", doubled: 42}
messages historisés : 1 · données transportées : true
```

Le payload est bien porté d'un worker à l'autre, avec l'identité du worker ajoutée en route.

## 2. Worker sans bus — OK (dégradé proprement)

`BaseWorker(bus=None).execute(...)` ne lève pas : il journalise un avertissement et n'émet rien.
`Worker()` nu lève `NotImplementedError`, comme attendu pour une classe abstraite.

## 3. Scheduler : ordonnancement — OK

```
max_workers=2
fetch  (prio 5, dur 2) : 0 → 2
side   (prio 9, dur 3) : 0 → 3      ← priorité plus haute : démarre dans le même créneau
parse  (dép. fetch)    : 2 → 3
report (dép. parse)    : 3 → 4
durée totale : 4        chaîne respectée : true
```

Les dépendances sont honorées, la priorité est respectée à l'intérieur d'un créneau, et deux tâches
occupent les deux créneaux.

## 4. Gestion d'erreur — OK, et l'erreur est explicitement simulée

Injection d'un échec sur `load` (tentative 1) :

```
load : failed      error = "Simulated failure on attempt 1"
use  : blocked     (dépendance échouée)
free : completed   (tâche indépendante : continue)
```

Le libellé `Simulated failure` vient du moteur lui-même : il ne fait pas passer une panne réelle pour
un incident de production, et inversement.

## 5. Retries — OK (mais virtuels)

`Task(max_retries=1, retry_delays=[2])` avec échec à la 1re tentative :

```
[0 "started"] [0 "retry"] [2 "started"] [3 "completed"]   attempts: 2
```

## 6. Reprise après interruption — ABSENT (écart confirmé par le code)

`ExperimentUIController.continue_experiment` promet « continues from where it left off », mais :

```python
if state.tasks_completed > 0 and state.tasks_generated == state.tasks_completed:
    return self.restart_experiment(experiment_id)   # run terminé → repart de zéro
return self.start_experiment(experiment_id)          # sinon → nouvelle passe
```

Aucune reprise au dernier `task_index` atteint. Un run interrompu à 40/100 tâches repart donc de zéro
en s'appelant « continue ».

*Statut de la preuve* : constat **statique** (lecture du chemin d'exécution), non reproduit en
exécution live dans ce lot. À confirmer par un test dédié en R9 si cette capacité est attendue.

## 7. Timeouts — ABSENTS

```
grep -rn "timeout" core/runtime core/workers core/events   →  aucune occurrence
```

Une tâche bloquée côté worker n'a donc aucune limite de temps : elle peut bloquer l'appelant
indéfiniment. C'est une limite réelle de la V1, pas une option cachée.

## 8. Exécution concurrente — SIMULÉE, pas réelle

Le scheduler n'utilise ni `thread`, ni `asyncio`, ni `concurrent.futures`. Ses `duration` sont des
**unités abstraites** et son `clock` avance par saut. Il simule un ordonnancement : il ne fait pas
tourner deux tâches en parallèle.

Conséquence directe pour les rapports suivants : un chiffre de « temps d'exécution » issu du scheduler
n'est **pas** un temps mesuré.

## 9. Persistance et isolation — PARTIEL

| Élément | État |
|---|---|
| Résumé de run (config, état final, compteurs) | `OK` — atomique, sous `data/experiments/runs/`, rechargé au démarrage |
| Designs d'expérience | `OK` — un fichier atomique par `(id, version, statut)` |
| État du `TaskScheduler` | **aucune persistance** : `run()` réinitialise `_results`/`_events` |
| Isolation | `OK` — répertoires par run, RAW par expérience, aucune écriture partagée |

## 10. Providers — PARTIEL

Fabriques et adaptateurs présents (`core.providers`, `captn_runtime.captn.providers`), mais
l'environnement ne contient **aucun moteur d'inférence local** :

```
torch MISSING · llama_cpp MISSING · transformers MISSING · onnxruntime MISSING
```

Seuls un backend distant compatible OpenAI (LM Studio / OpenRouter) ou les chemins déterministes sont
exerçables ici.

---

## Écarts classés (pour R9)

| Écart | Nature | Décision |
|---|---|---|
| Pas de timeout | fonctionnalité absente | documenter ; ajouter en R9 si demandé |
| Concurrence simulée | simulation assumée | documenter ; ne pas présenter les durées comme mesurées |
| `continue` ≠ reprise | comportement trompeur | corriger ou renommer, après confirmation |
| Scheduler sans persistance | limite de conception | documenter |

## Non-régression

```
tests/ : 1 694 passed · 13 skipped · 0 failed   (état de référence de l'audit, inchangé par R1)
```

R1 n'a modifié aucun fichier de code : le rapport est la seule livraison.
