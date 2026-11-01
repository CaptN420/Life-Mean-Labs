# LIFE_MEAN — AUDIT & FEATURE POOL (V1)

**Date** : 2026-10-31
**Projet actif** : `C:\Users\celes\Documents\Hermes-Workspace\Life_mean_realm`
**Méthode** : audit statique par AST, aucun code legacy exécuté, aucun delete.

---

## 1. Écarts de comptage expliqués

| Mesure | Valeur annoncée | Valeur réelle | Explication |
|--------|-----------------|---------------|-------------|
| Fichiers Python modernes | 191 | **1 613** | Le `191` était une sous-mesure (un seul sous-dossier). Comptage net hors `legacy/`, `venv`, `build`, `dist`, `crawled`. |
| Fichiers Python legacy | ~10 400 | **10 399** brut (`find legacy -name "*.py"`) | Confirme l'ordre de grandeur. Sur ce total, **481** sont applicatifs CaptN-BRAIN/Mia_Brain ; le reste sont des dépendances tierces embarquées (`crawled/`, `venv/`). |
| Fonctionnalités découvertes | 147 | **187** | Le scan FeaturePool couvre 14 répertoires modernes + legacy. Écart = classes non comptées dans l'audit manuel initial. |

**Doublons de noms** : aucun — les 187 noms de features sont uniques dans le registre.

### Répartition par source
- **Modernes** : 117
- **Legacy** : 70

### Répartition par statut technique
- VALIDATED : 129
- BLOCKED : 52
- BROKEN : 6

---

## 2. Preuve d'inventaire (scan réel)

```
Discovered 187 features
Agents: 55, Debates: 29
Legacy: 70, Modern: 117
Analyzed 187 features
Total features: 187
Categories: ['routing','agents','experiments','debate','personas','studio',
             'providers','validation','safety','autopilot','observability',
             'generation','persistence','crawlers']
All tests passed!
```

Sortie brute : `feature_pool/tests/test_feature_pool.py`.

---

## 3. Crawlers récupérés (legacy)

| Fichier | Lignes | Contenu | Tests |
|---------|--------|---------|-------|
| `legacy/Mia_Brain/CaptN-BRAIN-main/captn/workers/data_ingestion/crawler.py` | 1002 | `GitHubCrawler`, `CrawlerWorker`, `CrawlResult`, rate-limit, export JSONL | — |
| `legacy/Mia_Brain/CaptN-BRAIN-main/tools/crawler_cli.py` | 182 | CLI d'utilisation du crawler | — |
| `legacy/Mia_Brain/CaptN-BRAIN-main/tests/test_crawler.py` | 361 | 17 tests (parse_repo, rate-limit, budget, dataset export) | 17 ✅ |

Classe cible : `GitHubCrawler.crawl(owner, name, branch, include_ext, max_files)`.

---

## 4. Architecture FeaturePool implémentée

```
feature_pool/
  schemas.py            — modèles de données, statuts technique vs intégration
  registry.py           — registre versionné, recherche, statistiques
  scanner.py            — découverte statique AST (lecture seule)
  analyzer.py           — analyse capacités, confiance, tests
  dependencies.py       — graph de dépendances, orphelins, conflits
  compatibility.py      — matrice de compatibilité
  integration_planner.py— plans d'intégration (sans exécution)
  history.py            — traçabilité des changements
  tests/test_feature_pool.py — suite de tests
```

**Cycle de vie** : `DISCOVERED → ANALYZED → VALIDATED → READY → INTEGRATED`
**États complémentaires** : `BROKEN, BLOCKED, ARCHIVED, EXPERIMENTAL` (ARCHIVED = conservé, jamais supprimé)

**Sécurité** :
- Scanner 100 % lecture seule (AST, aucune exécution).
- Aucun import dynamique du legacy.
- Aucune activation automatique — validation explicite requise.
- Aucun delete, aucun écrasement, aucun déplacement.

---

## 5. Interface Life_mean Studio

Page **« Feature Pool »** ajoutée à `life_mean_studio/launcher/app.py` :
- Tableau consultable (ID, Nom, Catégorie, Source, Statut, Intégration, Tests, Confiance, Action).
- Recherche + filtres (statut / catégorie / source).
- Rafraîchissement et export CSV.
- Panneau d'historique (20 derniers changements).
- En lecture seule — pas d'activation automatique.

---

## 6. Roadmap de récupération legacy

| Phase | Focus | Cibles |
|-------|-------|--------|
| **P0 — Immédiat** | Crawlers | `GitHubCrawler`, `crawler_cli`, `test_crawler` (17 tests) |
| **P1 — Semaine 2** | Moteur de débat | `DebateState`, `BaseDebateCore` (historical) |
| **P2 — Semaine 3** | Providers & routing | `LLMProvider`, `OpenAIProvider`, `SmartRouter` |
| **P3 — Semaine 4** | Validation & generation | `MathValidator`, `PatchValidator`, `FixGenerator` |

---

*Rapport généré par audit statique réel. Fichiers de preuve : `.feature_pool_report.json`, `feature_pool_full_report.json`, `feature_pool_full_report.csv`.*
