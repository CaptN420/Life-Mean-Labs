# LIFE_MEAN — EXAMEN D'ÉTAT, CHECKPOINT ET FEATURE POOL FIRST

**Rapport** : `reports/EXAMEN_ETAT_20261101.md`
**Date** : 2026-11-01, 00:38 → 01:05 (heure locale, UTC−04:00)
**Projet** : `C:\Users\celes\Documents\Hermes-Workspace\Life_mean_realm`
**Branche** : `main` @ `d1237af` — aucun commit créé, aucun fichier déplacé ou supprimé.
**Nature** : examen non destructif. Aucune nouvelle implémentation. Aucune nouvelle fonctionnalité.

---

## 0. Méthode et limites

Toute affirmation de ce rapport vient d'une commande réellement exécutée pendant cette session, dont la sortie est citée. Ce qui n'a pas été exécuté est marqué **NON VÉRIFIÉ**.

Périmètre chiffré : **1756 fichiers `.py`, ~159 950 lignes** hors `.venv`, `node_modules`, `legacy/`.

Trois chiffres de mon message précédent étaient **faux ou incomplets** ; ils sont corrigés au §2 (imports hors projet, « Studio toujours actif », « packaging corrigé »).

---

## 1. Verdict sur les affirmations à vérifier

| Affirmation | Verdict | Preuve |
|---|---|---|
| 110 tests Studio réussis | **VRAI** | `pytest life_mean_studio/tests -q` → `110 passed, 2 skipped in 35.53s` |
| 2 tests ignorés | **VRAI, avec motif précis** | `SKIPPED [1] test_prompts.py:170` et `[1] test_workflows.py:153` — motif : `seed_defaults` sauté « due to SQLite file locking » (verrou SQLite sous Windows) |
| `jinja2` ajouté aux dépendances | **VRAI et effectif** | `pyproject.toml:16` `jinja2>=3.1` ; paquet installé ; `test_launcher.py` → 24 passed (22+2 avant) |
| Packaging corrigé (`feature_pool*`, `life_mean_studio*`) | **VRAI seulement après réparation** | La simple édition de `pyproject.toml` **ne suffisait pas** : le finder editable installé ne listait que 11 paquets, sans `feature_pool`/`life_mean_studio`/`pipeline_inspector`. Import depuis `C:\Users\celes\AppData\Local\Temp` → `ModuleNotFoundError` ×3. Réparation : `pip install -e . --no-deps --no-build-isolation` → MAPPING régénéré, 13 imports OK depuis un autre cwd |
| « Studio et orchestrateur toujours actifs » | **FAUX au moment du contrôle** | Aucun processus `.venv/Scripts/python` actif, aucune fenêtre `Life_mean Studio`. Orchestrateur : OK (`:3000` LISTENING, `/health` → 200). Studio **relancé** pendant cette session et re-vérifié : fenêtre présente, `SendMessageTimeoutW` → *responsive* |

### Commandes exécutées (extrait)

| Commande | Résultat |
|---|---|
| `git status --porcelain` | 8 fichiers modifiés, ~20 entrées non suivies |
| `pytest life_mean_studio/tests -q -rs` | `110 passed, 2 skipped in 35.53s` |
| `pytest life_mean_studio/tests/test_launcher.py -q` | `24 passed in 2.88s` |
| `pytest tests/test_sentinel.py -q` | `31 passed in 0.10s` |
| `pytest pipeline_inspector/tests -q` | `27 passed in 2.13s` |
| `pytest feature_pool/tests -q` | `9 passed in 6.37s` |
| `import` des 13 paquets depuis `%TEMP%` | 13/13 OK après réinstallation editable |
| `GET :3000/health` | `200 {"status":"ok","activeModel":null,"vram":80000,"queueLength":0}` |
| `GET :3000/codelab/status/x` | `401 Unauthorized` (auth exigée, attendu) |
| `GET :8080/dashboard` | `200`, 327 535 octets (conteneur Docker) |
| `GET :8082/dashboard` | **connexion refusée** (dashboard hôte arrêté) |
| `GET :1234/v1/models` (LM Studio) | **connexion refusée** — backend LLM hors ligne |
| `pytest tests -v` (suite racine complète) | **29 failed, 1552 passed, 13 skipped, 12281 warnings in 434.17s (7 min 14 s)** — 1594 tests collectés |
| `pytest tests -q` (2ᵉ exécution, indépendante) | **29 failed, 1552 passed, 13 skipped in 439.30s (7 min 19 s)** — **mêmes comptes, même liste d'échecs ⇒ baseline reproductible** |

### 1bis. Les 29 échecs de la suite racine, par cause (vérifiés un par un)

| Groupe | Nb | Cause réelle (message) | Nature |
|---|---|---|---|
| `test_autopilot_llm_adapter.py` | 5 | `Failed to fetch models: Connection error` → `error: 'No answer computed'`, `is_valid is False` | **Environnement** : LM Studio `:1234` éteint. Ces tests devraient `skip`, ils échouent |
| `test_workspace_ui.py` | 16 | `workspace.html must exist` / `FileNotFoundError: experiments\ui\workspace.html` (idem `.css`, `.js`) | **Implémentation absente** : les 3 fichiers n'existent pas (`experiments/ui/` ne contient que `dashboard.html`, `dashboard_combined.html`) |
| `test_error_memory.py` | 4 | `'fix_imports' in []`, `should_avoid_strategy(...) is False`, `get_stats() 0 == 2` | **Régression fonctionnelle** dans `code_lab/error_memory.py` (mémoire d'erreurs vide) |
| `test_phase7_weakness.py` | 1 | `KeyError: 'domain'` | **Contrat d'interface cassé** (schéma attendu ≠ produit) |
| `test_qa_fixes.py` | 1 | `assert 403 == 200` sur un `DELETE` | **Test obsolète** : le dashboard exige désormais l'en-tête CSRF (403 attendu sans en-tête) |
| `test_dashboard_ui.py` | 1 | `re.search('const\\s+el\\s*=\\s*id\\s*=>...')` → `None` | `dashboard.html` ne définit plus l'alias `el` (modifié récemment, +485 lignes) |
| `test_code_lab_visibility.py` | 1 | itération de réparation non visible dans la sortie | **Traçabilité** Code Lab |

**Aucun de ces 7 fichiers de test n'importe les 4 fichiers que j'ai modifiés** (`grep -l` sur `feature_pool|life_mean_studio|pyproject` → vide). Ces échecs sont **antérieurs à cette session**.

---

## 2. Corrections apportées à mes propres affirmations

1. **« Packaging corrigé »** : partiellement faux avant réinstallation. Corrigé par régénération du finder editable (preuve ci-dessus).
2. **« Studio toujours actif »** : faux au moment du contrôle. Le Studio avait disparu (aucun processus, aucune fenêtre). Relancé et vérifié *responsive*. **Expérience de contrôle** : lancé directement (`python -m life_mean_studio`, sans passer par une session terminal managée), le Studio reste vivant **≥ 120 s** (fenêtre présente à t=20/40/60/80/100/120 s) avec **0 octet dans le log** et aucun `faulthandler` déclenché. Donc : l'application ne meurt pas d'elle-même ; les disparitions observées correspondent aux lancements effectués depuis ma session terminal, pas au scénario double-clic de l'utilisateur. Aucun test automatisé ne couvre ce point (R12).
3. **Port du dashboard** : mon profil interne indiquait `8082` ; sur cette machine le dashboard qui répond est **`8080` (Docker)**, `8082` est éteint.

---

## 3. Checkpoint (artefacts de récupération)

Répertoire : `reports/CHECKPOINT_20261101_003801/`

| Fichier | Contenu |
|---|---|
| `git_status.txt` | état complet du worktree |
| `git_branch.txt`, `git_head.txt` | `main`, 5 derniers commits |
| `git_diff.patch` | **diff complet des 8 fichiers modifiés** |
| `untracked.txt` | liste des fichiers non versionnés |
| `git_stash.txt` | vide (aucun stash) |
| `python_version.txt`, `pip_freeze.txt` | environnement exact (Python 3.14.9, PySide6 6.12.0) |
| `services.txt` | état du port 3000 |
| `uncommitted_sources.tar.gz` | **386 519 octets** — snapshot des sources non commitées (8 modifiés + `feature_pool/` + `pipeline_inspector/`) |
| `MANIFEST.txt` | commande + code de sortie de chaque capture |

### État Git

- Branche `main`, HEAD `d1237af` « fix: serve dashboard on both /dashboard and /dashboard.html ».
- **8 fichiers modifiés non commités** : `captn_runtime/captn_experiences.jsonl` (+4397), `experiments/dashboard.py` (+60/−2), `experiments/ui/dashboard.html` (+485/−4), `life_mean_studio/engine/storage.py` (+9/−4), `life_mean_studio/launcher/app.py` (+226/−?), `pyproject.toml` (+4), `sandbox/tools/tool-2/spec.json` (+1/−1), `start_studio.bat` (+38/−?).
- **~20 entrées non suivies**, dont **`feature_pool/` et `pipeline_inspector/` en entier** : deux paquets fonctionnels (2773 + ~1800 lignes, 36 tests) **ne sont pas versionnés**. C'est le risque de perte numéro un.

### Récupération

- Revenir à l'état commité : `git checkout -- <fichier>` (perd les modifications locales).
- Revenir à l'état *d'avant* mes correctifs pour un fichier précis : extraire la version du `uncommitted_sources.tar.gz` ne suffit pas (il contient l'état *après*) ; utiliser `git diff` + les hunks concernés.
- Aucune action destructive n'a été faite ; aucun `git reset`, `clean`, `stash` ni commit.

---

## 4. Inventaire réel des composants

| Composant | Classification | Preuve |
|---|---|---|
| Life_mean Studio (GUI) | **VERIFIED WORKING** | Fenêtre `Life_mean Studio` visible + `SendMessageTimeoutW`→responsive ; construction en 0,15 s ; 110 tests ; 187 lignes dans la table Feature Pool ; 4 lignes dans la table Services |
| Démarrage Studio | **VERIFIED WORKING (après correctif)** | Avant : blocage >10 min dans `_find_tests` (pile capturée par `faulthandler`). Après : `analyze_all` 0,75 s |
| Hermes Orchestrator (Node) | **VERIFIED WORKING (partiel)** | `:3000` LISTENING ; `/health` 200 ; écritures protégées (401 sans auth). Non vérifié : routage VRAM réel, appels `/codelab/task` authentifiés |
| Dashboard d'expériences | **VERIFIED WORKING** | `:8080/dashboard` 200, 327 535 octets (Docker) |
| Dashboard hôte (`:8082`) | **DOWN** | connexion refusée |
| Pipeline Inspector | **VERIFIED WORKING (API/noyau)** | 27 tests passent ; ingestion lecture-seule, masquage des secrets, pont Feature Pool. **Aucune page dans le Studio** (`grep pipeline_inspector app.py` → 0 résultat) |
| Feature Pool | **PARTIALLY WORKING** | 187 features, mais **14,0 % des classes** indexées (187/1335) et 0 feature issue de `pipeline_inspector/` ou `feature_pool/` |
| Sentinel (déterministe) | **VERIFIED WORKING** | 31 tests passent ; `core/safety/` (sentinel, policy_guard, resource_guard, loop_detector, incident_manager) |
| Sentinel (couche LLM) | **BLOCKED** | LM Studio (`:1234`) hors ligne → analyse LLM indisponible |
| PolicyGuard (permissions) | **PARTIALLY WIRED** | 179 lignes + tests (`test_chaos_safety.py`). **1 seul appel de production** : `core/debate/engine.py:1055` (`start_debate`). Jamais appelé par le Studio, `code_lab` ou le PackageManager |
| ExecutionGate / ExperimentGate | **IMPLEMENTED BUT UNVERIFIED (stub)** | `core/debate/experiment_gate.py:251` : « In a real system, this would check PolicyGuard, ResourceGuard, etc. » → ne vérifie que des limites numériques |
| CaptN Runtime | **IMPLEMENTED BUT UNVERIFIED** | `captn_runtime/` : **0 fichier de test** ne le cite (`grep` sur 47 fichiers de test) |
| Model Router / Adaptive router | **IMPLEMENTED, backend OFF** | `core/router/adaptive.py`, `code_lab` ; LM Studio refuse la connexion → non exerçable |
| Action Hub / Personal Hub | **PLANNED (absent)** | Aucun fichier ne correspond (`grep personal_hub|action hub|ActionRegistry` → 0) |
| `hermes-debate/` | **EXPERIMENTAL** | Projet séparé, non packagé, alimente 12 features « mixtes » du pool |
| `legacy/Mia_Brain/CaptN-BRAIN-main` | **LEGACY (référence)** | 70 features « legacy » du pool ; embarque son propre `venv` |
| `historical/v0-alchemy-multi-agent` | **EXPERIMENTAL (archive)** | Fournit la preuve de test de plusieurs features dites VALIDATED |

---

## 5. Risques de stabilité

Sévérité : **S1** bloquant potentiel, **S2** majeur, **S3** modéré, **S4** mineur.

| # | Risque | Preuve | Sév. | Reproductibilité | Validation suggérée | Effort | Bloque ? |
|---|---|---|---|---|---|---|---|
| R1 | **Deux paquets fonctionnels non versionnés** (`feature_pool/`, `pipeline_inspector/`) | `git status` : `?? feature_pool/`, `?? pipeline_inspector/` | S1 | permanente | `git add` + commit (autorisation requise) | 10 min | Oui, pour tout travail sérieux |
| R2 | **PolicyGuard non appliqué aux chemins d'écriture** (Studio AgentBuilder, PackageManager, code_lab) | 1 seul appel de production (`engine.py:1055`) | S1 | oui | test : écrire un agent en mode « deny » et constater le refus | 1–2 j | Oui pour la direction A |
| R3 | **ExecutionGate est un stub** | `experiment_gate.py:251` commentaire explicite + seules bornes numériques vérifiées | S1 | oui | test d'un `ExecutionGateRequest` avec PolicyGuard en deny → doit refuser | 1–2 j | Oui si le gate autorise des exécutions |
| R4 | **Feature Pool aveugle à 86 % du code** | 187/1335 classes = 14,0 % ; 0 feature de `pipeline_inspector/`/`feature_pool/` ; 27 classes sécurité invisibles dont `PolicyGuard`, `ResourceGuard`, `ExperimentExecutionGate` | S2 | oui (`scanner.py:89-92` liste de dossiers codée en dur + `_classify_feature` sur sous-chaînes) | rejouer la couverture après correctif ; comparer à un inventaire `ast` | 0,5–1 j | Oui pour « FEATURE POOL FIRST » |
| R5 | **VALIDATED à preuve faible** | 27/138 VALIDATED n'ont que des tests `legacy/`, `historical/`, `hermes-debate/` ; 12 mixtes ; 99 projet courant | S2 | oui | exiger que le fichier de test importe le module de la feature | 1 j | Oui (statut trompeur) |
| R6 | **Conflits = bruit combinatoire** | 8190 conflits = **70 legacy × 117 modern** (produit cartésien exact), 0 high/medium | S3 | oui | ne compter que les conflits sur même symbole | 0,5 j | Non |
| R7 | **Graphe de dépendances inopérant** | `orphans: 187` = toutes les features | S3 | oui | vérifier un cas connu : `Sentinel` → `IncidentManager` | 1 j | Non |
| R8 | **Aucun mécanisme de vérification de patch** | pas de « verification record » ; `code_lab/engine.py:728` a une boucle `VERIFY + REPAIR` locale au Code Lab seulement | S2 | oui | prototype lecture-seule (§7) | 2–4 j | Non, mais c'est le sujet de la direction A |
| R9 | **Dépendance LM Studio absente = chemins LLM non exerçables** | `:1234` connexion refusée | S2 | oui | démarrer LM Studio, rejouer `check_llm_backend` | 5 min | Bloque les démos B/D |
| R10 | **Quatre implémentations de « débat »** (`philosophical_council`, `core/debate`, `debate_lab`, `hermes-debate`) | 4 arborescences, 29 features catégorie `debate` | S2 | oui | documenter laquelle est canonique avant tout patch | 0,5 j (doc) | Risque de patcher la mauvaise |
| R11 | **CaptN Runtime sans test** | 0 fichier de test ne le cite | S3 | oui | au moins un test d'import + un test de routage | 1 j | Non |
| R12 | **Pas de test de non-régression sur le temps de démarrage** | la panne de cette session n'a été détectée par aucun test | S3 | oui | test : construire `LifeMeanStudioApp` doit prendre < 5 s | 30 min | Non |
| R13 | **Rapports Feature Pool dupliqués** (`.feature_pool_report.json` 2,6 Mo / `feature_pool_report.json` 2,7 Mo) | 2 fichiers à la racine | S4 | oui | garder la règle « le plus récent gagne » (déjà implémentée dans le pont) | — | Non |
| R14 | **Des tests dépendent d'un backend LLM vivant et échouent au lieu de `skip`** | `pytest tests/test_autopilot_llm_adapter.py` → `5 failed, 1 passed in 28.09s`, tous avec `error: 'No answer computed'` + log `Failed to fetch models: Connection error` (LM Studio `:1234` éteint) | S2 | oui | `pytest.skip` si `check_llm_backend()` KO, ou marqueur `@pytest.mark.requires_llm` | 0,5 j | Oui : interdit une « suite verte » reproductible |
| R15 | **16 tests pointent une UI inexistante** (`workspace.html/css/js`) | `FileNotFoundError: experiments\ui\workspace.html` ; `ls experiments/ui/` → seulement `dashboard.html`, `dashboard_combined.html` | S3 | oui | décider : créer les 3 fichiers **ou** marquer ces tests `xfail` avec motif | 0,5 j (décision) / 2–3 j (implémentation) | Non |
| R16 | **`code_lab/error_memory.py` ne mémorise rien** | `'fix_imports' in []`, `should_avoid_strategy(...) is False`, `get_stats() 0 == 2` (4 tests) | S2 | oui | rejouer `test_error_memory.py` et inspecter le store (chemin/écriture) | 1 j | Non, mais c'est une capacité annoncée qui ne fonctionne pas |
| R17 | **Contrat cassé : `KeyError: 'domain'`** | `tests/test_phase7_weakness.py:138` | S3 | oui | aligner schéma et test sur le format réellement produit | 0,5 j | Non |
| R18 | **Le dashboard a perdu l'alias `el`** | `re.search('const el = id => document.getElementById')` → `None` dans `dashboard.html` | S3 | oui | restaurer l'alias ou mettre à jour le test | 15 min | Non |
| R19 | **Test DELETE obsolète vs CSRF** | `assert 403 == 200` dans `test_qa_fixes.py:159` ; le POST/DELETE exige désormais `X-Lifemean-CSRF` | S4 | oui | envoyer l'en-tête dans le test | 15 min | Non |

**Rien de tout ceci n'est inventé** : chaque ligne renvoie à une sortie de commande citée au §1 ou reproduite ci-dessus.

---

## 6. ÉTAPE 3 — Feature Pool First : ce qu'il dit, et ce qu'il ne peut pas dire

### 6.1 Chiffres officiels du pool

```
total: 187   by_status: {VALIDATED: 138, READY: 49}
by_source: {legacy: 70, modern: 117}
with_tests: 138   ready_for_integration: 138
conflicts: 8190 (high 0, medium 0, low 8190)
orphans: 187
```

### 6.2 Recherche par domaine (découverte ≠ analyse ≠ validation)

| Domaine demandé | Hits | VALIDATED | READY | Constat |
|---|---|---|---|---|
| **Vérification des patchs** | 7 | 5 | 2 | `PatchGenerator` = READY (aucun test) ; `PatchValidator` = VALIDATED **mais** sa seule preuve est `legacy\...\tests\test_core_runtime.py`. Rien sur un *enregistrement de vérification* |
| **Permissions des agents** | **0** | 0 | 0 | Le pool ne voit **ni `PolicyGuard`, ni `ResourceGuard`, ni `ExperimentExecutionGate`**. « 0 hit » est un **artefact du scanner**, pas une preuve d'absence dans le code |
| **Validation et tests** | 14 | 13 | 1 | `EvidenceValidator` VALIDATED (`tests/test_evidence_layer.py`) — la seule preuve solide du lot |
| **Pipeline Inspector** | 5 | 4 | 1 | Les 5 hits sont des **crawlers legacy**. `pipeline_inspector/` (2773 lignes, 27 tests) est **totalement invisible** |
| **Sentinel** | 11 dont 9 par nom | 9 | 2 | `Sentinel`, `SentinelAction`, `SentinelConfig`… preuve = `tests/test_sentinel.py` (31 tests) → **solide**. `SentinelProvider` = READY |
| **Exploration scientifique** | 68 | 49 | 19 | Trop large : le mot-clé `debate` ramène des classes d'infrastructure |
| **Intégration de fonctionnalités** | 52 | 32 | 20 | `AgentRegistry`, `QuarantineManager`… statuts inutilisables (cf. 6.3) |

### 6.3 Quatre constats qui invalident un usage naïf

1. **Couverture 14,0 %** : 187 features pour **1335 classes** présentes dans les dossiers scannés. `scanner.py:89-92` contient une **liste de dossiers codée en dur** (`core`, `experiments`, `life_mean_studio`, `captn_runtime`, …) qui **omet `pipeline_inspector` et `feature_pool`** ; `_classify_feature` (l.129-173) n'enregistre ensuite que les classes dont le nom contient un mot-clé (`router`, `provider`, `safety`, `sentinel`, `debate`, `validator`, …) ou un suffixe (`engine`, `controller`, `manager`, `worker`, `agent`). **27 classes de sécurité/permissions** tombent dans le trou, dont `PolicyGuard`.
2. **VALIDATED ne veut pas dire « validé »** : 27 features sur 138 n'ont pour toute preuve qu'un fichier de test de `legacy/`, `historical/` ou `hermes-debate/`. Le mécanisme est une simple recherche de sous-chaîne du nom de la feature dans le contenu du fichier (`analyzer._find_tests`).
3. **Conflits = produit cartésien** : 8190 = 70 × 117. Le détecteur compare chaque legacy à chaque moderne ; aucun conflit high/medium. Chiffre sans valeur décisionnelle.
4. **`orphans: 187`** : le graphe de dépendances ne relie rien. `ready_for_integration: 138` repose donc sur un graphe vide.

### 6.4 Faut-il créer un nouvel explorateur ?

**Non.** Le pont existe déjà, dans le bon sens : `pipeline_inspector/feature_pool_bridge.py` lit le dernier rapport du pool (le plus récent par mtime), normalise les noms, et sépare explicitement **usage observé** et **statut de validation**. Ce qui manque n'est pas un explorateur, c'est :
- (a) la **couverture de découverte** du pool (R4) ;
- (b) une **page Studio** pour le Pipeline Inspector (0 page aujourd'hui) ;
- (c) une **preuve de validation** qui ne soit pas une sous-chaîne (R5).

---

## 7. Porte de vérification avant le patch suivant — faisabilité

**Aucune implémentation.** Ancrages existants, vérifiés :

| Ancrage | Ce qu'il fournit déjà | Manque |
|---|---|---|
| `pipeline_inspector/` | ingestion d'événements, corrélation, décisions de sécurité avec **niveau de certitude**, masquage des secrets, `EventStore` | aucun schéma « verification record » |
| `core/debate/experiment_gate.py` | statuts `PROPOSED / AWAITING_APPROVAL / RUNNING`, approbation | `_check_safety_guards` est un stub |
| `code_lab/engine.py:728` | boucle locale `VERIFY + REPAIR` avec `pytest` | non généralisée hors Code Lab |
| `code_lab/checkpoint.py` | notion de point de reprise | pas de lien patch ↔ diff ↔ tests |
| `git` | `git diff` = diff réel, `git stash` = retour arrière | non exploité par les agents |

Enregistrement proposé (schéma, non implémenté) : `patch_id`, `files_changed`, `diff`, `permissions_granted`, `commands_run[]`, `tests{cmd, exit, passed, failed}`, `static_analysis{ast_ok, ruff}`, `side_effects`, `rollback{sha|stash|tar}`, `status ∈ {VERIFIED, FAILED, INCOMPLETE, UNKNOWN, REQUIRES_APPROVAL}`.

Règle : tout statut ≠ `VERIFIED` **arrête** la continuation automatique. Effort estimé : **2–4 jours** (1 j schéma + collecte git, 1 j exécution tests ciblés, 1 j intégration Pipeline Inspector, 0,5–1 j tests). Dépendances : aucune nouvelle. Risque principal : **faux sentiment de sécurité** si les tests lancés ne couvrent pas les fichiers modifiés — à contrer par « tests choisis par fichier modifié, sinon `INCOMPLETE` ».

---

## 8. Notation des directions (estimations de planification, pas des mesures)

Critères notés 1–5 : **VU** valeur utilisateur, **IT** intérêt technique, **CA** compatibilité avec l'architecture existante, **FA** facilité (5 = peu d'effort), **TE** testabilité. Total /25.

| Direction | VU | IT | CA | FA | TE | **Total** | Justification courte |
|---|---|---|---|---|---|---|---|
| **A. Cadre de confiance** (patchs vérifiés, permissions, échec sûr) | 5 | 4 | 5 | 4 | 5 | **23** | Tout est déjà là mais débranché : `PolicyGuard` (179 l.) testé, gate à 1 stub près, `git diff` gratuit. Le plus gros gain par jour investi |
| **E. Environnement auto-améliorant** (Feature Pool, agents codeurs) | 5 | 4 | 4 | 3 | 4 | **20** | Dépend de R4/R5 : sans couverture, l'auto-amélioration pilote sur 14 % du code |
| **B. Laboratoire scientifique multi-agents** | 3 | 5 | 4 | 2 | 4 | **18** | Le moteur de débat existe (4 variantes), mais LM Studio hors ligne et aucune source scientifique branchée |
| **D. Plateforme sécurité Sentinel** | 3 | 4 | 3 | 2 | 3 | **15** | Déterministe solide (31 tests), mais le monitoring OS/réseau n'existe pas ; ne jamais promettre un antivirus |
| **C. Personal AI OS** | 4 | 2 | 2 | 1 | 2 | **11** | Aucun code (`Action Hub` absent) ; tout à construire, aucune fondation réutilisable |
| **F. Laboratoire d'exploration** (capteurs, bio) | 2 | 3 | 2 | 1 | 2 | **10** | Hors périmètre logiciel actuel ; rien à réutiliser, validation externe difficile |

---

## 9. Stratégie recommandée : **3 — double piste**, avec A comme piste de stabilisation

Justification fondée sur les preuves, pas sur une préférence :

1. `PolicyGuard` **existe et est testé** mais n'est appelé qu'une fois → la promesse « seuls les mécanismes de permission autorisent » n'est pas tenue dans le code (R2/R3). C'est le plus gros écart entre le discours et le réel.
2. `feature_pool/` et `pipeline_inspector/` **ne sont pas versionnés** (R1) : toute exploration qui les utilise risque de les perdre.
3. Le Feature Pool pilote des décisions sur **14 % du code** (R4) : « FEATURE POOL FIRST » n'est fiable qu'après son correctif de couverture.
4. Aucun gel de fonctionnalité n'est nécessaire : le cœur est stable (110 + 31 + 27 + 9 tests verts).

**Donc** : stabiliser A (R1→R5) **et** prototyper en isolation (E ou B) sans toucher au cœur, avec la porte du §7 comme condition d'intégration.

---

## 10. Trois feuilles de route

### CONSERVATRICE (fiabilité d'abord)
- **Jalon 1** : versionner `feature_pool/` + `pipeline_inspector/` et figer le **baseline de tests réel** : `29 failed, 1552 passed, 13 skipped` (R1).
- **Dépendances** : autorisation de commit.
- **Tests d'acceptation** : `git status` propre pour ces 2 paquets ; l'import depuis un autre cwd reste OK ; le baseline est **documenté** (29 échecs nommés) et non plus supposé « vert ».
- **Effort** : 1–2 h. **Risques** : quasi nul. **Conditions** : aucune.

### ÉQUILIBRÉE (recommandée)
- **Jalon 1** : CONSERVATRICE + rendre la suite **reproductible** : R14 (`skip` si LLM absent), R19/R18/R17 (15 min chacun), puis trancher R15 (workspace UI : créer ou `xfail`).
- **Jalon 2** : correction de couverture du Feature Pool (R4) + test de non-régression « démarrage < 5 s » (R12).
- **Jalon 3** (isolé) : prototype lecture-seule du *verification record* (§7), alimenté par Pipeline Inspector, **sans modifier le cœur**.
- **Dépendances** : R1 fait. **Tests d'acceptation** : `0 failed` hors tests marqués `requires_llm`/`xfail` motivés ; couverture ≥ 80 % des classes ; les 27 classes sécurité visibles ; démarrage < 5 s ; un patch volontairement cassé produit `FAILED` et arrête la chaîne.
- **Effort** : 4–6 j. **Risques** : élargir la découverte peut révéler beaucoup de BROKEN réels (à assumer, pas à masquer) ; R16 (`error_memory`) peut cacher une régression plus large dans `code_lab`. **Conditions** : accord explicite sur le périmètre du jalon 3.

### EXPLORATOIRE (apprentissage)
- **Jalon 1** : B ou D en isolation (paquet séparé, données réelles, pas d'intégration au Studio).
- **Dépendances** : LM Studio démarré (R9) pour B ; sources de logs OS pour D.
- **Tests d'acceptation** : reproduction d'un résultat connu ; séparation explicite mesure / hypothèse / spéculation.
- **Effort** : 1–2 semaines. **Risques** : dette qui s'ajoute à R2–R5 ; aucune garantie d'intégration ultérieure. **Conditions** : accepter que le cœur ne bouge pas pendant ce temps.

---

## 11. Questionnaire créateur

1. Qu'est-ce qui t'excite le plus à explorer ? (A / B / C / D / E / F, plusieurs possibles)
2. Qu'est-ce qui te frustre le plus aujourd'hui ? (démarrage, statuts faux, permissions non appliquées, LM Studio absent, autre)
3. Quelle capacité existante compte le plus à tes yeux ? (Studio, Pipeline Inspector, Feature Pool, Sentinel, débat)
4. Fiabilité ou expérimentation en priorité pour les 30 prochains jours ?
5. Que doit accomplir Life_mean dans 30 jours ?
6. Qu'est-ce qui doit rester expérimental (donc hors cœur) ?
7. Quels risques sont inacceptables ? (perte de code non versionné, action d'agent non autorisée, faux rapport de succès…)

---

## 12. Premier jalon proposé (à valider, non commencé)

**Jalon 0 — « Rendre le sol sûr » (2–3 h, aucun code de fonctionnalité)**
1. Commit des 8 fichiers modifiés + `feature_pool/` + `pipeline_inspector/` (sur autorisation).
2. Figer le baseline : `29 failed / 1552 passed / 13 skipped` consigné, avec la liste nominative des 29 (déjà au §1bis).
3. Décider du sort de R15 (workspace UI) : créer les 3 fichiers, ou `xfail(strict=False)` motivé.
4. `reports/` conservé comme trace locale (non versionné) ou ajouté au `.gitignore`.

Critère de sortie : `git status` ne montre plus de paquet fonctionnel non suivi ; le baseline est reproductible à l'identique deux fois de suite ; le Studio démarre en < 5 s.

---

**AWAITING CREATOR DECISION — NO IMPLEMENTATION AUTHORIZED.**
