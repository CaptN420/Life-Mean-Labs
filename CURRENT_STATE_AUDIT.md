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
| Tests de référence | **1 773 passed, 13 skipped, 0 failed** (après P1→P9) |

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
| 17 | GPU / inférence locale | `BLOCKED_EXTERNAL` | `torch`, `llama_cpp`, `transformers`, `onnxruntime` absents |
| 18 | Collecteurs Windows (Defender, Event Log) | `BLOCKED_EXTERNAL` | `psutil`, `win32evtlog`, `win32service` absents |
| 19 | Feature Pool à 987/989 non observées | `PARTIAL` | usage observé ≠ validation, statuts inchangés |
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
