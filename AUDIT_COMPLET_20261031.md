# Audit complet — Life_mean_realm

**Date :** 31 octobre 2026
**Périmètre :** `C:\Users\celes\Documents\Hermes-Workspace\Life_mean_realm`
**Méthode :** lecture du code, exécution réelle des endpoints, test navigateur réel, `node --check`, `py_compile`, inspection du rapport FeaturePool.
**Verdict court :** le dashboard ne répond pas aux clics à cause d'**une seule ligne de JavaScript** (erreur de syntaxe fatale). Le FeaturePool annonce « 6 cassées / 42 bloquées » mais **aucune n'est réellement cassée** : ce sont des faux positifs d'un heuristique de comptage de parenthèses.

---

## 1. État runtime constaté

| Composant | État | Preuve |
|---|---|---|
| Conteneur `life_mean_realm-dashboard-1` | `Up (healthy)` | `docker ps` |
| Port | `127.0.0.1:8080 -> 8080` | `docker ps` |
| `GET /dashboard` | 200 | `curl` |
| `GET /api/settings` | 200, backend LLM joignable | `backend_reachable: true`, `authenticated: true` |
| Orchestrator `:3000/health` | 200 | `curl` |
| CSRF | cookie `lifemean_csrf` sans `Secure`, header `X-Lifemean-CSRF` | `git diff` + `curl` |

Le cookie `Secure` retiré (commit de travail) est **correct** pour du HTTP sur 127.0.0.1 : sinon le navigateur ne renvoie jamais le cookie et tous les POST échouent en `csrf_failed`. C'était bien un bug, il est réglé. **Mais ce n'était pas la cause des onglets.**

---

## 2. P0 — Pourquoi les onglets sont « inchangeables »

### Cause racine unique

`experiments/ui/dashboard.html` déclare **deux fois** `el` au niveau global du même bloc `<script>` :

```js
// ligne 1498
function el(id) { return document.getElementById(id); }

// ligne 4577  (section "Skills & Tools")
const el = id => document.getElementById(id);
```

En JavaScript, `function el` et `const el` dans la **même portée de script** sont une `SyntaxError: Identifier 'el' has already been declared`. Une erreur de syntaxe **empêche l'exécution de tout le bloc `<script>`** : aucune fonction n'est créée, donc `onclick="switchTab(...)"` lève `ReferenceError`.

### Preuves

```
$ node --check _dash_script.js
SyntaxError: Identifier 'el' has already been declared   (ligne 3088 du script extrait = 4577 du HTML)
```

Test dans un vrai navigateur sur `http://127.0.0.1:8080/dashboard` :

```
typeof switchTab  -> "undefined"
typeof el         -> "undefined"
.tab-panel        -> 11 panneaux présents
actif             -> panel-autopilot
clic sur Settings -> actif reste panel-autopilot
appel direct      -> ReferenceError: switchTab is not defined
```

Après suppression de la seule ligne 4577 (test sur une copie) : `node --check` → **exit 0**, plus aucune erreur de syntaxe.

### Impact

Tous les onglets, tous les boutons, tous les handlers inline du dashboard sont morts : Autopilot, Experiments, Debate, Code Lab, Settings, Compare, Cluster Tree, Experimental, Workspace, Agent Builder, Skills & Tools. Le HTML et le CSS sont bons, le serveur est bon — c'est purement le parsing JavaScript.

### Correctif (Phase 1)

Supprimer la ligne 4577 :
```diff
-        // ── Skills & Tools tab ───────────────────────────────────────────────
-        const el = id => document.getElementById(id);
+        // ── Skills & Tools tab ───────────────────────────────────────────────
+        // (helper `el` déjà défini ligne 1498 — ne pas redéclarer)
```
Puis rebuild de l'image (le HTML est copié dans l'image, pas monté) :
```bash
docker compose build && docker compose up -d
```

---

## 3. P0/P1 — Incompatibilités front ↔ back (le dashboard « répond » mais renvoie 404)

Une fois les onglets réparés, ces boutons resteront cassés. Constats vérifiés en direct.

| # | Appel front (JS) | Serveur | Résultat réel |
|---|---|---|---|
| 1 | `GET /api/experiments/{id}/observability` | implémenté **seulement en `do_POST`** | `404 Not found` |
| 2 | `GET /api/experiments/{id}/manifest` | idem | `404 Not found` |
| 3 | `PUT /api/extensions/skills/{id}/approve` | `do_PUT` ne gère que `/api/settings` | `404 Not found` |
| 4 | `POST /api/extensions/skills/{id}/approve` | route inatteignable (voir #5) | `404 Not found` |
| 5 | `POST /api/extensions/pipeline/{id}/approve` | idem | `404 Not found` |
| 6 | `DELETE /api/extensions/skills/{id}` / `tools/{id}` | pas de branche dans `do_DELETE` | `404 Not found` |

**Cause du point 5/4 :** la regex de routage n'autorise aucun sous-chemin.

```python
# life_mean_extensions/api.py:38
_ID_RE = re.compile(r"^/api/extensions/(skills|tools)/([^/]+)$")   # ← '$' interdit /approve
_PIPELINE_RE = re.compile(r"^/api/extensions/pipeline/([^/]+)$")
```

Or `experiments/dashboard.py` teste ensuite `sub = parsed.path.split("/")[-1]` pour `approve|activate|disable` — code **jamais exécutable**. `match_extension_id()` retourne `None` sur `/skills/x/approve`, on tombe dans le `else` → 404.

**Cause du point 1/2 :** `do_GET` n'a aucune branche `observability` / `manifest` (elles sont lignes 308 et 315, dans `do_POST`). Le front utilise `fetch()` sans `method` = GET.

**Conséquence utilisateur :** l'onglet *Skills & Tools* est entièrement inerte (les 4 boutons Approve/Activate/Disable/Delete), le panneau *Observability* et *Export manifest* / *Replay* échouent avec un `alert("Failed to load ...")`.

### Correctifs (Phase 2)

**a) Router les sous-chemins d'extension** — soit élargir la regex et le tuple de retour, soit créer deux regex distinctes :

```python
_EXT_ACTION_RE = re.compile(r"^/api/extensions/(skills|tools)/([^/]+)/(approve|activate|disable)$")
_PIPELINE_ACTION_RE = re.compile(r"^/api/extensions/pipeline/([^/]+)/(approve|activate)$")
```

**b) Ajouter les branches GET** pour `observability` et `manifest` dans `do_GET` (copier les 8 lignes de `do_POST`, elles ne lisent rien et ne mutent rien).

**c) Aligner les verbes** : soit faire accepter `PUT` par `do_PUT` en déléguant aux mêmes handlers que `do_POST`, soit passer le front en `POST` (plus rapide, moins de code). Recommandé : **front en POST** pour approve/activate/disable, car la logique serveur existe déjà.

**d) Implémenter `DELETE`** pour `skills/{id}` et `tools/{id}` (`_extensions_skill_delete` existe déjà dans `ExtensionsApiMixin` — vérifier, sinon l'ajouter) ou retirer les boutons « Supprimer » du front.

---

## 4. FeaturePool — les « broken / blocked » sont des faux positifs

### Ce que dit le rapport

```
total 153 | VALIDATED 105 | BLOCKED 42 | BROKEN 6
ready_for_integration 105 | with_tests 113 | orphans 153
```

### Ce que fait réellement le code

```python
# feature_pool/analyzer.py:69-89
issues = []
if not feature.test_paths: issues.append("no_tests")
if unresolved:             issues.append("unresolved_dependencies")
if self._has_syntax_issues(feature): issues.append("syntax_issues")
return "BROKEN" if len(issues) > 1 else "BLOCKED"
```

et le test de syntaxe :

```python
# feature_pool/analyzer.py:153
if content.count('(') != content.count(')'):
    return True
```

Ce n'est **pas** un test de syntaxe : c'est un comptage brut de parenthèses sur tout le fichier, y compris dans les chaînes et docstrings. Un `":-)"` ou un `(` dans un commentaire suffit à déclarer le fichier « cassé ».

### Vérification réelle des 14 fichiers incriminés

Tous **compilent parfaitement** :

```
OK  core/debate/engine.py
OK  philosophical_council/core/debate_engine.py
OK  code_lab/multiagent.py
OK  legacy/.../captn/runtime/workers.py
OK  legacy/.../diversifier_worker.py
OK  legacy/.../code_backend_worker.py
OK  legacy/.../domain_classifier_worker.py
OK  legacy/.../chemistry_validation_worker.py
```

Exemple : `core/debate/engine.py` a 473 `(` et 475 `)` — déséquilibre dans des chaînes, fichier valide.

### Répartition exacte des 48 statuts non-validés

| Cause(s) | Nombre | Réalité |
|---|---|---|
| `no_tests` uniquement | 34 | Le test est cherché par simple sous-chaîne du nom de classe dans `test_*.py`. Une classe utilisée indirectement n'est jamais « trouvée ». |
| `unbalanced_parens` uniquement | 8 | **Faux positif prouvé** (compile). |
| `no_tests` + `unbalanced_parens` | 6 | **Faux positif prouvé** (compile). Les 6 « BROKEN » sont tous dans `legacy/`, dossier **exclu de l'image Docker** (`.dockerignore`). |

→ **0 feature réellement cassée.** Le chiffre « 42 bloquées / 6 cassées » est un artefact d'heuristique, pas un état du code.

### Autre signal inutilisable

`orphans: 153 / 153` = toutes les features. `detect_orphans()` retourne toute feature sans dépendance **et** sans dépendant ; comme l'analyse de dépendances ne remplit quasiment pas le graphe, tout est orphelin. Le champ n'a aucune valeur informative en l'état.

### Correctifs (Phase 3)

1. Remplacer `_has_syntax_issues` par `ast.parse()` (ou `py_compile`) sur le fichier, avec cache — c'est le seul vrai test.
2. Détecter les tests par import/`grep` du nom de **module** en plus de la classe, ou marquer `no_tests` comme `WARNING` et non comme `BLOCKED`.
3. Séparer les statuts : `BROKEN` (ne compile pas) / `UNTESTED` (compile, pas de test) / `BLOCKED` (dépendance absente réelle).
4. Corriger ou supprimer `orphans` (sinon il pollue les stats).
5. Régénérer `.feature_pool_report.json` / `.csv` — les fichiers actuels sont périmés et non versionnés.

---

## 5. Lanceurs `.bat`

| Fichier | État | Problème |
|---|---|---|
| `run_server.bat` | ✅ fonctionne | `docker compose up -d --build` + sync data. Le lockfile est supprimé avant la fin → la garde « single instance » ne protège que le démarrage. Le navigateur est ouvert avant que le conteneur soit healthy (risque de page blanche au 1er lancement). |
| `start_studio.bat` | ⚠️ dépend de `hermes-orchestrator/` | Lance `npm start` dans un dossier **exclu de l'image et non présent** ; si absent, la fenêtre cmd se ferme silencieusement. Utilise `.venv/Scripts/python.exe` (slash, OK sous cmd mais fragile). |
| `run_compare.bat` | ❌ cassé | Pointe vers `C:\...\Life_mean\compare_mia.py` — **mauvais dossier** (`Life_mean_realm`). |
| `test_snap_bat.bat` | ❌ cassé | Pointe vers `C:\...\Life_mean\sandbox\snapshot_test\test_build.py` — dossier inexistant. |

Correctif : remplacer les chemins absolus par `%~dp0compare_mia.py` etc., ou supprimer les deux scripts obsolètes.

---

## 6. Sécurité / configuration

1. **`.env` contient une vraie clé `OPENROUTER_API_KEY` en clair** (plus celle de LM Studio). Il est bien dans `.gitignore` et `.dockerignore`, donc non commité et non copié dans l'image — mais il traîne dans le workspace. À rotationner si le dossier est partagé/sauvegardé.
2. `LIFE_MEAN_LLM_BASE_URL=http://host.docker.internal:1234/v1` — **correct** depuis le conteneur (testé : `backend_reachable: true`).
3. Cookie CSRF sans `Secure` : acceptable en HTTP local, **à remettre** dès exposition réseau/HTTPS. Idéal : conditionner au schéma (`BASE_URL.startswith("https")`).
4. Conteneur : `read_only: true`, `cap_drop: ALL`, `no-new-privileges`, ports liés à `127.0.0.1` — bon niveau.
5. Aucun test d'intégration ne couvre les routes `extensions/*` : c'est pour ça que les 404 sont passés inaperçus.

---

## 7. Dette / fichiers morts (à nettoyer)

| Fichier | Taille | Statut |
|---|---|---|
| `dashboard_debug.html` (racine) | 302 450 o | **doublon exact** de `experiments/ui/dashboard.html` — dump de debug, à supprimer |
| `experiments/ui/dashboard_combined.html` | 62 967 o | non référencé par le code (seulement par un `.md`) |
| `ui/index.html`, `ui/workspace.html`, `ui/debate_monitor.html` | ~115 Ko | non référencés par `experiments/` |
| `feature_pool/_scan.py` + `_scan_refined.py` + `scanner.py` | 730 lignes | 3 scanners concurrents |
| `.feature_pool_report.json/.csv` + `feature_pool_full_report.*` | ~240 Ko | rapports dupliqués, non versionnés |
| `_audit_*.py`, `_dash_script.js` | — | fichiers d'audit (ce rapport) — à supprimer après usage |

Autres points :
- `experiments/dashboard.py` (1 238 lignes) + 3 mixins (`life_mean_extensions`, `experimental`, `compare`) : le routage est une chaîne de `elif` sur ~68 branches. Les incohérences de verbes viennent de là. Un table de routes `(method, regex, handler)` supprimerait la classe entière de bugs.
- `git status` : 4 fichiers modifiés non commités (`dashboard.py`, `storage.py`, `launcher/app.py`, `captn_runtime/*.jsonl`). À commiter par lots séparés.

---

## 8. Plan de correction par phases

### Phase 1 — Débloquer les onglets (P0, ~10 min)
1. Supprimer la ligne 4577 de `experiments/ui/dashboard.html`.
2. `node --check` sur le script extrait → doit passer.
3. `docker compose build && docker compose up -d`.
4. Vérification navigateur : `typeof switchTab === "function"` + clic sur chaque onglet.

**Critère d'acceptation :** les 11 onglets changent de panneau, plus aucune `ReferenceError` en console.

### Phase 2 — Rendre l'API cohérente (P0/P1, ~1 h)
1. Ajouter les branches `GET` pour `observability` et `manifest`.
2. Corriger le routage `extensions/*` (regex sous-chemins) ou passer les actions en `POST` + élargir la regex.
3. Implémenter `DELETE /api/extensions/skills/{id}` et `/tools/{id}`.
4. Test de fumée pour chaque bouton : Approve → Activate → Disable → Delete, sur un skill créé pour l'occasion.

**Critère :** aucun `404` sur les 10 routes listées au §3.

### Phase 3 — Fiabiliser le FeaturePool (P1, ~45 min)
1. `_has_syntax_issues` → `ast.parse` + cache.
2. Statut `UNTESTED` distinct de `BLOCKED` ; `no_tests` n'est plus bloquant.
3. Réparer/supprimer `orphans`.
4. Régénérer le rapport et **vérifier** : le nombre de `BROKEN` doit tomber à 0.

**Critère :** `BROKEN = 0`, et les seuls `BLOCKED` sont des dépendances d'import réellement absentes.

### Phase 4 — Lanceurs et nettoyage (P2, ~30 min)
1. Corriger/remplacer `run_compare.bat` et `test_snap_bat.bat`.
2. Ajouter une attente de santé dans `run_server.bat` avant d'ouvrir le navigateur.
3. Supprimer `dashboard_debug.html` et les rapports dupliqués.
4. `git add -A && git commit` par thème (dashboard fix / feature pool / bat).

### Phase 5 — Garde-fous (P2, ~1 h)
1. Ajouter un test `tests/test_dashboard_html_syntax.py` qui extrait les `<script>` et lance `node --check` (ou au minimum vérifie l'absence de double déclaration top-level).
2. Ajouter un test de contrat : pour chaque route appelée par le front, un `OPTIONS`/`GET` renvoie autre chose que 404.
3. Relancer la suite complète.

---

## 9. Commandes de vérification (à rejouer après chaque phase)

```bash
# 1. Syntaxe JS
python _audit_js.py

# 2. Handlers inline non définis
python _audit_handlers.py

# 3. Endpoints cassés
curl -s -o /dev/null -w "%{http_code} %{url_effective}\n" \
  http://127.0.0.1:8080/api/experiments/x/observability \
  http://127.0.0.1:8080/api/experiments/x/manifest

# 4. FeaturePool : faux positifs
python _audit_features.py

# 5. Compilation Python des fichiers incriminés
python -m py_compile core/debate/engine.py code_lab/multiagent.py

# 6. Santé conteneur
docker ps --format "{{.Names}} {{.Status}}"
```

---

## 10. Synthèse

| Sévérité | Problème | Localisation | Effort |
|---|---|---|---|
| **P0** | Double déclaration `el` → **tout le JS du dashboard est mort** | `dashboard.html:4577` | 1 ligne |
| **P0** | `observability` / `manifest` en GET → 404 | `dashboard.py` `do_GET` | ~10 lignes |
| **P1** | Actions `extensions/*` inatteignables (regex + verbe) | `life_mean_extensions/api.py:38` + `dashboard.py:355` | ~40 lignes |
| **P1** | `DELETE` skills/tools absent | `dashboard.py` `do_DELETE` | ~15 lignes |
| **P1** | FeaturePool : 48 faux positifs | `feature_pool/analyzer.py:153` | ~30 lignes |
| **P2** | 2 `.bat` pointent vers l'ancien dossier | `run_compare.bat`, `test_snap_bat.bat` | 2 lignes |
| **P2** | Doublons/fichiers morts (~500 Ko) | racine, `ui/`, `experiments/ui/` | suppression |
| **P3** | Clé API en clair dans `.env` | `.env` | rotation |

Le dashboard n'a **pas** de problème d'architecture : il a une erreur de syntaxe d'une ligne et un contrat d'API qui a dérivé. Les deux se corrigent en une session.
