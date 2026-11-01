# PIPELINE_VALIDATION_REPORT

**Projet** : `Life_mean_realm`
**Phase** : 0 — Validation du Pipeline Inspector existant (aucune recréation)
**Date** : 2026-11-01
**Méthode** : inspection des fichiers réels, exécution réelle, lecture seule sur les journaux d'origine.

**Verdict global : PARTIAL — fonctionnel, avec 3 défauts confirmés corrigés et 4 limites documentées.**

Aucun fichier de log n'a été modifié. Aucune commande trouvée dans les logs n'a été exécutée. Aucun service Windows n'a été touché. Aucune suppression hors de la cache d'événements dérivée (reconstruite depuis les journaux).

---

## A. Imports et compilation Python — OK

15 modules `pipeline_inspector/*.py` compilés un par un avec l'interpréteur du projet :

```
py_compile 15 files, failures: []   (rc=0)
```

`experiments/dashboard.py` compile également (`py_compile` rc=0), ainsi que les 3 blocs `<script>` du dashboard (`node --check` 3/3 OK).

---

## B. Doublons / blocs morts après les patchs — OK

- Analyse AST de chaque module : **aucun** nom de fonction ou de classe défini deux fois (`DUPLICATE DEFS: none`).
- 55 déclarations de routes dans `dashboard.py` : les apparents « doublons » (`/api/experiments`, `/api/settings`, `/api/agents`, `/api/code-lab/runs`) sont **une route par verbe HTTP** (`do_GET` + `do_POST` + éventuellement `do_PUT`), pas des registrations en double. Vérifié méthode par méthode.
- Deux `SyntaxError` JavaScript **corrigés** dans `dashboard.html` (constante `el` redéclarée ; chaîne littérale coupée par un retour à la ligne). Un seul `SyntaxError` neutralisait tout le script → onglets inertes. Preuve : `node --check` 3/3 OK.

---

## C. Ingestion incrémentale — OK après deux corrections

| Contrôle | Résultat |
|---|---|
| Fichiers découverts | 1 167 |
| Fichiers analysés | 1 167 |
| Lignes malformées | 0 |
| Événements émis | 786 377 (passe 1, run 5) puis **837 054** après reprise du fichier plafonné (run 6) |
| Deuxième passe à vide | `events_added = 0` — aucun doublon (run 2) |
| Reprise après plafond | **bug corrigé** (voir § M1) |
| Offsets de reprise | **bug corrigé** (voir § M2) |

Deux bugs réels ont été trouvés en exerçant l'ingestion, pas en la relisant :

- **M1 — perte silencieuse après plafond.** `max_records_per_file = 200 000`. Le fichier `data/raw_debates/exp_1.jsonl` (85 557 445 octets) atteignait le plafond ; l'état d'ingestion enregistrait `size == st_size` **sans** drapeau, donc la passe suivante le comptait comme entièrement consommé. **Le reste du fichier n'était jamais lu, sans erreur.** Correctif : colonne `truncated` (migration `ALTER TABLE` automatique), reprise à l'offset enregistré, message d'erreur explicite. Réparation de l'état historique : `UPDATE ingest_state SET truncated=1 WHERE events>=200000` (1 ligne).

  **Démonstration en production** : après le correctif, la passe run 5 s'arrête à l'offset 68 012 323 avec `truncated=1`, puis la passe run 6 relit **ce fichier uniquement** (`files_parsed=1`, `files_skipped=1166`) et ajoute **50 677 événements** en 9,9 s, `errors: []`. État final : `offset == size == 85 557 445`, `truncated=0`. Le fichier est donc intégralement ingéré — mais il faut **deux passes** à cause du plafond (voir § O #9).
- **M2 — offsets relatifs après reprise.** `JsonlAdapter._read_lines()` faisait `seek(start_offset)` puis `pos = 0` : les offsets renvoyés étaient **relatifs au point de reprise** alors qu'ils étaient stockés comme absolus. L'offset enregistré est tombé à 17 545 122 **au milieu d'une ligne** ; la passe suivante a lu 50 677 événements puis s'est arrêtée, sans erreur. Correctif : lecture depuis le début, saut des lignes déjà consommées, offsets et numéros de ligne exacts (coût linéaire ≈1 s pour 85 Mo).

Tests de non-régression ajoutés : `test_ingestor_resumes_after_per_file_cap`, `test_store_ingest_state_truncated_roundtrip`, `test_resume_offsets_are_absolute`.

---

## D. Déduplication SQLite — OK

- `SELECT count(*) - count(distinct event_id) FROM events` → **0**.
- `INSERT OR IGNORE` sur `event_id` (hash stable type + fichier + ligne + horodatage).
- Test unitaire existant : `test_store_dedupes_and_filters`.
- Deux passes consécutives sur les mêmes fichiers n'ajoutent **rien** (`run 2 : events_added = 0`).

---

## E. Masquage des secrets — **défaut trouvé et corrigé**

Sonde réelle :

```
api_key=sk-ABC123SECRET456   → api_key=sk-***REDACTED***
token=ghp_abcdefghijklmnop   → token=***REDACTED***
C:\Users\celes\secret.txt    → ~/secret.txt
password=hunter2             → password=hunter2      ❌ NON MASQUÉ
```

Cause : l'expression exigeait **8 caractères minimum** pour une valeur non quotée ; `hunter2` (7) passait en clair. Ajout de `access_key`, des clés AWS (`AKIA…`) et des blocs PEM, et suppression du seuil de longueur.

Test de non-régression ajouté : `test_redaction_masks_short_passwords_and_keys`.

Le masquage s'applique aux copies (payload stocké, API, exports) ; **les fichiers d'origine ne sont jamais réécrits**.

---

## F. Corrélations — explicite / probable / inconnue — **défaut trouvé et corrigé**

`correlation.py` distingue correctement les trois niveaux (`_is_pair` : `model_call_id`/`task_id` → explicite ; `session_id` ou fenêtre temporelle → probable ; sinon aucun lien). Les tests `test_correlation_explicit_and_unknown` et `test_correlation_ambiguous_keeps_unknown` passent.

**Mais le champ stocké sur chaque événement était surévalué** : les adapters écrivaient `correlation="explicit"` dès qu'un `run_id` existait. Résultat mesuré sur la base : **785 941 événements « explicites » / 436 inconnus, zéro probable** — 100 % de certitude sur une simple appartenance à un run.

Correctif appliqué à deux niveaux : les adapters (champ stocké) et `_is_pair` (calcul des liens). Seuls `model_call_id` et `correlation_id` restent **explicites** ; `task_id`, `run_id`, `session_id` et `generation_id` deviennent **probables** (0,6–0,85) ; un événement isolé reste **unknown** (0,0).

Effet mesuré après ré-ingestion complète :

| Corrélation stockée | Événements |
|---|---:|
| `explicit` (correlation_id d'audit) | **393** |
| `probable` (run/session/task/gen) | **777 284** |
| `unknown` | **8 700** |

Au niveau des *liens* calculés (échantillon de 20 000 événements) : 0 explicite, 11 516 probables, 8 483 sans lien — l'explicite n'apparaît que lorsque `model_call_id` est réellement présent (286 événements en base), ce qui est cohérent.

---

## G. Aucune corrélation présentée comme certaine sans preuve — corrigé

Voir § F. En complément :
- Le graphe est construit **uniquement** à partir des transitions observées, jamais depuis le schéma théorique. Le schéma théorique sert de légende, et les écarts sont exposés : `observed_not_in_hypothesis = ['FILE_PATCH', 'PIPELINE_ERROR']`.
- `correlation_summary` calcule les liens à la demande ; le store n'est jamais annoté de façon permanente.
- Un événement sans identifiant n'obtient **aucun** lien (`link_to_previous = null`).

---

## H. Analyse des décisions de sécurité — OK, avec divulgation d'échantillon ajoutée

- 393 décisions (`SECURITY_REVIEW/APPROVE/DENY/ESCALATE`), **12 incohérences** détectées de type « DENY suivi d'une exécution ».
- 10 000 événements d'exécution examinés (`TOOL_CALL`, `FILE_PATCH`, `TOOL_RESULT`).
- Le module ne conclut pas sur une simple corrélation temporelle : il regroupe par clé observée et exige une décision DENY **précédant** une exécution dans le même groupe.
- **Défaut de transparence corrigé** : ces analyses portent sur les N derniers événements (10 000 / 20 000), pas sur la base entière. Le payload expose désormais `sample: {events_scanned, limit, truncated, note}` pour `graph`, `security`, `errors`, `performance`, `features`.

---

## I. Routes HTTP — OK (test réel, pas lecture de code)

Serveur lancé localement (`experiments.dashboard --port 8091`), requêtes réelles :

| Route | Code | Taille | Temps |
|---|---:|---:|---:|
| `/api/pipeline/stats` | 200 | 1 208 B | 0,4 s |
| `/api/pipeline/sessions?limit=5` | 200 | 1 274 B | 0,7 s |
| `/api/pipeline/events?limit=3` | 200 | 2 739 B | 0,6 s |
| `/api/pipeline/graph` | 200 | 16 578 B | 0,3 s |
| `/api/pipeline/security` | 200 | 116 555 B | 0,9 s |
| `/api/pipeline/performance` | 200 | 2 557 B | 0,5 s |
| `/api/pipeline/errors` | 200 | 9 561 B | 0,3 s |
| `/api/pipeline/features` | 200 | 3 946 B | 2,8 s |
| `POST /api/pipeline/reports` | 200 | 7 fichiers écrits | 5,4 s |
| `POST /api/pipeline/export` | 200 | `data/pipeline_reports/<UTC>/pipeline_export.json` | 4,9 s |

Le POST exige l'en-tête `X-Lifemean-CSRF` (double-submit). Une première tentative avec `X-CSRF-Token` a été rejetée en **403** — comportement attendu, pas un bug. Le front injecte le bon en-tête via un wrapper `fetch` global (vérifié dans le HTML).

---

## J. Affichage réel dans Life_mean Studio — **UNAVAILABLE (non intégré)**

`grep -rl "pipeline_inspector" life_mean_studio/` → **aucun fichier**. Les onglets Studio sont : Agent Builder, Workflow Builder, Model Settings, Tool Registry, Diagnostics. **Le Pipeline Inspector n'est pas branché dans Studio** ; il est exposé par le dashboard HTTP (`experiments/dashboard.py` + onglet `pipeline` de `dashboard.html`).

Conséquence honnête : le critère « affichage réel dans Life_mean Studio » n'est **pas** atteint. Le visualiseur existe, mais dans l'UI web, pas dans l'application PySide6. Le rapport d'implémentation ne doit pas prétendre le contraire.

---

## K. Tests — 36 passed (27 + 9)

```
pipeline_inspector/tests  →  27 passed  (0,65 s)
feature_pool/tests        →   9 passed  (4 min 07 — scan complet du dépôt)
```

Dont 4 tests de non-régression ajoutés pendant cette validation (drapeau `truncated`, reprise après plafond, offsets absolus, masquage court/AWS). La suite `feature_pool` a été relancée **après** le changement de règle `READY`/`VALIDATED` : 9 passed sur le code courant.

**Limite honnête** : aucun test de `feature_pool/tests` n'asserte le nouveau comportement (`grep VALIDATED|READY|validate_all` → 0 occurrence). Ce changement n'est donc couvert que par non-régression, pas par un test dédié — à ajouter.

Validation JS : `node --check` 3/3. Compilation Python : 15/15.

---

## L. État réel du Feature Pool — règle « pas READY par simple découverte » appliquée

Le Feature Pool a été régénéré par le pipeline officiel (`discover → analyze_all → validate_all → export_report`), sans modification manuelle de statut.

| Statut | Nombre | Signification |
|---|---:|---|
| VALIDATED | **138** | code qui parse **et** au moins un test associé |
| READY | **49** | code qui parse, dépendances résolues, **aucun test** → non promu |
| BROKEN | **0** | aucun fichier ne provoque d'erreur de syntaxe (`ast.parse`) |
| BLOCKED | **0** | aucune dépendance déclarée introuvable |

Deux corrections structurelles ont rendu ce résultat crédible :

1. **Le test de syntaxe était faux.** `_has_syntax_issues()` comparait `content.count('(')` et `content.count(')')`. Parenthèses dans les docstrings, f-strings, regex, smileys → 48 faux verdicts sur 153 features. Vérification indépendante par `ast.parse` sur les 8 fichiers accusés : **8/8 parsent**. Remplacé par `ast.parse` avec cache.
2. **La promotion en VALIDATED ne prouvait rien.** `validate_all()` promouvait en `VALIDATED` dès que le code parsait. Désormais : `READY` = code sain sans test ; `VALIDATED` exige un test. Un `no_tests` devient un *coverage gap* consigné (`feature.coverage_gaps`), jamais un statut BROKEN.

---

## M. Autres défauts confirmés et corrigés pendant cette phase

### M3 — Rapport périmé masquant le rapport frais
`export_report()` écrivait `feature_pool_report.json` ; le pont lisait `.feature_pool_report.json` (avec point). L'ancien fichier (153 features, 105 VALIDATED / 42 BLOCKED / 6 BROKEN) gagnait toujours. Correctif : le pont retient le fichier **le plus récent** (mtime) et expose `generated_at` ; l'export écrit le même payload aux deux emplacements. Aucune suppression.

### M4 — Rapports écrits dans un chemin non inscriptible en Docker
Chemin par défaut `reports/pipeline/` alors que le conteneur monte `/app` en lecture seule. Corrigé en `data/pipeline_reports/`, surchargeable par `PIPELINE_REPORTS_DIR`.

### M5 — `bytes_read` toujours à 0
Compteur déclaré, jamais incrémenté. Corrigé (`stats.bytes_read += st.st_size`) ; la passe de reprise a réellement mesuré 85 557 445 octets.

---

## N. Chiffres de la passe finale (ré-ingestion complète, 1 167 fichiers)

| Métrique | Valeur |
|---|---:|
| Événements en base | **837 054** |
| Fichiers indexés | 1 167 |
| Lignes malformées | 0 |
| Sessions (stats globales) | 11 180 |
| `TOOL_CALL` | 272 740 |
| `AGENT_SELECTED` | 181 361 |
| `TEST_RESULT` | 91 007 |
| `PIPELINE_START` | 90 906 |
| `ROUTING_DECISION` | 90 537 |
| `PIPELINE_ERROR` | 40 851 |
| Corrélations | 393 explicite / 827 961 probable / 8 700 inconnue |
| Décisions de sécurité | 393, dont **12 incohérences** (échantillon 10 393 événements) |
| Erreurs classées | **7 825** sur 8 codes |
| Modèles suivis | 9 |
| Features reliées au pipeline | **6 / 187** |
| Graphe observé | 9 nœuds, 50 arêtes — `FILE_PATCH` et `PIPELINE_ERROR` absents du schéma théorique |

Sources : `captn_experiences` 8 264, `code_lab_events` 1 832, `code_lab_trajectory` 391, `hermes_audit` 393, `raw_debates` 765 314, `text_log` 10 183.

Répartition des erreurs : `AUTH_INVALID` 60, `API_SCHEMA_ERROR` 1 381, `CODE_BUG` 108, `UNCLASSIFIED` 190, `DEGRADED_FALLBACK` 19, `AGENT_PARSE_FAILURE` 1 055, `TIMEOUT` 12, `VALIDATION_FAILED` 5 000.

### N-bis — Limites de lecture à retenir

- Les compteurs d'analyse (`security`, `errors`, `performance`, `features`, `graph`) portent sur les **N derniers événements**, pas sur la base entière. Le champ `sample` le dit désormais explicitement.
- `sessions` (stats globales) et le nombre de sessions vu par `performance` ne coïncident pas (11 180 vs 8 484) : deux définitions différentes de la clé de session. Incohérence à documenter, pas à masquer.
- La durée maximale de session observée (≈519 509 s) vient de cohortes d'expérience, pas de conversations.

---

## O. Ce qui reste ouvert

| # | Point | Impact |
|---|---|---|
| 1 | Pipeline Inspector absent de Life_mean Studio (PySide6) | critère « Hub dans Studio » non atteint |
| 2 | Analyses sur échantillon (N derniers) sans pagination globale | compteurs non exhaustifs |
| 3 | 8 190 conflits `legacy_modern_mismatch` (≈1,7 Mo de JSON) alors que `by_source` annonce `legacy: 0` | bruit + taille de rapport |
| 4 | Base SQLite volumineuse (~0,5 Go), aucune politique de rétention | croissance non bornée |
| 5 | Mapping features ↔ logs faible (6/187) | usage observé peu informatif |
| 6 | Image Docker reconstruite et conteneur `healthy` (vérifié après correctifs) | reste à monter les journaux d'origine dans le conteneur (voir #8) |
| 7 | Rendu visuel des 12 onglets non vérifié dans un navigateur | validité syntaxique prouvée, rendu non observé |
| 8 | Le plafond `max_records_per_file = 200 000` impose **deux passes** pour `exp_1.jsonl` (85,5 Mo, ~250 k événements) | ingestion complète non garantie en une seule exécution |
| 9 | **Dans Docker, `/app/data` est un volume vide** : l'inspector n'y voit que les volumes montés (3 fichiers, 18 447 événements) et **pas** `data/raw_debates` (765 314 événements en local) | le déploiement conteneur ne reflète pas la richesse des logs locaux |

---

## P. Reproduction

```bash
# compilation
.venv/Scripts/python.exe -m py_compile pipeline_inspector/*.py experiments/dashboard.py

# tests
.venv/Scripts/python.exe -m pytest pipeline_inspector/tests -q

# validité JS des onglets
.venv/Scripts/python.exe _audit_js_blocks.py

# ingestion incrémentale (2e passe doit ajouter 0)
.venv/Scripts/python.exe -m pipeline_inspector ingest
.venv/Scripts/python.exe -m pipeline_inspector ingest

# API réelle
.venv/Scripts/python.exe -m experiments.dashboard --port 8091 &
curl -s http://127.0.0.1:8091/api/pipeline/stats
curl -s http://127.0.0.1:8091/api/pipeline/security
```

---

## Q. Conclusion

Le Pipeline Inspector existant est **réel, testé et fonctionnel** : 36 tests passent (27 pipeline_inspector + 9 feature_pool), 10 routes HTTP répondent, 1 167 fichiers sont ingérés sans une seule ligne malformée, et la déduplication est vérifiée sur une base de 837 054 événements.

Trois défauts de fond le rendaient cependant **trompeur**, et ils sont corrigés avec preuve : le masquage laissait passer les mots de passe courts, la corrélation s'annonçait « explicite » sur 100 % des événements, et l'ingestion perdait silencieusement la fin des gros fichiers. Les compteurs d'analyse sont désormais étiquetés comme échantillons.

Reste **PARTIAL** pour deux raisons vérifiées : aucune intégration dans Life_mean Studio, et des analyses bornées par échantillon. Le Pipeline Inspector ne doit donc pas encore être présenté comme le système d'observabilité central unique — il est **utilisable et fiable dans ses limites documentées**, pas exhaustif.
