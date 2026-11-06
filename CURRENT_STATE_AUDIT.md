# CURRENT STATE AUDIT — 2026-11-05

**Mandat** : correction intégrale, non-régression et validation réelle — phase 0 (« état réel du projet »).
**Méthode** : état Git, image Docker, sondes HTTP réelles contre le serveur démarré, lectures ciblées du code, comparaison avec les rapports existants.
**Aucun code modifié par cet audit. Aucun `git push`.**

---

## 0. Instantané

| Élément | Valeur |
|---|---|
| HEAD | `4779743` fix(R2) — lmpack Studio layout |
| Commits de la session | `f381c35` (P0), `b9602bb` (trig/log), `9b43f45` (README), `a719f12` (L0/L1), `5e66cc0` (R0), `4779743` (R2) |
| Fichiers suivis modifiés | `captn_runtime/captn_experiences.jsonl` (+4 397 lignes de journal runtime), `sandbox/tools/tool-2/spec.json` (1 ligne) |
| Non suivis | sondes de debug (`_*.py`, `_*.js`), `feature_pool_*.json/csv`, `artifacts/`, `Life_mean/results/` (1 Ko) |
| Conteneur | `life_mean_realm-dashboard-1` **Up (healthy)** |
| Image | construite il y a ~1 h, **antérieure à R2** |
| Tests de référence | **1 806 passed** `tests/` + `pipeline_inspector/tests` ; **1 876 passed** sur `tests/` seul (après P17) |

### Constat opérationnel n°1 — l'image Docker ne contient pas le code courant

```
docker exec life_mean_realm-dashboard-1 grep -c PackageFormatError /app/core/packager/__init__.py
→ 0        (la correction R2 est absente de l'image)
```

`docker-compose` copie le code dans l'image (pas de bind mount) : tant que l'image n'est pas reconstruite,
le dashboard sert une révision antérieure. **Toute validation bout-en-bout faite maintenant testerait
l'ancien code.**

---

## 1. Classification des problèmes connus

| # | Problème | État | Preuve |
|---|---|---|---|
| 1 | Runs perdus au redémarrage | `FIXED_AND_VERIFIED` | `f381c35` — run `exp_adb44a31` revu après `docker compose restart` : `rehydrated: true`, 3 tâches |
| 2 | Manifeste sans version moteur/deps/git | `FIXED_AND_VERIFIED` | manifeste live : engine 1.0.0, seed 21, `dependencies.combined_sha256`, `reproducibility_fingerprint` |
| 3 | Designs d'expérience non persistants | `FIXED_AND_VERIFIED` | un fichier atomique par `(id, version, statut)` ; `history()` ; FROZEN non écrasé |
| 4 | Événements et traces absents après restart | `FIXED_AND_VERIFIED` | summary enrichi (events/traces/agents bornés), restaurés après restart ; traces vides **déclarées** avec leur cause (voir §4octies) |
| 5 | `core/packager` incapable de lire les packs livrés | `FIXED_AND_VERIFIED` | `4779743` — `valid: True`, 11 personas sur les 2 packs (avant : `False`, 0) |
| 6 | Format de pack inconnu accepté en silence | `FIXED_AND_VERIFIED` | `PackageFormatError` explicite + test sur archive bidon |
| 7 | Tâches `sin`/`log` → `None` silencieux | `FIXED_AND_VERIFIED` | `b9602bb` — seed 21 : `pass_rate 0.333 → 1.0` |
| 8 | Jetons `hf_`/`xoxb-`/`AIza`/`glpat-` en clair | `FIXED_AND_VERIFIED` | `a719f12` — 4 motifs + test de régression |
| 9 | **Image Docker obsolète** | `FIXED_AND_VERIFIED` | reconstruite : `grep -c PackageFormatError` dans le conteneur → **5** (avant : 0), conteneur healthy |
| 10 | LM Studio renvoie 401 | `NOT_APPLICABLE` — artefact de sonde | voir §2bis : l'appel réel aboutit avec le token du `.env` |
| 11 | Aucune route HTTP pour les packages LM | `FIXED_AND_VERIFIED` | `experiments/packages_api.py` : `GET /api/packages`, `GET /api/packages/inspect`, `POST /api/packages/validate`, `POST /api/packages/import` — sondes live 200 |
| 12 | Aucune UI pour charger un package | `FIXED_AND_VERIFIED` | onglet **Packages** : catalogue, détail + double verdict, boutons Inspecter / Valider / **Importer** |
| 13 | Registres Skills/Tools vides | `FIXED_AND_VERIFIED` | `/tools` expose les **60** outils réels (`catalog`) séparément du registre ; état persisté (`data/extensions/registries.json`), survit au redémarrage |
| 14 | `continue_experiment` ne reprend pas | `FIXED_AND_VERIFIED` | checkpoint par tâche ; 3/8 arrêtées → reprise exécute **5** tâches, RAW 3→8, métriques cumulées ; terminée/absente → refus motivé |
| 15 | Aucun timeout moteur | `FIXED_AND_VERIFIED` | `task_timeout_seconds` (TASK_TIMEOUT + résultat tardif jeté), `run_timeout_seconds` (RUN_TIMEOUT, reste reprenable), client LLM borné (60 s, `max_retries=0`) |
| 16 | « Concurrence » du scheduler | `NOT_APPLICABLE` (simulation assumée) | ni thread ni asyncio : horloge virtuelle |
| 17 | GPU / inférence locale | `BLOCKED_EXTERNAL` | `torch`, `llama_cpp`, `transformers`, `onnxruntime` absents (aucun collecteur à écrire : c'est une dépendance lourde, décision utilisateur) |
| 18 | Collecteurs Windows (Defender, Event Log) | `FIXED_AND_VERIFIED` | **mauvais classement** : aucun collecteur n'existait dans le dépôt, et `psutil`/`win32*` n'étaient pas nécessaires — `powershell`/`wevtutil` suffisent (voir §4duodecies) |
| 19 | Feature Pool à 987/989 non observées | `FIXED_AND_VERIFIED` (mesure) / `PARTIAL` (couverture) | l'échantillon était non représentatif : **2 → 14** observées sur la base locale, couverture déclarée ; statuts inchangés (voir §4undecies) |
| 20 | Pipeline Inspector | `FIXED_AND_VERIFIED` | `a719f12` — 392 151 événements, idempotent, 28 tests |
| 21 | `/api/agents` en dur + création non persistée | `FIXED_AND_VERIFIED` | registre réel (12 agents), toggle vérifié par relecture, doublon → 409 |

### 4bis. Défaut découvert pendant P1 : import qui dupliquait le registre

`PackageManager.import_package()` vérifiait les conflits avec `storage.get_agent(agent_id)`, alors que
`create_agent()` attribue un **UUID**. Le test ne pouvait donc jamais correspondre :

- import #1 → 11 agents ; import #2 du **même** pack → **22 agents**, `success: true`, `conflicts: 0`.

Reproduit sur base temporaire avant correction, puis corrigé :

- détection par **nom** (identité réelle d'un agent dans un pack), insensible à la casse ;
- ré-import → `success: false`, `"Nothing new: 11 item(s) already present"`, 11 conflits, **11 agents** en base ;
- le message d'échec à zéro import ne dit plus « No content imported » quand la vérité est « déjà présent ».

Persistance vérifiée : `LIFE_MEAN_STUDIO_DB=/app/studio_data/life_mean_studio_data.db` + volume nommé
`life_mean_studio_data` (l'image est `read_only: true`, sans volume l'import échouait). Contrôle réel :
11 agents en base, puis `docker compose restart` → **toujours 11**.

### 4ter. Agent Builder : deux faux succès, corrigés

`GET /api/agents` renvoyait **4 templates codés en dur** ; `POST /api/agents` fabriquait un id
(`agent_xxxx`), répondait `status: "created"` et **n'écrivait rien**. L'UI alertait « Agent created ».
Rien n'affichait donc les 11 agents importés.

Corrigé et vérifié sur le conteneur :

```
GET  /api/agents        -> 200 | source: studio_registry | total: 12 | actifs: 12
                              base: /app/studio_data/life_mean_studio_data.db
POST /api/agents/{id}/toggle {enabled:false} -> 200 enabled=False verified=True
                              actifs 12 -> 11, puis retour à 12
POST /api/agents/inconnu/toggle -> 404 agent_not_found
POST /api/agents (doublon)      -> 409 agent_exists
POST /api/agents (nouveau)      -> 200 persisted=True verified=True (UUID réel en base)
```

L'import conserve désormais le `role` du pack (ex. « Transformation ») dans `description` : il était
jeté, ce qui laissait 11 cartes identiques « general ». Réserve honnête : les 11 agents déjà importés
avant cette correction gardent une description vide — aucun rattrapage silencieux n'a été fait.

### 4quater. Reprise réelle (P3) — ce que « Continue » fait maintenant

`continue_experiment` appelait `start_experiment` (nouvelle exécution depuis la tâche 0) et, pour une
expérience terminée, `restart_experiment` en silence. Le bouton « Continue » ne continuait rien.

Désormais chaque tâche terminée écrit **sa preuve RAW puis sa ligne de checkpoint** (dans cet ordre :
on ne saute que ce qui a laissé une trace). Les identifiants de tâches étant des UUID aléatoires, la
reprise s'appuie sur l'**index + empreinte du contenu** (domaine, difficulté, description, vérité
terrain) : si le contenu régénéré diffère, la reprise est **refusée** au lieu de mélanger deux
exécutions.

Mesure réelle (script hors pytest, `LIFE_MEAN_RUNS_DIR` temporaire) :

```
APRÈS ARRÊT (8 tâches prévues, stop après la 3e)
  checkpoint : {'total': 8, 'seed': 42, 'domain': 'math'}
  entrées    : 3   indices: [0, 1, 2]
  lignes RAW : 3
APRÈS CONTINUE
  tâches réexécutées : 5      ← les 3 premières ne sont pas relancées
  entrées checkpoint : 8      indices: [0..7]
  lignes RAW         : 8
  état UI : completed=8 valid=8 pass_rate=1.000
REFUS
  sans checkpoint     : False — « aucune progression enregistrée »
  expérience terminée : False — « déjà terminée (2/2 tâches) »
```

L'API renvoie 409 `resume_refused` avec la raison (avant : 500 générique « Failed to continue »), et
l'UI affiche ce message. Un checkpoint antérieur est **archivé** (`.jsonl.bak`), jamais supprimé.

Mesure réelle en HTTP contre le conteneur (expérience de 4 000 tâches, arrêtée en cours de route) :

```
POST /api/experiments/{id}/stop   -> 200
après stop   : completed=975/4000   checkpoint=976 lignes   RAW=975 lignes
POST /api/experiments/{id}/continue -> 200 {"status": "resumed"}
après reprise: completed=4000/4000  checkpoint=4001 lignes  RAW=4000 lignes
POST continue (2e fois) -> 409 resume_refused
```

Exactement une ligne RAW et une ligne de checkpoint par tâche, aucune tâche exécutée deux fois.

### 4quinquies. Transparence — un test existant a été adapté (sans être affaibli)

La boucle déterministe exécute désormais **tâche par tâche** (`run_task`) au lieu d'un `run_batch` :
c'est la condition d'un checkpoint par tâche. `tests/test_qa_fixes.py::test_runner_loop_sets_valid_counts`
simulait un `run_batch` renvoyant deux résultats ; le simulacre a été déplacé sur `run_task`.

- assertions **conservées** : `tasks_valid == 1`, `tasks_invalid == 1`, `tasks_completed == 2`,
  `pass_rate == 0.5` ;
- assertion **ajoutée** : `run_task.call_count == 2` (une exécution par tâche, aucune reprise).

Aucun seuil abaissé, aucun test supprimé.

### 4sexies. Timeouts moteur (P4)

Il n'existait **aucun** timeout dans `core/runtime`, `core/workers`, `core/events`, ni dans le runner :
un outil bloqué figeait l'expérience indéfiniment. Pire, `LLMClient` construisait
`OpenAI(base_url=..., api_key=...)` **sans timeout** — donc le défaut de 600 s, avec retries.

Trois garde-fous, tous explicites :

| Garde-fou | Réglage | Comportement |
|---|---|---|
| Tâche | `task_timeout_seconds` (défaut 120 s, 0 = désactivé) | au-delà : résultat `TASK_TIMEOUT`, `is_valid=False`, aucune réponse inventée ; le thread abandonné est un daemon et **son résultat tardif est jeté** (jamais compté deux fois) |
| Exécution | `run_timeout_seconds` (défaut 0 = désactivé) | au-delà : arrêt propre, erreur `RUN_TIMEOUT`, tâches déjà enregistrées **reprenables** ; le délai se réarme à chaque reprise |
| Appel LLM | `LIFE_MEAN_LLM_TIMEOUT_SECONDS` (défaut 60 s) ou `LLMClient(timeout=…)` | `timeout` passé au client ET à chaque requête, `max_retries=0` ; dépassement → `finish_reason="timeout"` et texte `[LLM_TIMEOUT …]`, jamais un succès silencieux |

Mesures réelles :

```
# client LLM, dans le conteneur, backend réel (29 modèles)
timeout client: 60.0
normal      -> finish_reason=length  | 1.87s
timeout 1ms -> finish_reason=timeout | 0.01s | '[LLM_TIMEOUT after 0.00s: no answer within 0.001s]'

# garde-fou d'exécution, via HTTP (run_timeout_seconds=2, 4000 tâches)
après garde-fou : completed=1365/4000  running=False
  RUN_TIMEOUT: l'exécution a dépassé 2s — arrêtée à 1365/4000 tâches ; les tâches enregistrées restent reprenables.
continue        -> 200 resumed
après reprise   : completed=2776/4000  (le délai se réarme : 2e RUN_TIMEOUT enregistré)
```

Réserve honnête : Python ne tue pas un thread. Une tâche expirée continue donc en arrière-plan
(daemon) ; son résultat est ignoré, mais elle consomme encore du CPU/IO jusqu'à sa fin naturelle.

### 4septies. Registres d'extension (P5) — trois défauts, pas un « total: 0 »

Le rapport annonçait « registres vides ». En creusant, `total: 0` était à la fois **vrai** et
**trompeur**, et deux bugs empêchaient de le peupler :

1. **60 outils réels invisibles.** `library/tools` fournit 60 outils déterministes, utilisés à chaque
   exécution par `ToolWorker`, mais le registre d'auto-extension n'en connaissait aucun. Désormais la
   réponse sépare explicitement `catalog` (les 60, `in_registry: false`) de `all`/`stats` (le registre
   d'approbation). Faire apparaître un outil n'est pas l'activer — c'est écrit dans la réponse.
2. **Aucune persistance.** Les registres vivaient en mémoire : `POST /api/extensions/tools` répondait
   `proposed` et tout disparaissait au redémarrage. Ajout de `life_mean_extensions/store.py`
   (`data/extensions/registries.json`, écriture atomique, `.bak` conservé), rechargé à la création de
   la couche. Un échec d'écriture ne devient jamais un succès : `500 persistence_failed`
   (« applied in memory but NOT persisted »).
3. **Porte d'approbation injoignable.** Deux causes cumulées : `_ID_RE` n'acceptait pas le suffixe
   d'action (`/approve` → 404) et `do_PUT` ne routait que `/api/settings`. Corrigées : le cycle
   complet fonctionne maintenant en HTTP.

Mesures réelles contre le conteneur :

```
GET  /api/extensions/tools   -> registre total 0, catalogue 60  (avant toute proposition)
POST /api/extensions/tools   -> 200 tool-183485ab | persisted True
POST /api/extensions/tools   -> 200 tool-5ca351b9 | ids distincts (avant : un seul id partagé)
PUT  .../tool-183485ab/approve  -> 200 approved  persisted True
PUT  .../tool-183485ab/activate -> 200 active    persisted True
PUT  .../tool-183485ab/disable  -> 200 disabled  persisted True
docker compose restart
GET  /api/extensions/tools   -> 3 tools conservés (2 proposed, 1 disabled)
```

Troisième bug trouvé en chemin : `POST /api/extensions/tools` **coupait la connexion** au lieu de
répondre, parce que `OSError` (système de fichiers en lecture seule) s'échappait du handler avant
l'envoi. Le bac à sable des outils générés vivait dans `/app/sandbox` (image en lecture seule) ; il est
maintenant sous `data/sandbox/` (volume inscriptible) et les erreurs de proposition renvoient
`500 proposal_failed`.

Réserve honnête : `skills` reste à **0** — il n'existe aucune source de skills dans ce dépôt
(pas de `skills/`, rien dans les `.lmpack`). La réponse liste les sources vérifiées au lieu de laisser
croire à une panne.

---

### 4octies. Événements/traces après restart (P6) — persister, ou dire pourquoi c'est vide

Le summary de run ne stockait que `state` + `config`. Après un restart, le manifeste répondait donc
`events: []` / `traces: []` : honnête, mais le dashboard ne pouvait plus dire **pourquoi** un run
s'était terminé ainsi.

Ce qui a changé :

- le summary porte maintenant un bloc `observability` : `agents`, `events` (plafond 500) et `traces`
  (plafond 200), plus `totals`, `truncated` et `limits` — une troncature est toujours déclarée ;
- `rehydrate_from_summaries()` restaure ce bloc ; `GET /api/experiments/{id}/observability` et
  `/manifest` renvoient la même forme qu'un tracker vivant, avec `rehydrated: true`.

Relevé réel (conteneur, run `exp_d58c53de`) :

```
avant restart  fichier /app/data/experiments/runs/exp_d58c53de.json
               events 2, traces 0, agents 3, limits {events:500, traces:200}
docker compose restart dashboard
après restart  GET /manifest -> rehydrated True
               events restaurés 2 (experiment_started, experiment_completed), agents 3
               note « (2 of 2 events, 0 of 0 traces) »
               progress: COMPLETED, tasks_completed 3
```

**Défaut trouvé en chemin, non corrigé car hors périmètre** : les traces déterministes ne sont
**jamais produites**. `record_transition()` et `record_rule_application()` existent dans
`experiments/observability.py` mais n'ont **aucun appelant** dans le dépôt (`grep` sur tout le code
hors `observability.py` : 0 hit). Les manifestes annonçaient donc une section « traces » toujours vide
sans le dire. La réponse porte désormais `traces_absent_reason` (manifeste vivant **et** rehydraté) :
un build qui ne produit pas de traces le déclare au lieu de laisser croire à une perte. Les événements,
eux, sont réels mais rares : 2 à 3 par run (`experiment_started` / `experiment_completed`), l'essentiel
de la preuve vivant dans le RAW jsonl.

Second point relevé pendant la manipulation HTTP : `POST /api/experiments` ne fait que **créer** le run
(`status: created`) ; il faut ensuite `POST /api/experiments/{id}/start`. Un run « terminé » avec
`tasks_completed: 0` vu juste après la création vient de là, pas d'un bug du moteur.

### 4nonies. Traces déterministes réellement produites (P8)

Constat de P6 : `record_transition()` et `record_rule_application()` existaient, étaient exposés dans
chaque manifeste… et n'avaient **aucun appelant**. `update_progress()` non plus. Trois mécanismes
annoncés, jamais alimentés.

Câblage réalisé :

- `ExperimentRunner` publie ses deux décisions déterministes par tâche via un `trace_sink` optionnel :
  `RoutingRule` (entrée : tâche/domaine/difficulté → sortie : workers et outils retenus) et
  `ValidationRule` (entrée : réponse + vérité terrain → sortie : `valid`/`method`/`error`) ;
- un sink qui lève n'échoue jamais une tâche (avertissement journalisé, test dédié) ;
- la boucle d'exécution appelle désormais `update_progress(tasks_completed, tasks_total, current_step,
  elapsed_seconds)` après chaque tâche et une fois à la fin.

Relevé contre le conteneur (run `exp_97f1c8e1`, 3 tâches) :

```
progression: tasks_completed 3, tasks_total 3, current_step 'finished', total_rounds 3
traces: 6  ['RoutingRule', 'ValidationRule']
events: 8  | traces_absent_reason: None
exemple: ValidationRule  in {task_id, answer 24, ground_truth 24} -> {valid true, method deterministic}
```

Avant ce correctif, le même run affichait `tasks_completed: 0` et `traces: []`. Les manifestes portent
toujours `traces_absent_reason`, mais seulement quand la liste est réellement vide (mode débat), avec
une raison exacte.

### 4decies. Le « flake » CSRF était un reset TCP, pas de la concurrence (P9)

Après la correction de P7, c'est `test_state_changing_with_wrong_token_is_403` qui a échoué sur un
passage complet — le second test signalé comme instable dans le §6 initial. Reproduit **hors suite** :
1 échec sur 12 exécutions du seul fichier. Trace capturée :

```
ConnectionAbortedError: [WinError 10053] Une connexion établie a été abandonnée …
```

Cause : `do_POST`/`do_PUT`/`do_DELETE` répondaient **403 avant de lire le corps** de la requête. Windows
réinitialise une socket fermée avec des données non lues : le client ne voyait jamais la réponse, selon
le moment où il finissait d'écrire (d'où 1 échec sur 12).

A/B mesuré sur 60 requêtes POST avec corps de 4 Ko et jeton invalide :

```
SANS drain (ancien comportement) : 403 reçus 53/60, connexions avortées 7/60
AVEC drain (corrigé)             : 403 reçus 60/60, connexions avortées 0/60
```

Correctif : `_drain_request_body()` lit et jette le corps (plafonné à 1 Mo) avant toute réponse 403 des
trois verbes ; un test de régression martèle 25 fois la même requête et exige 25 fois 403. Le fichier
passe désormais 10/10 exécutions consécutives (avant : 1 échec sur 12).

### 4undecies. « 2 fonctionnalités observées sur 989 » était un artefact d'échantillon (P10)

`GET /api/pipeline/features` ne lisait que les **N événements les plus récents par type**
(`limit=20000` sur `TOOL_CALL`, `5000` sur les trois autres). Sur la base réelle du poste
(837 054 événements), cette fenêtre était monopolisée par un seul producteur : 5 005 événements
`captn_experiences`/`captn_runtime`. Les 815 991 événements `raw_debates` — ceux qui portent
`tool_worker`, `math_validation_worker`, `router`, `bug_worker`… — n'étaient jamais lus.

Mesure avant/après sur la base locale :

```
avant : features_observed 2   / 989   | events scannés 5 005
après : features_observed 14  / 989   | events scannés 4 500 sur 25 populations
        populations en base : 1 112 272 événements (tronqué : oui)
        top : CriticAgent 442, IntegrationPlanner 304, SyntaxWorker 300, BugWorker 300,
              PolyglotCoder 300, DeterministicCoder 300, Worker 300, FixGenerator 300
```

Correctif : `EventStore.distinct_values()` (colonnes en liste blanche — une valeur d'API ne devient
jamais un nom de colonne SQL) et `PipelineInspector._stratified_events()` qui échantillonne **par
population** (agent, puis source), avec un quota identique par groupe. Le payload et le rapport
Markdown portent désormais `coverage` : stratégie, nombre de populations, quota, événements dans les
populations échantillonnées, `truncated`.

**Chiffres conteneur, différents et honnêtes** : la base du conteneur ne contient que **18 447**
événements (`text_log` + `captn_experiences`) — `/app/data` est un volume qui masque
`data/raw_debates`, donc les 815 k événements `raw_debates` n'y sont pas ingérés. Le conteneur affiche
donc `features_observed: 2` avec `groups_sampled: 6`, ce qui est cohérent avec SA base : ce n'est plus
un artefact d'échantillonnage mais un manque de données, et la réponse le déclare (`coverage`).

Reste ouvert et assumé : **987 fonctionnalités non observées** sur 989. Ce n'est pas un défaut à
corriger par du code : la majorité du pool (widgets Qt, stores, classes de sécurité) n'est jamais
instanciée par les pipelines qui tournent ici. Le rapport continue de dire « usage observé ≠
validation » et ne modifie aucun statut.

### 4duodecies. « Collecteurs Windows bloqués » était un mauvais classement (P11)

L'audit rangeait les collecteurs Defender / Event Log en `BLOCKED_EXTERNAL` au motif que `psutil`,
`win32evtlog` et `win32service` étaient absents. Deux erreurs dans ce constat :

1. **Aucun collecteur n'existait dans le dépôt** (`grep -rn "Defender\|win32evtlog\|collector"` sur tout
   le code : rien de système — seul `core/router/evidence.py` utilise le mot « collector » pour des
   preuves de raisonnement). Ce n'était donc pas « bloqué par une dépendance », mais **non écrit**.
2. **Les dépendances ne sont pas nécessaires** : Windows fournit `powershell` et `wevtutil`. Un
   `pip install psutil pywin32` aurait ajouté du poids pour deux appels système ponctuels.

Nouveau module `core/safety/os_collectors.py` (zéro dépendance pip) :

- `defender_status()` → `Get-MpComputerStatus` (protection temps réel, antivirus, date de signature) ;
- `recent_events(log, count)` → `wevtutil qe … /f:xml` parsé en `{event_id, level, provider,
  time_created, computer}` ;
- `os_snapshot()` → les deux, avec `degraded` listant ce qui n'a pas répondu.

Contrat tenu : aucune exception ne remonte, sortie bornée (≤ 50 événements, 512 Ko, timeout),
`ok`/`error` explicites, et **jamais** de valeur inventée quand la source ne répond pas.

Mesures réelles, route `GET /api/sentinel/os` :

```
dashboard hôte (Windows 11) :
  host platform Windows, supported true, degraded []
  defender: ok true, real_time_protection true, antivirus_enabled true, signature 1793882711
  event_log: ok true, count 3
             {"event_id":"10016","level":"warning","provider":"Microsoft-Windows-DistributedCOM", ...}
             {"event_id":"19","level":"information","provider":"…WindowsUpdateClient", ...}

conteneur Docker (WSL2, Linux) :
  host platform Linux, supported false, degraded ["defender","event_log"]
  defender: ok false, error "not a Windows host"
```

Le conteneur ne peut pas lire le Defender de l'hôte : il le **dit** (`supported: false`) au lieu de
renvoyer un état plausible. La route est utile sur le dashboard hôte (`--port 8082`), ce qui est
exactement là où la télémétrie système a un sens.

Reste `BLOCKED_EXTERNAL` : le GPU / l'inférence locale (#17) — dépendances lourdes (`torch`,
`llama_cpp`), décision d'installation qui revient à l'utilisateur, rien à corriger dans le code.

### 4terdecies. Exposition UI : télémétrie système et couverture d'échantillon (P12)

Deux données réelles étaient produites par l'API mais invisibles dans le dashboard :

- **Onglet « Système »** (`panel-system`) : hôte (nom, plateforme, supporté), ligne `degraded`, cartes
  Defender (temps réel / antivirus / anti-spyware / date de signature) et table des 5 derniers
  événements système. Une source en échec affiche **sa raison** (texte rouge) au lieu d'une valeur
  plausible.
- **Ligne de couverture** dans la carte *Feature Pool ↔ Pipeline* : « 14 observées / 989 chargées —
  4500 événements répartis sur 25 populations (tronqué) — 1 112 272 événements dans ces populations ».
  Sans elle, « 14 » se lisait comme un total.

Vérification réelle, navigateur piloté sur le dashboard hôte (`:8082`) :

```
onglet Système   -> « Hôte CN — Windows 11 — supporté: true », « ✔ Toutes les sources ont répondu »
                    Defender: temps réel true, antivirus true, anti-spyware true,
                    signature 05/11/2026 07:45:11
                    événements: 566 Kernel-Power, 114 HttpService, 7040 Service Control Manager
onglet Pipeline  -> « 14 observées / 989 chargées — 4500 événements répartis sur 25 populations »
                    lignes: CriticAgent 442, IntegrationPlanner 304, SyntaxWorker 300
```

Les 4 blocs `<script>` du dashboard passent `node --check` après modification (un `const` dupliqué
neutralise tout un bloc : c'est vérifié, pas supposé).

### 4quaterdecies. Journal d'usage runtime + faux positif d'appariement (P13)

Le compte « usage observé » dépendait entièrement de ce que l'ingestion de logs avait conservé. Nouveau
journal d'exécution : `experiments/usage_recorder.py` écrit **une ligne par composant réellement
exécuté** (`data/usage/feature_usage.jsonl`, append-only, `experiment_id` + `task_id` + horodatage), et
le pont Feature Pool fusionne deux sources déclarées séparément :

```
usage_sources: {"logs": {...}, "runtime": {"records": 22, "features_observed": 1}}
```

Relevé réel sur un run de 3 tâches : 6 lignes = `ToolWorker` + l'outil **réellement détecté**
(`math_is_prime`, `math_trig`, …). Une première version enregistrait les cinq outils de la famille du
routeur — corrigée : l'émission se fait là où `detect_tool()` répond, pas après coup.

**Faux positif trouvé pendant la mesure** : `math_gcd` comptait comme un usage de la fonctionnalité
« C ». Le matcher de secours faisait `candidate_key in key` sans garde de longueur sur
`candidate_key`, donc toute feature au nom court (une lettre, un acronyme) absorbait les entités qui la
contenaient. Corrigé (les deux côtés doivent faire ≥ 6 caractères). Effet mesuré sur la base locale :
**14 → 13** fonctionnalités observées — le quatorzième était ce faux positif.

Mesures après correction, base locale : `CriticAgent 442`, `ToolWorker 311` (300 logs + 11 runtime),
`SyntaxWorker 300`, `BugWorker 300`. Conteneur (base réduite à 18 k événements) : 2 observées dont
`ToolWorker` via `runtime` sur 8 exécutions réelles.

### 4quindecies. Onglet « Traces » — les décisions deviennent consultables (P14)

Les traces `RoutingRule`/`ValidationRule` existaient dans l'API mais n'étaient lisibles qu'en JSON. Nouvel
onglet **Traces** : sélection d'un run, filtre par règle (Toutes / Routing / Validation), table
`heure · règle · tâche · entrée · sortie`, et une ligne de contexte qui dit d'où vient la donnée
(« run rehydraté depuis le résumé persisté — 4/4 traces conservées », ou la raison quand il n'y en a pas).

Vérifié au navigateur contre le conteneur (`:8080`) :

```
options   : exp_40f9b76b — COMPLETED (2 tâches), exp_bd923aee, exp_97f1c8e1, exp_3e1ae21c, exp_d58c53de…
sélection : exp_40f9b76b
note      : « run rehydraté depuis le résumé persisté — 4/4 traces conservées »
compteur  : 4 / 4 traces   → filtre ValidationRule : 2 / 4 traces
lignes    : ValidationRule task_d72593db  {answer 6, ground_truth 6}  -> {method deterministic, valid true}
            RoutingRule    task_d72593db  {domain math, difficulty 1} -> {selected [math_validation_worker, …]}
```

Les 4 blocs `<script>` passent `node --check` ; `tests/test_dashboard_ui.py` + `test_dashboard_security.py` :
49 passed.

### 4sexdecies. Le journal d'usage couvre les agents de débat (P15)

Le journal runtime ne voyait que le pipeline déterministe (`ToolWorker` + outil détecté). Les débats
multi-agents ne laissaient aucune trace d'usage : les personas réellement sollicités étaient invisibles
du décompte.

`AutoPilot` publie désormais une ligne par couple `(agent, modèle)` ayant produit **au moins un tour avec
du contenu** — un persona muet (tour rejeté par le garde de répétition) n'est pas compté, sinon le journal
mesurerait le casting au lieu de l'exécution. Le sink est optionnel et un sink qui lève ne casse jamais un
débat (5 tests dédiés, dont un bout-en-bout sink → `FeatureUsageRecorder` → fichier JSONL).

**Appariement des noms, deuxième correction** : la règle « ≥ 6 caractères des deux côtés » introduite en
P13 bloquait un nom court légitime — `Stoic` ne trouvait pas `StoicAgent` (feature existante), alors que
`math_gcd` devait rester non apparié. La règle est maintenant : **sous-chaîne, candidat ≥ 4 caractères,
et un seul candidat possible** (ambiguïté ⇒ aucun match). Vérifié : `Nihilist → NihilistAgent`,
`Existentialist → ExistentialistAgent`, `Pragmatist → PragmatistAgent`, `Socrates → SocratesThinker`,
`Stoic → StoicAgent`, `math_gcd → aucun`.

Mesure locale après correction : **12 features observées / 989** (contre 13 avec l'ancien matcher
permissif — l'écart est le faux positif retiré), **1 161 exécutions runtime** enregistrées, et les outils
non appariables (`math_gcd` 169, `math_fibonacci` 129, `math_factorial` 91…) restent listés dans
`unmapped_entities` : ce sont des fonctions, pas des classes du pool — le dire vaut mieux que les
rattacher de force.

### 4septiesdecies. Outils mathématiques : analyse exacte, refus explicites (P16)

Mission dédiée (rapport d'audit) : `sin(144 degrees)` et `log(28)` doivent produire un nombre,
toute opération non prise en charge doit échouer explicitement.

État à l'ouverture : `sin`/`cos`/`tan`/`log`/`sqrt` étaient détectés et `log` recevait déjà `base=e`.
**Trois défauts réels trouvés en exécutant, pas en relisant** :

| Cas | Avant | Après |
|---|---|---|
| `sqrt(-1)` | **réponse 1.0** (le `re.findall(r"\d+")` perdait le signe) | `MATH_DOMAIN_ERROR`, aucun nombre |
| `tan(90 degrees)` | `1.633e16` (cos calculé en degrés, `tan: "inf"`) | `tan: None` + `tan_undefined`, `MATH_DOMAIN_ERROR` |
| `2^8` | `answer None` sans erreur (worker re-détectait, aucun mot-clé) | `256.0`, via `tool_name` transmis |

Nouveau module `library/tools/math_expressions.py` : grammaire **fermée**, sans `eval` ni LLM —
`nom(args)` et `a^b` sur littéraux, `pi`, `e`. Il dit quoi appeler **et** avec quoi (arité, unité,
base), ce que la détection par mots-clés ne savait pas faire. Unités explicites : `degrees`/`deg`/`°`,
`radians`/`rad`, et un littéral en π sans unité vaut des radians (`sin(pi/2)`), jamais des degrés.
Bases documentées : `ln(x)` = `log(x)` = naturel, `log10(x)` = 10, `log2(x)` = 2, `log(x, b)` = b.

Ajouts d'outils/détection : `exp`, `pow`, `ln`, `log10`, `log2` (scores > `log` pour que la base ne soit
pas devinée en aval) ; `trig` accepte `angle_rad` à côté de `angle_deg` et refuse les deux à la fois.

Refus structurés conservant l'expression : `UNSUPPORTED_MATH_OPERATION` (opération inconnue, arité
fausse, argument non littéral, expression incomplète) et `MATH_DOMAIN_ERROR` (verdict de l'outil :
`sqrt(-1)`, `log(0)`, `log(-5)`, `tan(90°)`). Un dict d'erreur ne peut plus devenir une « réponse » —
`ln(0)` renvoyait `{'valid': False, 'error': 'value>0'}` dans `answer`.

Traçabilité : nouvelle règle `MathExpressionRule` (expression demandée, outil retenu, paramètres
normalisés, unité, verdict, raison). Vérifiée en exécution réelle via le contrôleur :

```
expr: Calculate sin(144 degrees) | tool: math_trig | params: {'angle_deg': 144.0} | answer: 0.587785
expr: Calculate log(28)          | tool: math_log  | params: {'value': 28.0, 'base': 2.718…} | answer: 3.332205
```

61 tests dédiés (`tests/test_math_expressions.py`) : analyse, unités, bases, domaines invalides,
entrées malformées, opérations inconnues, traçabilité, non-régression `gcd`/`lcm`/`factorial`/
`fibonacci`/`is_prime`.

### 4octodecies. Branchement complet : générateur, outils, run, dashboard (P17)

Un outil supporté ne vaut que si une tâche peut l'atteindre. Le générateur n'émettait que `sin` et
`log` ; `cos`, `tan`, `ln`, `log10`, `sqrt`, `exp`, `pow` étaient routables mais jamais produits.

Générateur (`experiments/generation/task_generator.py`) : 11 familles émises, avec des domaines
garantis — `tan` tiré hors des singularités (`_TAN_SAFE_ANGLES` exclut 90° + k·180°), logs sur des
valeurs > 1, `sqrt` ≥ 0, `exp` sur 0..6, `pow` sous les deux formes `2^8` et `pow(2, 8)`.

**Vérité terrain calculée par le même outil que la réponse** : `_compute_math_ground_truth` appelle
`parse_math_task` + `MATH_TOOLS[...]`. Une divergence de convention (base du log, unité d'angle)
devient impossible par construction au lieu d'être rattrapée après coup.

Piège corrigé en route : `reasoning_type="calculation"` (le défaut) avait été branché sur la
trigonométrie, ce qui transformait **toutes** les tâches mathématiques en sinus (mesuré : 300 tâches,
3 familles). Corrigé — `calculation` reste varié, seuls `trig`/`trigonometry` forcent le trio.

Mesure réelle (8 seeds × 80 tâches = 640 tâches, exécution complète par `ExperimentRunner`) :
**640 tâches, 0 échec**, toutes les familles exercées (`tan` 50, `sin` 50, `log` 46, `exp` 45,
`pow` 44, `ln` 43, `sqrt` 42, `log10` 37, `cos` 35, plus `gcd`/`lcm`/`factorial`/`is_prime`/`fibonacci`).

Dashboard : `ExperimentState.error_codes()` agrège les erreurs par code machine
(`MATH_DOMAIN_ERROR`, `UNSUPPORTED_MATH_OPERATION`…), exposé en `error_count` / `error_codes` et affiché
sur la carte du run (`Erreurs: 3 [MATH_DOMAIN_ERROR×3]`). Une erreur non reconnue est classée
`UNCLASSIFIED`, jamais inventée.

9 tests dédiés (`tests/test_math_end_to_end.py`) ; 2 tests existants ajustés (jeux de règles de traces)
pour admettre `MathExpressionRule` sans relâcher l'exigence sur les deux règles structurantes.


**Complément `/manifest`** : le bloc `progress` n'exposait que `tasks_completed` — un run terminé annonçait
24/24 sans dire s'il était bon. Il porte maintenant `tasks_valid`, `tasks_invalid`, `pass_rate`
(`None` tant que rien n'est validé, jamais 0 trompeur). Mesuré dans le conteneur après rebuild :

```
progress: {status: COMPLETED, tasks_completed: 18, tasks_valid: 18, tasks_invalid: 0, pass_rate: 1.0}
carte   : {status: COMPLETED, tasks_valid: 18, pass_rate: 1.0, error_count: 0, error_codes: {}}
familles: cos, log, log10, pow, sin, sqrt, tan, exp, ln
```

## 2. Sondes HTTP réelles (serveur démarré)

| Route | Code | Charge utile |
|---|---|---|
| `/api/experiments` | 200 | 813 o (registre réel) |
| `/api/training/runs` | 200 | `{"runs": [], "total": 0}` — route fonctionnelle, aucune exécution |
| `/api/models` | 200 | `{"models": [], "total": 0}` — registre vide |
| `/api/agents` | 200 | 439 o |
| `/api/role-templates` | 200 | 3 999 o |
| `/api/experimental/capabilities` | 200 | 2 374 o (exécuteurs + `connected`) |
| `/api/experimental/designs` | 200 | 15 o (`[]`) |
| `POST /api/experimental/harness/start` | **400** `missing_executor` | validation réelle d'entrée — pas de faux `200` |
| `/api/extensions/skills` · `/tools` | 200 | `total: 0` — registres vides |
| `/api/pipeline/stats` | 200 | 664 o |
| `/api/sentinel/status` | 200 | `enabled: true`, `llm_available: false` |
| `/api/settings` | 200 | 18 608 o (clé OpenRouter configurée : `true`) |
| `/api/packages` · `/api/workflows` · `/api/lmpack` | **404** | **absentes** |

Aucune route ne renvoie `200` avec un contenu mensonger : `harness/start` refuse explicitement une
requête incomplète, et les registres vides le disent (`total: 0`) au lieu d'inventer des entrées.

---

## 3. Providers et modèles

### 2bis. Correction d'un constat de cet audit — LM Studio fonctionne

Le §3 initial classait LM Studio en `CONFIRMED_BROKEN` sur la base d'un `401`. **Ce constat était faux** :
il provenait d'une sonde lancée **depuis l'hôte**, sans en-tête d'authentification, sur un nom
(`host.docker.internal`) qui ne résout que depuis le conteneur.

Vérification faite dans l'environnement réel de l'application (`.env` chargé par `env_file`) :

```
GET  {LIFE_MEAN_LLM_BASE_URL}/models   →  HTTP 200, 29 modèles
POST {…}/chat/completions  model=qwen3.5-2b  →  HTTP 200 en 6.59 s
    model renvoyé : qwen3.5-2b   usage : 24 tokens (8 de raisonnement)
GET /api/settings → provider_models[lm_studio].key_configured = true, 26+ modèles
```

Le backend local est donc **opérationnel et authentifié**. Réserve honnête : le modèle `qwen3.5-2b`
consomme des tokens de raisonnement, donc un `max_tokens` trop court renvoie un contenu vide — ce n'est
pas une panne mais un paramétrage à surveiller côté appels.

### 3. Providers déclarés

| Élément | Constat |
|---|---|
| Providers déclarés | `lm_studio`, `openrouter` |
| Clé OpenRouter | configurée (`openrouter_key_configured: true`) |
| Modèles disponibles | liste peuplée (`available_models`, 10+ entrées) |
| LM Studio | **opérationnel** — 29 modèles servis, complétion réelle en 6.59 s (§2bis) |
| Provider par défaut | `general.provider: null` — aucun provider sélectionné explicitement |

**Aucune intervention nécessaire** : le `.env` contient déjà `LIFE_MEAN_LLM_BASE_URL`,
`LIFE_MEAN_LLM_API_KEY` et `OPENROUTER_API_KEY`, et `docker-compose` les injecte via `env_file`.
Le `401` observé venait d'une sonde hors conteneur (voir §2bis) — pas d'une configuration manquante.

---

## 4. Priorisation (phases suivantes)

| Priorité | Problème | Phase |
|---|---|---|
| **P0** | Image Docker obsolète (toute validation porte sur du vieux code) | 8 |
| **P1** | Aucune route/UI de chargement de package LM | 3 / 4 / 8 |
| **P1** | LM Studio 401 (backend indisponible) | 5 |
| **P1** | Événements/traces non persistés (décision à trancher, sans invention) | 1 |
| **P2** | `continue` qui ne reprend pas | 1 / 6 |
| **P2** | Aucun timeout moteur | 6 |
| **P2** | Registres Skills/Tools vides | 7 |
| **P3** | Feature Pool 987/989 non observées | 7 |
| **Externe** | GPU, collecteurs Windows | 6 / hors périmètre |

---

## 5. Ce que cet audit ne fait pas
- Il ne re-corrige aucun des problèmes déjà marqués `FIXED_AND_VERIFIED` (règle explicite du mandat).
- Il ne présente pas `total: 0` comme une panne : ce sont des registres réellement vides.
- Il ne touche ni aux packages, ni aux datasets, ni aux historiques.
- Il n'exécute aucun `git push` : les commits restent locaux jusqu'à autorisation explicite.

---

## 6. Le test instable est expliqué et neutralisé (cause mesurée, plus « inconnue »)

`tests/test_dashboard_security.py::…::test_default_bind_is_loopback` avait échoué une fois sur un passage
complet, puis passait seul et dans tous les sous-ensembles. Il n'était ni « aléatoire » ni lié à la
concurrence des serveurs in-process : il lisait sa cible avec `inspect.getsource`, qui décrit le fichier
**tel qu'il était à l'import**.

Mécanisme reproduit par sonde (`scratch/linecache_probe.py`), sur `experiments/dashboard.py` réel :

```
A. avant réécriture  : assertion = True   | 1re ligne = 'def start_dashboard('
B. fichier réécrit (3 lignes vides en tête, sémantique inchangée)
   pendant le run    : assertion = False  | 1re ligne =
                        '            self._send_error(500, f"Failed to start training: {e}", co'
C. fichier restauré  : sha256 identique
```

Décaler les lignes invalide tous les `co_firstlineno` enregistrés à l'import : linecache relit le
**nouveau** fichier et `getsource` le tranche aux **anciennes** lignes, donc renvoie le corps d'une autre
fonction. Le fragment observé lors de l'échec réel était exactement de cette famille
(`self._send_error(500, f"Failed to start training: …`) — c'est la trace laissée dans le rapport.

Correction (aucune assertion affaiblie) :

- `tests/source_utils.py::current_source()` relit le fichier et **retrouve la définition par nom** via
  `ast` (`get_source_segment`), donc un décalage de lignes ne peut pas renvoyer la mauvaise fonction ;
- les trois tests qui inspectaient du texte (`default_bind_is_loopback`, le filtre d'env du bac à sable,
  `test_llm_never_executes_commands`) passent par ce lecteur ; le test de bind vérifie en plus le
  **contrat réel** (`inspect.signature(...).parameters["host"].default == "127.0.0.1"`) ;
- `tests/test_source_utils.py` pin le mécanisme : il réécrit réellement le fichier dans un sous-processus,
  vérifie que `current_source` reste correct **et** que `inspect.getsource` renvoie bien la mauvaise
  fonction (si CPython change un jour, ce test le dira), puis restaure le fichier et compare son sha256.

Statut : `FIXED_AND_VERIFIED`. Le test n'est plus sensible à une réécriture pendant l'exécution.

La **seconde** instabilité du même fichier (`test_state_changing_with_wrong_token_is_403`, citée au §6
initial) a une autre cause, également mesurée : voir §4decies — un reset TCP provoqué par une réponse
403 envoyée avant la lecture du corps de la requête. Les deux causes sont donc identifiées et fermées,
aucune assertion n'a été assouplie.
