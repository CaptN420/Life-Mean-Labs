# PIPELINE_VALIDATION_REPORT — 2026-11-05

**Projet** : `Life_mean_realm`
**Phase** : L1 — re-validation du Pipeline Inspector existant (aucune recréation)
**Méthode** : exécution réelle. Ingestion lancée sur une **copie** des logs dans un répertoire temporaire ; les fichiers du dépôt n'ont été ouverts qu'en lecture.
**Rapport précédent conservé** : `PIPELINE_VALIDATION_REPORT.md` (2026-11-01, verdict `PARTIAL`) — non modifié.

**Verdict global : PARTIAL** — 10 points `OK`, 1 point `OK après correction` (masquage des secrets), 1 limite documentée (ingestion volumineuse).

| Point | Sujet | Verdict |
|---|---|---|
| A | Imports / compilation | `OK` |
| B | Doublons / blocs morts | `OK` |
| C | Ingestion incrémentale | `OK` |
| D | Déduplication SQLite | `OK` |
| E | Masquage des secrets | **`OK après correction`** (4 familles de jetons fuyaient) |
| F | Corrélations explicites / probables / inconnues | `OK` |
| G | Aucune corrélation présentée comme certaine sans preuve | `OK` |
| H | Analyse des décisions de sécurité | `OK` |
| I | Routes HTTP | `OK` (10/10, dont 1 piège de méthode) |
| J | Affichage réel dans Studio / dashboard | `OK` |
| K | Résultats des tests | `OK` — 28/28 |
| L | État réel du Feature Pool | `OK` — l'usage observé ne promeut rien |

---

## A. Imports et compilation — OK

- 15 modules `pipeline_inspector/*.py` compilés un par un : **0 échec**.
- `experiments/dashboard.py` compile : **0 échec**.
- Blocs `<script>` inline du dashboard : **3/3** valides via `node --check` (v22.23.2), dont le bloc principal de 3 666 lignes.

## B. Doublons et blocs morts — OK

- Analyse AST des 15 modules : **aucune** définition de fonction/classe en double.
- Recherche de **corps de fonction identiques** entre modules (hachage de l'AST) : **aucun doublon**.

## C. Ingestion incrémentale — OK

Découverte réelle sur le dépôt : **1 386 fichiers** via 6 adapters.

```
code_lab_events 440 · code_lab_trajectory 308 · raw_debates 634
hermes_audit 1 · captn_experiences 1 · text_log 2
```

Deux passes consécutives sur la même copie :

```
run 1 : 392 151 événements ajoutés, 1 386 fichiers, 0 erreur, 66.65 s
run 2 :       0 événement ajouté,  1 386 fichiers,          1.92 s
compteur SQLite : 392 151 → 392 151   (idempotent = true)
```

Distribution effectivement stockée : 392 151 événements, 6 647 sessions.
Types dominants : `TOOL_CALL` 122 088 · `AGENT_SELECTED` 87 131 · `PIPELINE_START` 43 862 ·
`TEST_RESULT` 43 934 · `ROUTING_DECISION` 43 407 · `PIPELINE_COMPLETE` 26 238 · `PIPELINE_ERROR` 17 884.
Sécurité : `SECURITY_REVIEW` 139, `SECURITY_APPROVE` 137, `SECURITY_DENY` 100, `SECURITY_ESCALATE` 20.

## D. Déduplication SQLite — OK

Réinsertion des 50 premiers événements déjà présents :

```
échantillon 50 → lignes insérées 0 → compteur 392 151 → 392 151
```

La clé d'événement est stable : un même enregistrement relu ne crée pas de doublon.

## E. Masquage des secrets — OK après correction (défaut confirmé)

Testé avec 9 formes de secrets réelles. **4 familles passaient en clair** :

| Secret | Avant | Après |
|---|---|---|
| `sk-proj-…` (OpenAI) | masqué | masqué |
| `gho_…` / `github_pat_…` | masqué | masqué |
| `Bearer …` | masqué | masqué |
| `password=…` (court) | masqué | masqué |
| `AKIA…` (AWS) | masqué | masqué |
| **`hf_…` (HuggingFace)** | **en clair** | masqué |
| **`xoxb-…` (Slack)** | **en clair** | masqué |
| **`AIza…` (Google)** | **en clair** | masqué |
| **`glpat-…` (GitLab)** | **en clair** | masqué |

Cause : `_SECRET_PATTERNS` ne reconnaissait ces jetons que s'ils étaient précédés d'un mot-clé
(`token=`, `api_key:`), ce qui n'est pas le cas dans une ligne de log qui affiche l'en-tête brut.

Correction : 4 motifs ajoutés à `pipeline_inspector/redaction.py` + test de non-régression
`test_redaction_masks_provider_tokens_recognized_at_first_sight`. Le masquage des chemins
utilisateur (`C:\Users\<user>` → `~/`) et des clés JSON sensibles était déjà correct, y compris en
profondeur.

## F. Corrélations — OK

Quatre situations construites et vérifiées sur les vraies fonctions (`build_links`, `correlation_summary`, `annotate`) :

| Situation | Liens | Relation | Confiance |
|---|---|---|---|
| `model_call_id` identique | 1 | `explicit` | 1.00 |
| même `session_id`, ordre temporel | 1 | `probable` | 0.70 |
| même `task_id` (sans id de corrélation) | 1 | `probable` | 0.85 |
| aucun identifiant commun | **0** | — | — |

Le module refuse explicitement de fabriquer un lien : sans identifiant, `link_to_previous` reste
`null` et `correlation` reste `unknown`.

## G. Aucune certitude sans preuve — OK

`correlation_summary` sur le jeu mixte (8 événements) :

```
links_explicit 1 · links_probable 2 · links_unknown 4 · events_without_session 2
```

La chaîne « certain » n'apparaît nulle part dans la sortie. Un `task_id` partagé ne produit jamais
`explicit` (commentaire explicite dans le code : « prouve l'appartenance à la MÊME TÂCHE, pas un lien
causal »).

## H. Décisions de sécurité — OK

Jeu de test : `SECURITY_REVIEW` → `SECURITY_DENY` → `TOOL_CALL` (même `task_id`), plus un `SECURITY_APPROVE` isolé.

```
total_decisions 3 · by_decision {REVIEW 1, DENY 1, APPROVE 1} · executions_observed 1
inconsistencies 2 :
  - denied_but_executed   (clé task_id:t1)      confidence "probable"
  - approved_without_execution (clé session_id:s2) confidence "probable"
```

Les deux anomalies sont **étiquetées `probable`**, jamais présentées comme une violation établie, et
la sortie porte un champ `caveat`. C'est le comportement attendu.

## I. Routes HTTP — OK (10/10)

Sur le dashboard Docker (`127.0.0.1:8080`), réponses réelles :

| Méthode | Route | Résultat |
|---|---|---|
| GET | `/api/pipeline/stats` | 200 — 664 o |
| GET | `/api/pipeline/sessions` | 200 — 51 269 o |
| GET | `/api/pipeline/events` | 200 — 4 657 o |
| GET | `/api/pipeline/errors` | 200 — 14 023 o |
| GET | `/api/pipeline/security` | 200 — 557 o |
| GET | `/api/pipeline/graph` | 200 — 8 078 o |
| GET | `/api/pipeline/performance` | 200 — 2 325 o |
| GET | `/api/pipeline/features` | 200 — 1 731 o |
| POST | `/api/pipeline/reports` | 200 — 733 o (rapports écrits) |
| POST | `/api/pipeline/export` | 200 — 76 o (JSON exporté) |

**Piège methodologique** : `reports` et `export` ont d'abord renvoyé 404 — ils sont **POST-only**.
Aucun défaut produit ; c'était une erreur de méthode de test. Vérifié en POST avec jeton CSRF.

## J. Affichage réel — OK

- Un bloc UI dédié existe dans `experiments/ui/dashboard.html` (« Pipeline Inspector — logique UI
  (lecture seule) »), avec `const PI_BASE = '/api/pipeline'`.
- Les appels sont construits dynamiquement (`PI_BASE + '/…'`), donc un `grep` naïf comptant des URL
  littérales en trouve zéro : faux négatif de méthode, pas de fonctionnalité manquante.
- Les données affichées proviennent des routes ci-dessus (payloads non vides vérifiés).
- Lecture seule confirmée : aucun `POST` déclenché par l'affichage ; les actions `ingest`,
  `reports`, `export` restent des boutons explicites.

## K. Tests — OK

```
pipeline_inspector/tests : 28 passed  (27 avant l'ajout du test de masquage)
```

## L. Feature Pool — OK (pas de promotion gratuite)

`GET /api/pipeline/features` :

```
features_loaded 989 · features_observed 2 · features_not_observed 987
total_events_scanned 5 005
```

Les deux features observées restent au statut `DISCOVERED` avec `integration_status: NOT_STARTED`,
et la ligne porte : « Usage observé ≠ validation. Statut Feature Pool non modifié. »

Une fonctionnalité n'est donc **jamais** promue `READY` parce qu'elle a été découverte, analysée ou
observée dans des logs.

---

## Limites documentées (non corrigées, non bloquantes)

1. **Volumétrie** : `data/raw_debates/` contient des fichiers jusqu'à **103 Mo**. L'ingestion
   complète prend 66 s sur copie locale ; sur le volume réel, prévoir un premier passage long.
   L'idempotence rend les passages suivants quasi gratuits (1,9 s).
2. **30 événements `UNKNOWN`** sur 392 151 (0,008 %) : lignes de log non reconnues par les adapters.
   Elles sont conservées telles quelles plutôt que devinées — c'est le comportement voulu, mais la
   liste mérite d'être revue si elle grossit.
3. **Les fichiers tronqués pour le test** (> 2 Mo) n'ont été copiés que sur 5 000 lignes : le comptage
   exact sur ces fichiers n'est pas celui du volume réel, seulement celui de la copie.

Aucun fichier de log d'origine n'a été modifié. Aucune commande trouvée dans les logs n'a été
exécutée. Aucune donnée supprimée hors du répertoire temporaire de test.
