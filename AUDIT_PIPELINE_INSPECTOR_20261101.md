# AUDIT — Pipeline Inspector & Feature Pool

**Projet** : `Life_mean_realm`
**Date** : 2026-11-01
**Portée** : audit statique + exécution réelle (tests, ingestion, régénération du pool)
**Règle appliquée** : observer avant d'intervenir · préserver avant de modifier · vérifier avant de valider.
Aucun log original supprimé. Aucun statut Feature Pool modifié à la main. Aucune commande extraite des logs n'a été exécutée.

---

## 1. Résumé exécutif

Trois défauts réels expliquaient les symptômes signalés, et chacun a été reproduit puis corrigé avec preuve d'exécution :

| Symptôme signalé | Cause réelle (prouvée) | État |
|---|---|---|
| « je ne peux pas changer d'onglet dans le HTML » | **Deux `SyntaxError` JS** : `const el` déclaré une seconde fois (bloc principal) et une chaîne littérale coupée par un retour à la ligne (bloc workspace). Un seul `SyntaxError` suffit à empêcher l'exécution **de tout le script** → `switchTab` inexistant, onglets inertes. | **Corrigé** |
| « le Feature Pool annonce des trucs broken et blocked » | `_has_syntax_issues()` comparait `content.count('(')` et `content.count(')')`. Ce n'est pas un test de syntaxe (parenthèses dans les docstrings, f-strings, regex, smileys). 48 verdicts faux sur 153 features. | **Corrigé** |
| Pipeline Inspector ignorait mes features | Le pont lisait `.feature_pool_report.json` alors que l'export écrivait `feature_pool_report.json` → un rapport **périmé** masquait le neuf. | **Corrigé** |

Bonus trouvé en vérifiant : l'ingestion **perdait silencieusement le reste d'un fichier** de 85 Mo une fois le plafond de 200 000 enregistrements atteint (fichier marqué « consommé »), et `bytes_read` valait toujours `0`. Corrigé + test de régression.

---

## 2. PHASE 1 — Inventaire de l'existant

### 2.1 Ce qui existe réellement (vérifié sur fichiers)

| Domaine | Composant existant | Chemin | État |
|---|---|---|---|
| Schémas d'événements | `PipelineEvent`, `EventType` (17 types), `ParseStats` | `pipeline_inspector/schemas.py` | Présent |
| Parsing de logs | `LogAdapter`, `JsonlAdapter`, `CodeLabEventsAdapter`, `RawDebatesAdapter`, `HermesAuditAdapter`, `TextLogAdapter`, `default_adapters()` | `pipeline_inspector/log_parser.py` | Présent, 1167 fichiers découverts |
| Persistance | `EventStore` (SQLite, WAL, `busy_timeout`), dédoublonnage `INSERT OR IGNORE`, état d'ingestion incrémental | `pipeline_inspector/event_store.py` | Présent |
| Ingestion incrémentale | `PipelineIngestor.run(full_rescan, adapter_names, dry_run)` | `pipeline_inspector/ingest.py` | Présent |
| Corrélation | `build_links`, `annotate`, `correlation_summary` (explicite / probable / inconnue) | `pipeline_inspector/correlation.py` | Présent |
| Graphe | `build_graph` — construit **uniquement** des transitions observées | `pipeline_inspector/pipeline_graph.py` | Présent |
| Performance | `model_metrics`, `pipeline_metrics` | `pipeline_inspector/performance.py` | Présent |
| Sécurité | `analyze` — décisions + incohérences décision/action | `pipeline_inspector/security_inspector.py` | Présent |
| Erreurs | `analyze` — classification (`AUTH_INVALID`, `API_SCHEMA_ERROR`, `CODE_BUG`, `DEGRADED_FALLBACK`, `UNCLASSIFIED`) | `pipeline_inspector/error_analyzer.py` | Présent |
| Pont Feature Pool | `FeaturePoolBridge` — lecture seule, comptage d'usage, **aucune écriture de statut** | `pipeline_inspector/feature_pool_bridge.py` | Présent |
| Rapports | `ReportGenerator` — 7 documents Markdown, horodatés, jamais écrasés | `pipeline_inspector/report_generator.py` | Présent |
| API HTTP | `PipelineApiMixin` — 11 routes `/api/pipeline/*` | `pipeline_inspector/studio_interface.py` | Présent |
| Dashboard | Dashboard HTTP maison (`BaseHTTPRequestHandler`) + UI 12 onglets | `experiments/dashboard.py`, `experiments/ui/dashboard.html` | Présent |
| Feature Pool | Scanner / Registry / Analyzer / DependencyGraph / Compatibility / Planner / History | `feature_pool/*.py` | Présent |
| Studio desktop | PySide6 (`life_mean_studio/`), Agent Builder | `life_mean_studio/` | Présent (non réaudité ici) |

### 2.2 Ce qui n'existe **pas** (à ne pas supposer)

- Pas de bus d'événements central, pas de tracing distribué, pas de telemetry OpenTelemetry : l'observabilité actuelle est **log-based + SQLite local**.
- L'ancien dossier `Life_mean/` (661 tests) est un projet distinct ; `Life_mean_realm` est l'évolution v3 avec Feature Pool. Les deux ne partagent pas leur couverture de tests.
- Le dashboard n'est pas une app FastAPI : c'est un `BaseHTTPRequestHandler` avec un mixin par domaine (expérimental, comparaison, extensions, pipeline).

### 2.3 Points d'intégration retenus

1. **Dashboard → Pipeline Inspector** : mixin + 11 routes, sans toucher au reste du handler.
2. **Pipeline Inspector → Feature Pool** : lecture seule du rapport JSON ; l'usage observé est présenté **à côté** du statut, jamais à la place.
3. **Rapports → disque** : écriture sous `data/pipeline_reports/<run>/`, jamais dans le code (le conteneur monte `/app` en lecture seule).

---

## 3. PHASE 2 — Parseur de logs (mesuré)

Ingestion réelle sur le dépôt (passe du 2026-11-01 01:11, avant correction des offsets — une réingestion propre est relancée après correctif) :

```
files_seen          : 1167
files_parsed        : 1167
records_read        : 786 377
events_emitted      : 786 377
malformed_lines     : 0
events_added        : 786 377
duration_s          : 117.1
```

Répartition observée (passe précédente, 650 881 événements) :

| Type | Occurrences |
|---|---:|
| `TOOL_CALL` | 269 905 |
| `TEST_RESULT` | 90 441 |
| `PIPELINE_START` | 90 340 |
| `ROUTING_DECISION` | 89 971 |
| `PIPELINE_COMPLETE` | 53 147 |
| `PIPELINE_ERROR` | 40 284 |
| `MODEL_RESPONSE` | 11 068 |
| `API_ERROR` | 2 825 |
| `MODEL_REQUEST` | 1 730 |
| `FILE_PATCH` | 460 |

Chaque événement conserve : `event_id` stable (hash), horodatage + `timestamp_iso`, source, agent/modèle, type, `session_id` / `conversation_id` / `request_id` / `task_id` quand ils existent, durée quand mesurable, statut, métadonnées, `source_file` + `source_line` (référence au journal d'origine).

**Aucune corrélation inventée** : quand l'identifiant manque, le lien est marqué `probable` ou `unknown` (test `test_correlation_ambiguous_keeps_unknown`).

---

## 4. PHASE 3 — Graphe du pipeline

Construit depuis les transitions observées : **9 nœuds, 35 arêtes**. Le schéma théorique (USER → HERMES → ROUTING → LLM → TOOL → SECURITY → RESULT → VALIDATION → RESPONSE) n'est **pas** imposé au graphe ; il sert seulement de légende. C'est conforme à la consigne « le graphe réel doit être construit à partir des événements observés ».

---

## 5. PHASE 4 — Dashboard (onglets)

### 5.1 Cause racine des onglets inertes

Deux `SyntaxError` distincts dans `experiments/ui/dashboard.html` :

1. **Bloc principal** : `const el = id => document.getElementById(id);` déclaré **une seconde fois** (`const` déjà déclaré en haut du même script) → le navigateur rejette **l'intégralité** du bloc avant exécution. Conséquence : `switchTab()` n'existe même pas, donc **tous** les onglets et boutons du bloc sont morts.
2. **Bloc workspace** (indépendant) : `... + msg + '` suivi d'un vrai retour à la ligne puis `';` → chaîne non terminée. Conséquence : les fonctions du workspace (`wsLog`, `wsSwitchView`) n'existaient pas.

Preuve de correction : `node --check` sur **chacun** des 3 blocs `<script>` → 3/3 OK (avant : 2 KO). Un `const` dupliqué **ne peut pas** passer `node --check` : sa réussite prouve la disparition du doublon.

### 5.2 Structure actuelle du dashboard

12 onglets / 12 panneaux, appariés :

`workspace`, `code-lab`, `debate`, `experiments`, `compare`, `experimental`, `clustertree`, `autopilot`, `skills`, `pipeline`, `agent-builder`, `settings`.

Le panneau `panel-pipeline` a été ajouté avec : ingestion (normale / complète), génération de rapports, export JSON, 4 compteurs, filtres (type / source / session / recherche), chronologie, sessions, graphe, décisions de sécurité, erreurs, performances, table Feature Pool ↔ Pipeline.

**Non vérifié** : rendu visuel réel dans un navigateur (pas de test visuel automatisé). Le HTML est syntaxiquement valide, l'API répond, mais je ne prétends pas avoir vu les 12 onglets s'afficher.

---

## 6. PHASE 5 — Feature Pool : les « broken / blocked » étaient faux

### 6.1 Preuve du faux positif

`feature_pool/analyzer.py` décidait BROKEN/BLOCKED ainsi :

```python
if content.count('(') != content.count(')'):
    return True   # "syntax issue"
```

Vérification indépendante par `ast.parse()` sur les 8 fichiers accusés :

```
AST OK    core/debate/engine.py                                  | parens 473 / 475
AST OK    philosophical_council/core/debate_engine.py            | parens 440 / 438
AST OK    code_lab/multiagent.py                                 | parens 200 / 202
AST OK    legacy/.../captn/runtime/workers.py                    | parens  46 /  44
AST OK    legacy/.../transformation/diversifier_worker.py        | parens 214 / 213
AST OK    legacy/.../code_generation/code_backend_worker.py      | parens 146 / 142
AST OK    legacy/.../quality/domain_classifier_worker.py         | parens 113 / 109
AST OK    legacy/.../transformation/chemistry_validation_worker.py | parens 121 / 122
```

8/8 parsent correctement. Les écarts de parenthèses viennent des chaînes, docstrings et regex — pas de la syntaxe.

### 6.2 Correction

- `_has_syntax_issues()` → `ast.parse()`, avec cache par fichier.
- `assess_readiness()` : **BROKEN** seulement si le fichier ne parse pas ; **BLOCKED** seulement si une dépendance déclarée est introuvable dans le registre ; `no_tests` devient un **coverage gap** (`feature.coverage_gaps`), plus un statut. Un manque de test n'est pas un défaut du code.

### 6.3 Effet mesuré

| Métrique | Avant | Après |
|---|---:|---:|
| Features découvertes | 153 | **187** |
| VALIDATED | 105 | **187** |
| BLOCKED | 42 | **0** |
| BROKEN | 6 | **0** |
| Coverage gaps `no_tests` | — | 49 |

---

## 7. PHASE 6 — Sécurité (ce que les logs prouvent, et ce qu'ils ne prouvent pas)

- **393 décisions** de sécurité observées, **12 incohérences** détectées (décision vs action réellement exécutée).
- Le rapport rappelle explicitement qu'un `APPROVE` **n'est pas** une preuve de sûreté : `security_inspector` compare la décision, la permission effective et l'exécution.
- Aucune commande présente dans les logs n'a été exécutée par l'inspector.

---

## 8. PHASE 7 — Performance

Mesures disponibles (9 modèles suivis) : tokens entrée/sortie, latence moyenne, tokens/s, taux d'échec, durée de session. Les mesures absentes **restent absentes** (`null`), elles ne sont pas estimées. Les métriques modèle et les métriques pipeline sont présentées séparément.

---

## 9. PHASE 8 — Erreurs classifiées

```
total        : 7 825
AUTH_INVALID, API_SCHEMA_ERROR, CODE_BUG, UNCLASSIFIED, DEGRADED_FALLBACK
```

Chaque erreur porte un code, une source, un horodatage et un extrait de message ; le rapport produit des recommandations **sans appliquer** de correctif.

> ⚠️ Ces 7 825 « erreurs » incluent 40 284 `PIPELINE_ERROR` bruts agrégés par code. Le chiffre du rapport public est celui des événements classés, pas des incidents distincts — à ne pas citer comme « 7 825 pannes ».

---

## 10. PHASE 9/10 — Architecture, persistance, confidentialité

- Base SQLite : `data/pipeline_inspector.db` (**~481 Mo** après ingestion complète de 786 k événements). Volume notable : prévoir purge/archivage.
- Rapports : `data/pipeline_reports/<UTC>/` — **écriture hors du code** (le conteneur monte `/app` en `read_only`). C'est un bug corrigé : l'ancien chemin `reports/pipeline/` aurait échoué en Docker.
- Masquage : `redaction.py` masque secrets et chemins dans l'UI et les exports ; les journaux d'origine ne sont jamais modifiés.
- Aucune transmission réseau.

---

## 11. PHASE 11 — Tests

| Suite | Résultat |
|---|---|
| `pipeline_inspector/tests` | **25 passed** (dont 2 nouveaux tests de régression sur le plafond d'ingestion et le drapeau `truncated`) |
| `feature_pool/tests` | exécuté après les modifications (voir sortie de session ; 8 tests, ~4 min à cause du scan complet du dépôt) |
| Validation JS | `node --check` sur les 3 blocs `<script>` → **3/3 OK** |
| Validation Python | `py_compile` sur `pipeline_inspector/*.py` + `experiments/dashboard.py` → OK |

---

## 12. Bugs trouvés en vérifiant (et corrigés)

### 12.1 Ingestion : perte silencieuse après plafond
`max_records_per_file = 200 000`. Le fichier `data/raw_debates/exp_1.jsonl` (85,5 Mo) atteignait le plafond. L'état d'ingestion enregistrait `size == st_size` **sans** drapeau, donc la passe suivante le comptait comme « déjà ingéré » : **le reste du fichier n'était jamais lu**.

Correctif : colonne `truncated` (migration `ALTER TABLE` automatique), reprise à l'`offset` enregistré, message d'erreur explicite, `bytes_read` réellement incrémenté. Deux tests de régression ajoutés.

État historique réparé à la main : `UPDATE ingest_state SET truncated=1 WHERE events >= 200000` (1 ligne : `exp_1.jsonl`).

### 12.2 Rapport périmé masquant le rapport frais
`FeaturePool.export_report()` écrivait `feature_pool_report.json` ; le pont lisait `.feature_pool_report.json` (avec point). Le fichier périmé (153 features, 105/42/6) gagnait toujours.

Correctif : le pont choisit désormais le fichier **le plus récent** (mtime), expose `generated_at`, et `export_report()` écrit le **même** payload aux deux emplacements (aucune suppression).

Effet : le pont charge `187 features, source=.feature_pool_report.json, generated_at=2026-11-01T01:11:28+00:00`, statuts `{VALIDATED: 187}`.

---

### 12.3 Ingestion : offsets relatifs après reprise (fin de fichier perdue)

`JsonlAdapter._read_lines()` faisait `fh.seek(start_offset)` **puis** `pos = 0` et comptait les octets depuis ce point. Les `next_offset` renvoyés étaient donc **relatifs au point de reprise**, alors que l'ingestion les enregistrait comme **absolus**.

Conséquence observée sur `data/raw_debates/exp_1.jsonl` (85,5 Mo) : après une reprise, l'offset enregistré tombait à 17 545 122 **au milieu d'une ligne**, et la passe suivante repartait de ce mauvais endroit (50 677 événements lus puis arrêt, sans aucune erreur signalée).

Correctif : lecture depuis le début du fichier, saut des lignes entièrement consommées (`pos <= start_offset`), offsets et numéros de ligne **exacts**. Coût linéaire assumé (≈1 s pour 85 Mo).

Preuve : `test_resume_offsets_are_absolute` vérifie que la reprise renvoie des offsets absolus, monotones, égaux à la taille du fichier en fin de parcours, et ne relit aucune ligne déjà consommée. Suite : **26 passed**.

### 12.4 Réparation des données dérivées

Les offsets stockés par la version buguée étaient inexploitables (ils rétrécissaient à chaque passe). `events`, `ingest_state` et `ingest_runs` sont une **cache dérivée** reconstruible intégralement depuis les journaux d'origine (jamais modifiés). Elle a donc été vidée puis régénérée par une ingestion complète.

---

## 13. Dettes ouvertes (non corrigées)

| # | Problème | Preuve | Impact |
|---|---|---|---|
| 1 | `conflicts.by_severity.low` contient **8 190** entrées `legacy_modern_mismatch` (~1,7 Mo sur 2,7 Mo du JSON) alors que `by_source` annonce `legacy: 0` | `len(conflicts.high/medium/low) = 0/0/8190` | Bruit massif dans le rapport, taille de fichier |
| 2 | `sessions = 11 180` gonflé par les identifiants par-enregistrement (CaptN) | comptage `stats.sessions` | Métrique « sessions » peu interprétable |
| 3 | Features reliées au pipeline : **6 / 187** | `FEATURE_POOL_PIPELINE_MAP.md` | Le mapping repose sur le nom d'agent/outil ; beaucoup de features ne sont jamais nommées dans les logs |
| 4 | Base 481 Mo / 786 k événements, sans politique de purge | `ls -la data/pipeline_inspector.db` | Croissance non bornée |
| 5 | Image Docker non reconstruite après ces correctifs | `docker-compose.yml` : aucun bind mount | Le conteneur sert encore l'ancien code |
| 6 | Rendu visuel des 12 onglets non vérifié dans un navigateur | — | À confirmer par toi (ou par un test navigateur) |

---

## 14. PHASE 12 — Tableau de synthèse

| Composant | Découvert | Implémenté | Testé | Intégré | Action suivante |
|---|---|---|---|---|---|
| Schémas d'événements (17 types) | Oui | Oui | Oui | Oui | — |
| Parseur de logs (6 adapters) | Oui | Oui | Oui | Oui | Ajouter un adapter Hermes natif si les logs changent de format |
| EventStore SQLite (WAL, dédoublonnage) | Oui | Oui | Oui | Oui | Politique de purge / archivage |
| Ingestion incrémentale | Oui | Oui (corrigée) | **Oui (2 tests ajoutés)** | Oui | Baisser le plafond ou le rendre configurable |
| Corrélation explicite/probable/inconnue | Oui | Oui | Oui | Oui | — |
| Graphe observé | Oui | Oui | Oui | Oui | — |
| Performance | Oui | Oui | Oui | Oui | — |
| Security Inspector | Oui | Oui | Oui | Oui | Exploiter les 12 incohérences |
| Error Analyzer | Oui | Oui | Oui | Oui | Séparer « événements en erreur » de « incidents » |
| Pont Feature Pool | Oui | Oui (fraîcheur corrigée) | Oui | Oui | Améliorer le mapping (6/187) |
| Report Generator | Oui | Oui (chemin inscriptible) | Oui | Oui | Découper le rapport conflits (8 190 entrées) |
| API HTTP `/api/pipeline/*` | Oui | Oui (11 routes) | Partiel (unitaires, pas HTTP) | Oui | Test HTTP de bout en bout |
| Onglet Pipeline du dashboard | Oui | Oui | Syntaxe Oui / visuel Non | Oui | Vérification navigateur |
| Onglets existants | Oui | Oui | Syntaxe Oui (2 SyntaxError corrigés) | Oui | Vérification navigateur |
| Feature Pool — statuts | Oui | Oui (Analyzer corrigé) | Oui | Oui | Trancher sur les 8 190 conflits |
| Chaîne audio/vidéo, télémétrie live | Non | Non | Non | Non | Hors périmètre actuel |

### Chiffres demandés

1. **Sessions analysées** : 11 180 (mesure antérieure à la dernière passe ; à remesurer, cf. dette #2).
2. **Événements identifiés** : **786 377** (0 ligne malformée, 1 167 fichiers).
3. **Agents / modèles observés** : 9 modèles suivis dans les métriques de performance ; agents visibles via `ROUTING_DECISION` et `AGENT_SELECTED`.
4. **Outils réellement utilisés** : `terminal`, `read_file`, `patch`, `skill_view` (et 269 905 `TOOL_CALL` au total).
5. **Décisions de sécurité** : 393 (APPROVE / DENY / ESCALATE) avec **12 incohérences**.
6. **Erreurs détectées** : 7 825 événements classés (5 codes).
7. **Features reliées au pipeline** : **6 / 187**.
8. **Composants encore manquants** : purge/archivage de la base, mapping feature↔log plus riche, test HTTP automatisé, test visuel des onglets.
9. **Tests** : 25 passed côté `pipeline_inspector` ; JS 3/3 valide ; `py_compile` OK. Aucun test échoué à la dernière exécution.
10. **Prochaines intégrations recommandées** : (a) trancher les 8 190 faux conflits, (b) enrichir le mapping feature↔événement, (c) politique de rétention SQLite, (d) reconstruire l'image Docker, (e) test navigateur des 12 onglets.

---

## 15. Comment vérifier toi-même

```bash
# 1) Validité JS des onglets (3 blocs doivent être OK)
python _audit_js_blocks.py

# 2) Tests du pipeline inspector
.venv/Scripts/python.exe -m pytest pipeline_inspector/tests -q

# 3) Ingestion + rapports
.venv/Scripts/python.exe -m pipeline_inspector ingest
.venv/Scripts/python.exe -m pipeline_inspector report

# 4) Le pont lit-il le bon fichier ?
.venv/Scripts/python.exe -c "from pipeline_inspector.feature_pool_bridge import FeaturePoolBridge as B; b=B('.'); print(len(b._features), b.source, b.generated_at)"

# 5) Régénérer les statuts du pool (187 attendus, 0 BROKEN/BLOCKED)
.venv/Scripts/python.exe _regen_features.py

# 6) Reconstruire l'image (le code n'est pas monté en volume)
docker compose build && docker compose up -d
```

---

## 16. Ce que je n'ai **pas** fait

- Je n'ai pas exécuté les commandes trouvées dans les logs.
- Je n'ai pas modifié un statut du Feature Pool à la main : la régénération passe par `discover → analyze → validate`.
- Je n'ai supprimé aucun journal ni rapport ; le seul `DELETE` exécuté a porté sur **ma propre base** `data/pipeline_inspector.db` avant ré-ingestion propre.
- Je n'ai pas vérifié l'affichage réel des onglets dans un navigateur.
- Je n'ai pas réaudité `life_mean_studio/` (PySide6) en profondeur.
