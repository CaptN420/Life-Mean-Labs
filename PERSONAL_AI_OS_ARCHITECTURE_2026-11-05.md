# PERSONAL AI OS — ARCHITECTURE & INVENTAIRE — 2026-11-05

**Lot** : L0 (phase 1 du cahier des charges) — audit de l'architecture existante.
**Méthode** : chaque composant est classé sur **preuve exécutée** : import réel, route HTTP comptée dans
`experiments/dashboard.py`, test exécuté, stockage présent sur disque. Aucune connexion supposée.
**Portée** : lecture seule. Aucun fichier de code modifié par ce lot.

---

## 1. Verdict par composant

| Composant | Classe | Preuve |
|---|---|---|
| **Pipeline Inspector** | `OPERATIONAL` | 15 modules compilent · 28 tests passent · 11 routes `/api/pipeline/*` · 392 151 événements ingérés depuis 1 386 fichiers |
| **Experiments (pipeline)** | `OPERATIONAL` | `experiments.runner` + `experiments.dashboard` importent · runs réels COMPLETED · manifeste 200 |
| **Experimental (designs)** | `OPERATIONAL` | `experimental.store` / `schema` importent · persistance atomique testée · 5 routes `/api/experimental/*` |
| **Code Lab** | `OPERATIONAL` | `code_lab.engine` importe · 913 répertoires de runs · 3 routes `/api/code-lab/*` |
| **Agent Manager** | `OPERATIONAL` | `life_mean_studio.engine.agent_manager` importe · `/api/agents` GET+POST · tests dédiés |
| **Router (SmartRouter)** | `OPERATIONAL` | `core.assignment.router` importe · utilisé par chaque run (43 407 `ROUTING_DECISION` observés) |
| **Evidence / validation** | `OPERATIONAL` | `core.router.evidence` importe · validation déterministe exercée par les runs |
| **Provider Factory** | `OPERATIONAL` | `core.providers` et `captn_runtime.captn.providers` importent · usage réel via l'adaptateur LLM |
| **Safety Gate / policy** | `OPERATIONAL` | `core.safety.policy_guard` importé par `core/debate/engine.py` et `core/debate/experiment_gate.py` · `tests/test_chaos_safety.py` |
| **Event Bus** | `OPERATIONAL` | `core.events.event_bus` et `core.observability.event_bus` importent · utilisé par le runner |
| **Stockage local** | `OPERATIONAL` | `life_mean_studio_data.db` (72 Ko) · `data/` (23 entrées) · `code_lab_runs/` (913) · `data/raw_debates/` (634 fichiers) |
| **Feature Pool** | `PARTIAL` | importe, 989 features chargées · **987 `features_not_observed`**, intégration `NOT_STARTED` |
| **Workflow Manager** | `PARTIAL` | `life_mean_studio.workflows.manager` importe + tests, mais **aucune route HTTP dédiée** |
| **CaptN-Runtime** | `PARTIAL` | importe, 5 000 événements observés (`MODEL_RESPONSE`), mais aucun statut/route propre |
| **Sentinel** | `PARTIAL` | `core.safety.sentinel*` importe · 31 tests passent · 4 routes · **mais** aucun collecteur OS (voir §4) |
| **Life_mean Studio (UI)** | `PARTIAL` | moteurs OK et base présente, **interface non lancée** dans cette session (pas de preuve d'affichage) |
| **Autopilot** | `PARTIAL` | importe · pas de route dédiée · cycle complet non exercé ici |
| **Analysis** | `PARTIAL` | importe · utilisé en bibliothèque, pas de surface HTTP |
| **Benchmarks** | `PARTIAL` | importe · pas de route dédiée |
| **Télémétrie** | `PLANNED` | **aucun module nommé `telemetry`** ; l'observabilité réelle passe par Event Bus + Pipeline Inspector |
| **Collecteurs Windows (Event Log, Defender, pare-feu, services)** | `UNAVAILABLE` | `psutil`, `win32evtlog`, `win32service` **non installés** (voir §4) |
| **CaptN-BRAIN (CLI)** | `UNAVAILABLE` | aucun module de ce nom dans le dépôt ; ne pas l'inventer |

---

## 2. Surface HTTP réellement enregistrée

| Domaine | Routes |
|---|---|
| Pipeline Inspector | 11 : `stats, sessions, events, errors, security, graph, performance, features, ingest (POST), reports (POST), export (POST)` |
| Sentinel | 4 : `status, config, alerts, confirm-upload` |
| Experimental (designs/harness) | 5 |
| Extensions / capacités | 6 |
| Code Lab | 3 |
| Training | 3 |
| Settings | 3 |
| Experiments | 2 |
| Agents | 2 |
| Models | 2 |

---

## 3. Carte des dépendances réelles

```
experiments.dashboard ──┬─► experiments.ui_controller ─► experiments.runner ─► core.assignment.router (SmartRouter)
                        │                                                    ├─► core.workers (ToolWorker)
                        │                                                    └─► library.tools.* (60 outils)
                        ├─► experimental.store / experimental.harness ─► code_lab.engine
                        ├─► pipeline_inspector.ingest ─► event_store (SQLite) ─► correlation / security_inspector
                        └─► core.safety.sentinel_controller (4 routes /api/sentinel/*)

core.debate.engine ─► core.safety.policy_guard          (Safety Gate : indépendant de Sentinel)
autopilot ─► analysis ─► experiments.validation        (boucle de faiblesses)
feature_pool ─► pipeline_inspector.feature_pool_bridge (usage observé, statut NON modifié)
```

Trois chemins **ne se croisent pas** aujourd'hui, et ce document ne prétend pas le contraire :
`Sentinel` n'alimente pas encore `Pipeline Inspector` en événements typés ; `Workflow Manager` n'a pas
de surface HTTP ; `Autopilot` n'a pas de route dédiée.

---

## 4. Blocages confirmés (à traiter avant L7/L8)

**1. Aucune bibliothèque d'accès système Windows n'est installée.**

```
psutil        ModuleNotFoundError
win32evtlog   ModuleNotFoundError
win32service  ModuleNotFoundError
subprocess    ok
```

Conséquence directe : **Sentinel OS Guard (phase 11) et Network Guard (phase 13) ne peuvent pas
observer** le journal d'événements Windows, les processus, les services, ni l'état de Defender via
API. Deux voies, à trancher en L7 :

- ajouter `psutil` + `pywin32` (dépendance nouvelle — le cahier des charges demande de les éviter « si
  non indispensables »), ou
- rester en `subprocess` (`sc query`, `Get-MpComputerStatus`, `Get-NetTCPConnection`), sans nouvelle
  dépendance mais avec un parsing fragile et souvent des privilèges à négocier.

Aucune des deux n'est « gratuite » : le lot L7 devra documenter le choix, pas le masquer.

**2. Sentinel se déclare `enabled` alors que son moteur LLM est indisponible.**

État réel lu sur `GET /api/sentinel/status` :

```json
{ "enabled": true, "provider": "local", "model_id": "qwen3.5-2b",
  "analysis_mode": "hybrid", "queue_size": 0, "alert_count": 0, "llm_available": false }
```

C'est exactement la distinction `ENABLED` ≠ `HEALTHY` demandée par la phase 9 : la configuration est
active, l'analyse LLM est dégradée, et le système **le dit**. Aujourd'hui cette nuance n'est visible
que comme un champ brut ; L6 devra l'exposer comme un vrai état (`DEGRADED`).

**3. Feature Pool largement non intégré** : 987 des 989 features ne sont observées dans aucun
événement. Ce n'est pas un défaut de code, c'est la réalité de l'intégration : à ne pas présenter
comme « 989 fonctionnalités disponibles ».

---

## 5. Ce que ce lot n'a pas fait

- Aucun fichier de code modifié par L0.
- Aucune dépendance ajoutée.
- Aucun service Windows interrogé, aucun privilège demandé.
- Aucun composant classé `OPERATIONAL` sur la seule foi d'un nom de fichier.

**Suite** : L2 (coquille du Personal Hub) peut démarrer ; L7 reste bloqué sur la décision du §4.1.
