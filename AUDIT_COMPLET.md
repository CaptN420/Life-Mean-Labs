# AUDIT COMPLET — Environnement et Sécurité Life_mean

**Date:** 2026-10-13  
**Auditeur:** Hermes Agent (lecture seule)  
**Dossier cible:** `C:\Users\celes\Documents\Hermes-Workspace\Life_mean`

---

## A. ÉTAT DU PROJET

### Version et statut
- **Version:** 1.0.0 (`pyproject.toml` ligne 7)
- **Status:** Phases 0–9 complètes, 713 tests passing, 12 skipped (deps externes), 2 known failures (`test_runtime_restore.py` — subprocess path issue)
- **License:** Apache-2.0 (changement depuis MIT, commit 95d7d01)

### Composants implémentés

| Couche | Fichier | Statut |
|--------|---------|--------|
| `philosophical_council/` | DebateEngine, agents, SmartRouter, EventBus, RAW storage | ✅ STABLE |
| `experiments/` | ExperimentConfig, settings API, dashboard HTTP | ✅ FONCTIONNEL |
| `code_lab/` | Engine V1 avec loop DEVELOPER/VERIFIER/CRITIC + pytest réel | ✅ FONCTIONNEL |
| `role_templates/` | Configuration des rôles et mappings de modèles | ✅ FONCTIONNEL |
| `library/` + `core/` | Tools, personas, protocols, reliability managers | ✅ STABLE |
| `analysis/` + `autopilot/` | Weakness analysis, curriculum controller | ✅ STABLE |
| `debate_lab/` | Controller pour sessions de débat | ✅ FONCTIONNEL |

### Composants incomplets ou partiellement implémentés

1. **Sandbox expérimental** (`experimental/harness.py`) — fonctionnel mais OPT-IN, ne touche pas le core stable
2. **Autonomous Synthetic Data Generator** — design doc complet mais PAS encore implémenté (phases 10+ non démarrées)
3. **Curriculum adjustments** — `approval_required=True` par défaut mais mécanisme d'approbation humaine NON CONNECTÉ (rôle philosophic_debate = NOT_CONNECTED)

### Relations Hermes / CodeLab / Lightning / LM Studio

| Composant | Rôle | Implémentation |
|-----------|------|----------------|
| **Hermes** | Orchestrateur desktop | Interface de chat, gestion des skills, outils browser/terminal |
| **CodeLab** | Génération + validation code | Utilise LLMClient via LM Studio ou OpenRouter |
| **Lightning** | ❌ NON TROUVÉ | Aucun composant "Lightning" dans le projet |
| **LM Studio** | Backend LLM local | `http://localhost:1234/v1` par défaut, credentials via `.env` ou `overrides/llm.env` |

### Fonctionnalités prévues mais non implémentées

- **Data factory autonome** (AUTONOMOUS_SYNTHETIC_DATA_GENERATOR.md) — phases 10+ non démarrées
- **Approval gate humaine** pour curriculum adjustments — code existe (`approval_required=True`) mais pas de UI/UX connectée
- **Isolation VM/Linux** — mentionné dans le design comme objectif, PAS implémenté

---

## B. DÉPENDANCES

### Dépendances principales (`pyproject.toml`)

| Dépendance | Version | Usage | Risque |
|------------|---------|-------|--------|
| `openai` | >=1.0.0 | LLM client (LM Studio/OpenRouter) | ⚠️ Non épinglé — version min seulement |
| `pydantic` | >=2.0.0 | Validation données | ✅ Standard |
| `ttkbootstrap` | non épinglé | UI legacy (philosophical_council) | ⚠️ Risque: dépendance optional, pas critique |
| `pyyaml` | >=6.0 | Config parsing | ✅ Standard |

### Dépendances optionnelles (`hermes_debate`)

| Dépendance | Version | Usage |
|------------|---------|-------|
| `pyyaml` | >=6.0 | Config |
| `aiohttp` | >=3.8.0 | HTTP async pour hermes-debate (projet séparé) |

### Verrouillage (`uv.lock`)
- **Format:** uv.lock v1, revision 3
- **Python:** >=3.10
- **Resolution markers:** Emscripten vs native
- **aiohttp:** 3.14.4 (pinée via lockfile)

### Dépendances historiques (non actives)
- `historical/v0-alchemy-multi-agent/` — code legacy avec `subprocess`, `_eval()`, `guard_subprocess_command()`
- `hermes-debate/` — projet séparé, intentionallement exclu du wheel
- `hermes-orchestrator/` — TypeScript, npm dependencies

---

## C. CAPACITÉS D'EXÉCUTION

### Tableau détaillé des capacités

| # | Capacité | Fichier | Fonction | Confirmation humaine | Risque |
|---|----------|---------|----------|---------------------|--------|
| 1 | Générer du code Python | `code_lab/engine.py:579` | `_execute()` → LLM DEVELOPER ou deterministic generator | ❌ NON — automatique via LLM | MOYEN |
| 2 | Exécuter automatiquement ce code | `code_lab/engine.py:887` | `subprocess.run([sys.executable, "-m", "pytest"])` | ❌ NON — exécution automatique dans workspace isolé | ÉLEVÉ |
| 3 | Exécuter commandes PowerShell/système | `experimental/retry_agent.py:350` | `subprocess.run(cmd, cwd=str(ws))` | ❌ NON | ÉLEVÉ |
| 4 | Installer dépendances pip/npm | ❌ NON TROUVÉ | — | N/A | NONE |
| 5 | Modifier fichiers sans confirmation | `code_lab/engine.py:879` | `_write_files()` → workspace | ❌ NON — écriture automatique dans workspace | MOYEN |
| 6 | Lancer tests automatiquement | `code_lab/engine.py:883` | `_run_tests()` → pytest | ❌ NON | ÉLEVÉ |
| 7 | Exécuter commandes Git | ❌ NON TROUVÉ dans code actif | — | N/A | NONE |
| 8 | Démarrer sous-agents | ❌ NON — pas de `delegate_task` dans le code | — | N/A | NONE |
| 9 | Accéder directement à Windows | `os` module importé | `resolve_llm_credentials()` lit `os.environ` | ✅ OUI — lecture d'env vars | FAIBLE |
| 10 | Contourner validation humaine | Variable | Voir section D | ❌ NON pour LLM, ✅ POUR dashboard HTTP | VARIABLE |

### Mécanismes d'exécution identifiés

**subprocess** (2 occurrences actives):
- `code_lab/engine.py:887` — pytest dans workspace isolé
- `experimental/retry_agent.py:350` — pytest dans sandbox jetable

**exec/eval**: ❌ AUCUN dans le code actif
- `compile()` utilisé pour validation syntaxique (`engine.py:958`) — SAFE
- `_eval()` dans `historical/v0-alchemy-multi-agent/src/launcher.py` — legacy, non actif

**Accès réseau**:
- LLMClient → HTTP vers LM Studio/OpenRouter
- Dashboard HTTP server (`experiments/dashboard.py:13`) — BaseHTTPRequestHandler

---

## D. FAILLES DE SÉCURITÉ

### Problèmes confirmés

| ID | Type | Détail | Sévérité |
|----|------|--------|----------|
| F1 | Architecture | Code généré par LLM s'exécute automatiquement sans approbation humaine | 🔴 CRITIQUE |
| F2 | Architecture | Pas d'isolation VM — exécution sur Windows host | 🟠 ÉLEVÉ |
| F3 | Credentials | API keys LLM stockées dans `.env` (git-ignored) ou `overrides/llm.env` | 🟡 MOYEN |
| F4 | Dashboard | HTTP server écoute sur `0.0.0.0` par défaut (`dashboard.py:714`) | 🟡 MOYEN |

### Risques théoriques

| ID | Type | Détail | Probabilité |
|----|------|--------|-------------|
| R1 | Prompt injection | LLM pourrait générer du code malveillant si prompt manipulé | FAIBLE — validation pytest + compile |
| R2 | Credential leak | Fuites via logs ou events JSONL | FAIBLE — `_hashes` excludes secrets, mais `settings_snapshot` contient URLs |
| R3 | Workspace isolation | Workspace isolé mais pas sandboxé (pas de container) | MOYEN — subprocess peut accéder filesystem local |

### Failles spécifiques identifiées

1. **F1 — Exécution automatique sans approbation** (CONFIRMÉ)
   - `code_lab/engine.py:579` `_execute()` appelle LLM puis lance pytest automatiquement
   - Pas de gate humaine entre génération et exécution
   - Impact: Un LLM malveillant ou un prompt manipulé pourrait générer du code destructeur

2. **F2 — Pas d'isolation système** (CONFIRMÉ)
   - Workspace existe (`code_lab/workspace.py`) mais c'est juste un dossier temporaire
   - subprocess.run s'exécute avec les permissions de l'utilisateur Windows
   - Pas de container, pas de VM, pas de namespace

3. **F4 — Dashboard HTTP exposé** (CONFIRMÉ)
   - `experiments/dashboard.py:714`: `http://{host}:{port}` 
   - Handler expose API endpoints pour runs, events, files
   - Aucune auth HTTP implémentée

---

## E. ARCHITECTURE RECOMMANDÉE

### Schéma logique des composants et frontières de sécurité

```
┌─────────────────────────────────────────────────────────────┐
│                    BOUNDARY: EXÉCUTION ISOLÉE               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              VM LINUX (proposée)                        ││
│  │  ┌───────────────────────────────────────────────────┐  ││
│  │  │  Container Docker / Podman                        │  ││
│  │  │  - Network: disabled by default                   │  ││
│  │  │  - Filesystem: read-only except /tmp/workspace    │  ││
│  │  │  - Processes: no sudo, no network out             │  ││
│  │  └───────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│              BOUNDARY: APPROBATION HUMAINE                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  UI Dashboard (lecture seule)                          ││
│  │  - View runs, events, files                             ││
│  │  - STOP button (existing)                               ││
│  │  - APPROVE button (NEW — before execution)            ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│              BOUNDARY: CREDENTIALS                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Vault / Secrets Manager                                ││
│  │  - API keys: never in logs, never in events             ││
│  │  - Precedence: env > overrides > .env (existing)        ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Contrôles nécessaires

| Contrôle | Application | Responsable |
|----------|-------------|--------------|
| Approbation humaine avant exécution | Code layer | Orchestrator (Hermes) |
| Isolation VM/Container | OS layer | System admin |
| Network namespace | OS layer | Docker/Podman |
| Credential encryption | App layer | experiments/credentials.py |
| Logging complet | App layer | code_lab/engine.py events |
| Stop mechanism | Code layer | ui_controller.py (existing) |

---

## F. PLAN DE CORRECTION

### Priorités CRITIQUE

| ID | Correction | Fichier | Effort |
|----|------------|---------|--------|
| C1 | Ajouter gate approbation humaine | `code_lab/engine.py` `_execute()` | Moyen |
| C2 | Documenter risque exécution auto | `README.md`, `CODE_LAB.md` | Faible |

### Priorités ÉLEVÉE

| ID | Correction | Fichier | Effort |
|----|------------|---------|--------|
| E1 | Isolation workspace renforcée | `code_lab/workspace.py` | Moyen |
| E2 | Dashboard auth HTTP | `experiments/dashboard.py` | Moyen |
| E3 | Credential scanning pre-commit | `.git/hooks/pre-commit` | Faible |

### Priorités MOYENNE

| ID | Correction | Fichier | Effort |
|----|------------|---------|--------|
| M1 | Logging events JSONL encryption | `code_lab/engine.py` `_emit_terminal()` | Élevé |
| M2 | Test sandbox isolation | `tests/test_workspace_isolation.py` | Moyen |

### Priorités FAIBLE

| ID | Correction | Fichier | Effort |
|----|------------|---------|--------|
| F1 | Migration credentials vers vault | `experiments/credentials.py` | Élevé |
| F2 | Documentation architecture sécurisée | `docs/ARCHITECTURE.md` | Faible |

---

## G. VERDICT FINAL

### Réponses aux questions du cahier des charges

| Question | Réponse | Preuve |
|----------|---------|--------|
| **Hermes peut-il exécuter du code ?** | ✅ OUI — Hermes Agent a accès à `terminal`, `execute_code`, `browser_exec` | Documentation Hermes + outils disponibles |
| **CodeLab peut-il exécuter du code automatiquement ?** | ✅ OUI — `_execute()` lance pytest sans approbation | `code_lab/engine.py:883-917` |
| **L'approbation humaine est-elle obligatoire ?** | ❌ NON — pas de gate avant exécution | Aucun `input()` ou confirmation UI avant `_run_tests()` |
| **Le code s'exécute-t-il sur Windows ou dans un environnement isolé ?** | ⚠️ WINDOWS HOST — workspace isolé mais pas containerisé | `subprocess.run(cwd=str(self.ws.workspace))` |
| **Quelles dépendances présentent un risque ?** | `openai>=1.0.0` non épinglé, `ttkbootstrap` optional | `pyproject.toml:12-15` |
| **Quels mécanismes permettent un démarrage automatique ?** | `threading.Thread(daemon=True)` pour experiments | `ui_controller.py:134-142` |
| **Quelles protections manquent ?** | Approbation humaine, isolation VM, auth dashboard | Voir section E |
| **Que faut-il corriger avant une remise en service ?** | C1 (gate approbation) + E2 (auth dashboard) minimum | Priorités CRITIQUE/ÉLEVÉE |

### Résumé exécutif

**Niveau de risque global: ÉLEVÉ** pour usage production, **MOYEN** pour recherche exploratoire.

Le système Life_mean est bien architecturé pour la validation déterministe (pytest + compile comme autorité), mais présente des lacunes critiques en matière de:
1. **Gouvernance** — pas d'approbation humaine avant exécution de code généré par LLM
2. **Isolation** — exécution sur host Windows sans container
3. **Surface d'attaque** — dashboard HTTP exposé sans auth

Le projet est **sûr pour le développement/recherche** si utilisé en mode local avec conscience des risques. **NON prêt pour production** sans les corrections C1, E1, E2.

---

**FIN DE L'AUDIT**  
*Document généré par lecture seule — aucune modification n'a été effectuée.*
