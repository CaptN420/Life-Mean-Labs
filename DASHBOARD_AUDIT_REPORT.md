# Audit Dashboard Life_mean — Vue d'ensemble

## 1. Architecture des dashboards

### Fichiers identifiés
| Fichier | Lignes | Rôle | Statut |
|---------|--------|------|--------|
| `experiments/ui/dashboard.html` | 4986 | Dashboard principal (actif) | ✅ Canonical |
| `ui/dashboard.html` | 4421 | Ancien dashboard (backup) | ⚠️ Obsolète |
| `experiments/dashboard.py` | 1047 | Serveur HTTP + API | ✅ Actif |
| `experiments/ui_controller.py` | 690 | Contrôleur UI | ✅ Actif |

### Onglets présents (dashboard actif)
1. **Autopilot** — Création et exécution d'expériences déterministes/débat
2. **Experiments** — Vue gérée des expériences (mode switching, restart, continue)
3. **Debate** — Laboratoire de débat multi-agents
4. **Code Lab** — Exécution de code avec templates de rôles
5. **Settings** — Configuration lue-seule + valeurs éditables
6. **Compare** — Comparaison d'expériences (browser, inspector, tray)
7. **Cluster Tree** — Arbre des sujets + explorateur de runs
8. **Experimental** — Sandbox expérimental (harness, feedback)
9. **Workspace** — Interface programmable (éditeur, workflow, console)
10. **Skills & Tools** — Couche d'extension modulaire (skills, tools, pipeline)

---

## 2. Bugs identifiés

### BUG P0 — `ReferenceError: el is not defined` (CORRIGÉ)
- **Fichier :** `experiments/ui/dashboard.html` ligne 4515 (avant correctif)
- **Cause :** `el` défini localement dans `loadCapabilities()` mais appelé dans `loadSkills()`, `loadTools()`, `loadPipeline()`
- **Correctif :** Déplacé `const el = id => document.getElementById(id)` au scope module (ligne 4498)
- **Tests :** 78 passed, 0 failed

### BUG P1 — Dashboard obsolète non synchronisé
- **Fichier :** `ui/dashboard.html` (ancien)
- **Problème :** Manque l'onglet "Experiments", les panneaux d'observabilité, et les fonctions JS récentes
- **Impact :** Si ce fichier est servi à la place, interface incomplète
- **Recommandation :** Supprimer ou marquer comme backup

---

## 3. Fonctionnalités manquantes / À implémenter

### Phase 1 — Stabilisation (Priorité haute)
| # | Élément | État | Action |
|---|---------|------|--------|
| 1.1 | Sync `ui/dashboard.html` vers canonical | ❌ | Supprimer ou marquer comme obsolète |
| 1.2 | Tests end-to-end des onglets | ❌ | Créer `tests/test_dashboard_ui.py` |
| 1.3 | Gestion d'erreurs API manquante | ⚠️ | Ajouter try/catch explicite sur tous les fetch |
| 1.4 | Validation formulaires | ⚠️ | Ajouter attributs `required` et messages d'erreur |

### Phase 2 — Features manquantes (Priorité moyenne)
| # | Élément | État | Action |
|---|---------|------|--------|
| 2.1 | Recherche dans Compare | ⚠️ | Implémenter filtre temps réel |
| 2.2 | Export manifeste expérience | ✅ | Déjà implémenté (`exportManifest`) |
| 2.3 | Replay configuration | ✅ | Déjà implémenté (`replayExperiment`) |
| 2.4 | Indicateur temps réel observabilité | ⚠️ | Polling 3s ok mais pas de feedback visuel |
| 2.5 | Historique prompts expérimentaux | ❌ | Non implémenté |

### Phase 3 — Améliorations UX (Priorité basse)
| # | Élément | État | Action |
|---|---------|------|--------|
| 3.1 | Thème sombre/clair toggle | ❌ | Ajouter toggle dans Settings |
| 3.2 | Notifications toast | ❌ | Système de notifications non intrusives |
| 3.3 | Sauvegarde locale config | ❌ | localStorage pour préférences |
| 3.4 | Documentation inline | ❌ | Tooltips et help text manquants |

---

## 4. Plan d'exécution

### Phase 1 — Stabilisation (à exécuter)
```
1. Supprimer ui/dashboard.html (backup)
2. Créer tests UI end-to-end
3. Ajouter validation formulaires
4. Vérifier gestion erreurs API
```

### Phase 2 — Features (à exécuter)
```
1. Améliorer recherche Compare
2. Ajouter feedback visuel observabilité
3. Implémenter historique prompts
```

### Phase 3 — UX (facultatif)
```
1. Thème sombre/clair
2. Notifications toast
3. Sauvegarde locale
4. Documentation inline
```

---

## 5. Points d'entrée API vérifiés

| Endpoint | Méthode | Status | Notes |
|----------|---------|--------|-------|
| `/api/experiments` | GET/POST | ✅ | CRUD expériences |
| `/api/experiments/{id}/start` | POST | ✅ | Démarrer |
| `/api/experiments/{id}/stop` | POST | ✅ | Arrêter |
| `/api/experiments/{id}/mode` | POST | ✅ | Changer mode |
| `/api/experiments/{id}/restart` | POST | ✅ | Redémarrer |
| `/api/experiments/{id}/continue` | POST | ✅ | Continuer |
| `/api/experiments/{id}/observability` | GET | ✅ | Données observabilité |
| `/api/experiments/{id}/manifest` | GET | ✅ | Export manifeste |
| `/api/extensions/skills` | GET/POST | ✅ | Liste/Créer skills |
| `/api/extensions/tools` | GET/POST | ✅ | Liste/Créer tools |
| `/api/extensions/capabilities` | GET | ✅ | Besoins détectés |
| `/api/extensions/pipeline` | GET | ✅ | Pipeline approbation |
| `/api/code-lab/runs` | GET/POST | ✅ | Runs Code Lab |
| `/api/debate/runs` | GET/POST | ✅ | Runs Debate |
| `/api/settings` | GET/PUT | ✅ | Configuration |
| `/api/compare/*` | GET/POST | ✅ | Comparaison |
| `/api/cluster/*` | GET | ✅ | Arbre + graphe |
| `/api/sentinel/*` | GET/POST | ✅ | Surveillance sécurité |

---

## 6. Tests à exécuter

### Tests existants
- `test_dashboard_http_smoke.py` — 6 passed ✅
- `test_phase7_autopilot.py` — 8 passed ✅
- `test_phase0_config.py` — 13 passed ✅
- `test_sentinel.py` — 31 passed ✅
- `test_observability.py` — 20 passed ✅

### Tests à créer
- `tests/test_dashboard_ui.py` — Navigation onglets, rendu vides/pleins
- `tests/test_experiments_tab.py` — Mode switching, restart, continue
- `tests/test_skills_tools_tab.py` — Skills, tools, pipeline affichage

---

## 7. Résumé exécution

### Ce qui doit être fait (priorité)
1. **Supprimer** `ui/dashboard.html` (backup obsolète)
2. **Créer** `tests/test_dashboard_ui.py` pour validation UI
3. **Améliorer** recherche Compare avec filtre temps réel
4. **Ajouter** feedback visuel polling observabilité
5. **Implémenter** historique prompts expérimentaux

### Ce qui est déjà fonctionnel
- ✅ Autopilot deterministe/debate mode switching
- ✅ Observability live (agents, transcript, traces, progress)
- ✅ Skills & Tools pipeline d'approbation
- ✅ Compare browser/inspector/tray
- ✅ Cluster Tree + Graph
- ✅ Workspace programmable
- ✅ Sentinel sécurité
- ✅ Export/Replay expériences
