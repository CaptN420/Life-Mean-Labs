# PERSONAL AI OS v1 — Découpage en phases exécutables

**But de ce document** : transformer le cahier des charges (19 phases) en **lots indépendants, vérifiables et réversibles**, exécutés un par un. Aucun lot ne démarre tant que le précédent n'a pas franchi sa porte de sortie. Aucun lot ne « termine » une phase en la déclarant opérationnelle sans preuve d'exécution réelle.

**Règles de conduite (rappel, non négociables)**
1. Lecture seule sur l'existant tant que le lot ne l'autorise pas explicitement.
2. Aucune suppression, aucun nettoyage destructif, aucune réécriture silencieuse.
3. Aucun faux succès : une capacité non vérifiée est marquée `PARTIAL` ou `UNAVAILABLE`, jamais `READY`.
4. Aucune modification d'un rapport existant : nouveau fichier daté.
5. Chaque lot laisse un point de retour arrière (commit dédié, pas de force-push).
6. Régression détectée ⇒ le lot est arrêté, pas « contourné ».

---

## Vue d'ensemble

| Lot | Phases couvertes | Livrable principal | Risque | État |
|---|---|---|---|---|
| **L0** | 1 | Inventaire des composants + carte de dépendances | nul (lecture) | à faire |
| **L1** | 0 | `PIPELINE_VALIDATION_REPORT_<date>.md` (re-validation) | nul (lecture) | à faire |
| **L2** | 2 + 7 (préférences) | Coquille Personal Hub dans Studio | UI | à faire |
| **L3** | 3 + 4 | Tâches + calendrier locaux, persistants | stockage | à faire |
| **L4** | 5 + 8 (+ début 15) | Quick AI + allocation des modèles | appels LLM | à faire |
| **L5** | 6 | Action Registry (handlers réels uniquement) | permissions | à faire |
| **L6** | 9 + 10 + 14 | Sentinel Control Center + AI Guard + politiques | sécurité interne | à faire |
| **L7** | 11 + 12 | Sentinel OS Guard lecture seule + alerte précoce | OS Windows | à faire |
| **L8** | 13 | Sentinel Network Guard lecture seule | réseau | à faire |
| **L9** | 16 + 17 + 18 + 19 | Vue d'état, télémétrie, tests globaux, rapports | intégration | à faire |

**Dépendances** : `L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7 → L8 → L9`.
Seule exception : **L5 (Action Registry)** peut démarrer en parallèle de **L3**, car il ne dépend que de L2 (coquille UI) et de L0 (inventaire des handlers).

---

## L0 — Inventaire et carte des dépendances *(Phase 1)*

**Objectif** : savoir ce qui existe réellement avant de toucher à quoi que ce soit.

- Inventorier : Studio, Feature Pool, Pipeline Inspector, Agent Manager, Workflow Manager, Model Router, Provider Factory, CaptN-BRAIN, Sentinel, Safety Gate, Event Bus, Télémétrie, stockage local, services Windows accessibles.
- Classer chaque composant : `OPERATIONAL` / `PARTIAL` / `UNAVAILABLE` / `LEGACY_UNVALIDATED` / `PLANNED`.
- Carte des dépendances réelles (imports vérifiés, pas supposés).

**Interdit dans ce lot** : créer un lien entre deux composants sous prétexte qu'il « devrait » exister.

**Preuve attendue** : chaque classification justifiée par un fichier + une commande exécutée.

**Livrable** : `PERSONAL_AI_OS_ARCHITECTURE_<date>.md` (partie inventaire).

**Porte de sortie** : aucun composant classé `OPERATIONAL` sans import réussi **et** route/handler identifié.

---

## L1 — Re-validation du Pipeline Inspector *(Phase 0)*

**Contexte** : `PIPELINE_VALIDATION_REPORT.md` existe déjà (2026-11-01, verdict `PARTIAL`, 3 défauts corrigés, 4 limites documentées). Interdiction de l'écraser — on produit un **nouveau** rapport daté.

**À vérifier** (A→L du cahier des charges) :

| Point | Méthode | Critère |
|---|---|---|
| A. Imports / compilation | `py_compile` sur les 15 modules + dashboard | 0 échec |
| B. Doublons / blocs morts | analyse AST des définitions | aucun doublon |
| C. Ingestion incrémentale | exécution réelle sur logs réels | pas de doublon, idempotent |
| D. Déduplication SQLite | rejeu du même lot d'événements | comptage stable |
| E. Masquage des secrets | échantillons piégés | 0 secret en clair |
| F/G. Corrélations | explicite / probable / inconnu | aucune corrélation « certaine » sans preuve |
| H. Décisions de sécurité | rejeu de logs DENY/ALLOW | classification exacte |
| I. Routes HTTP | appels réels | codes attendus |
| J. Affichage Studio | inspection de l'onglet | données réelles, pas de placeholder |
| K. Tests | `pytest pipeline_inspector/tests` | verts |
| L. Feature Pool | lecture de l'état | une feature découverte ≠ `READY` |

**Livrable** : `PIPELINE_VALIDATION_REPORT_<date>.md` + corrections confirmées (avec tests de non-régression), ou blocages documentés.

**Porte de sortie** : verdict explicite `OK` / `PARTIAL` / `BLOCKED` par point, preuves incluses.

---

## L2 — Coquille du Personal Hub *(Phases 2 + 7 préférences)*

**Périmètre** : uniquement le conteneur visuel. Aucun service métier à l'intérieur.

- Widget flottant repliable, coin inférieur droit, non bloquant pour la navigation.
- Six sections navigables : TODAY, CALENDAR, QUICK AI, ACTIONS, SENTINEL, SETTINGS.
- Chaque section affiche `UNAVAILABLE — <lot requis>` tant que son lot n'est pas livré.
- Préférences persistées (position, état replié, section d'accueil, densité, raccourcis visibles).
- Respect du framework UI et des styles existants.

**Interdit** : afficher une donnée inventée pour « remplir » une section.

**Tests** : montage/démontage du widget, persistance des préférences après rechargement, non-régression des onglets Studio existants.

**Porte de sortie** : le Hub s'ouvre, se replie, restaure ses préférences, et aucune régression sur les parcours scientifiques existants.

---

## L3 — Services personnels : tâches + calendrier *(Phases 3 + 4)*

- CRUD tâches : priorité, échéance, catégorie, notes, récurrence, historique, vue du jour.
- Calendrier local : événements, rappels, vues jour/semaine/mois, recherche.
- Stockage local persistant (schéma versionné, migration compatible).
- **Séparation stricte** : une tâche personnelle ne déclenche **jamais** une commande système.
- Association tâche/événement → workflow **uniquement explicite**, via l'Action Registry (L5). Avant L5 : le champ existe, il est inerte et affiché comme tel.
- Interfaces de connexion calendrier externe : déclarées, désactivées par défaut, aucun appel réseau.

**Tests** : persistance après redémarrage, récurrence, recherche, absence de déclenchement implicite (test négatif explicite).

**Porte de sortie** : créer une tâche avec échéance → redémarrer → la tâche est là, et **rien** n'a été exécuté.

---

## L4 — Quick AI + allocation des modèles *(Phases 5 + 8, amorce 15)*

- Réutiliser le Model Router / Provider Factory existants (aucun client LLM parallèle).
- Affichage obligatoire par réponse : nom **réel** du modèle, fournisseur, mode local/distant, état de connexion, erreur éventuelle.
- Panneau d'allocation : Quick AI, Coding, Planning, Analysis, Validation, Security Reviewer, Log Analysis, Research.
- Politique de fallback visible ; **aucun changement silencieux** du modèle d'un rôle sensible.
- Défaillance du Security Reviewer ⇒ **pas** d'autorisation automatique (elle bloque).
- Recherche web : uniquement si un connecteur réel est configuré ; sinon la capacité est déclarée `UNAVAILABLE`.
- Les réponses ne deviennent jamais des commandes exécutables.

**Tests** : backend absent ⇒ message explicite (pas de réponse simulée) ; sélection de modèle reflétée dans le manifeste d'appel ; fallback tracé.

**Porte de sortie** : une question posée avec un backend réellement disponible affiche le modèle réellement utilisé ; avec un backend coupé, elle échoue **explicitement**.

---

## L5 — Action Registry *(Phase 6)*

- Registre distinct du Feature Pool (capacités techniques ≠ opérations déclenchables).
- Chaque action : id stable, nom, description, icône, catégorie, **handler existant vérifié**, dépendances, paramètres, permissions, disponibilité, niveau de risque, confirmation requise.
- Une action dont le handler n'est pas résolu est listée `UNAVAILABLE`, jamais cliquable.
- Toute action sensible exige une confirmation explicite (pas de « tout autoriser »).
- Les événements d'exécution d'action vont au Pipeline Inspector (L6/L9 pour le branchement).

**Tests** : résolution de handler pour chaque action déclarée (test paramétré), refus si permission absente, journalisation de chaque déclenchement.

**Porte de sortie** : 0 action affichée `READY` sans handler résolu par un test.

---

## L6 — Sentinel Control Center + AI Guard + politiques *(Phases 9 + 10 + 14)*

**Base existante à auditer d'abord** : `core/safety/sentinel.py`, `sentinel_alert.py`, `sentinel_controller.py`, routes `/api/sentinel/*`, `tests/test_sentinel.py`. **Ne pas recréer.**

- Trois domaines : AI GUARD, OS GUARD, NETWORK GUARD — chacun affiche configuré / réel / dernière activité / dernière erreur / sources / couverture / permissions / alertes récentes.
- États distincts : `ENABLED` ≠ `RUNNING` ≠ `HEALTHY` ≠ `DEGRADED` ≠ `STOPPED` ≠ `UNAVAILABLE` ≠ `ERROR`. Un interrupteur ON n'est **pas** une preuve de protection.
- AI Guard : agents, appels d'outils, écritures fichiers, commandes demandées, décisions DENY, erreurs, changements de config → événements typés vers Pipeline Inspector.
- Une simple corrélation temporelle ne conclut **jamais** à une violation ; niveau de confiance obligatoire.
- Politiques LIGHT / BALANCED / STRICT / CUSTOM, validées et persistantes ; une politique ne peut pas désactiver les contrôles obligatoires des agents.
- Sentinel désactivé ⇒ les Safety Gate des agents restent actifs (test explicite).

**Porte de sortie** : chaque état affiché est dérivé d'une observation horodatée, et éteindre Sentinel ne désactive aucun contrôle obligatoire.

---

## L7 — Sentinel OS Guard lecture seule + alerte précoce *(Phases 11 + 12)*

**Contrainte absolue** : lecture seule. Pas de pilote noyau, pas d'admin par défaut, pas de kill de processus, pas de suppression/déplacement/chiffrement, pas de lecture de contenu quand les métadonnées suffisent.

- État observable de Defender, du pare-feu, des services de sécurité ; alertes Windows accessibles.
- Surveillance de dossiers **explicitement autorisés** ; détection de rafales de modifications.
- Signaux de rançongiciel : multi-signaux obligatoires avant élévation de sévérité.
- Sévérités : `INFORMATIONAL` / `LOW` / `MEDIUM` / `HIGH` / `CRITICAL`.
- Chaque alerte : horodatage, source, indicateurs, confiance, gravité, **limites de la détection**, actions recommandées.
- Jamais « ransomware détecté » sans preuve ; jamais « ordinateur protégé » parce que Sentinel tourne.
- Zones non surveillées affichées explicitement.

**Tests** : uniquement des événements synthétiques ou des fichiers inoffensifs en répertoire temporaire isolé. Aucune simulation destructive.

**Porte de sortie** : les collecteurs n'écrivent rien hors de leur propre cache, et une permission manquante produit `UNAVAILABLE` + raison, pas une erreur silencieuse.

---

## L8 — Sentinel Network Guard lecture seule *(Phase 13)*

- Inventaire des services locaux autorisés, ports en écoute, changements d'état, endpoints des modèles IA locaux.
- Détection d'écart par rapport à une base de référence (baseline explicite, pas d'heuristique cachée).
- Interdits : interception de contenu, proxy transparent, scan d'autres machines, modification de règles de pare-feu, blocage automatique.

**Porte de sortie** : l'inventaire est reproductible (deux exécutions ⇒ même liste, hors changements réels), et aucun paquet n'est émis vers l'extérieur.

---

## L9 — Intégration, télémétrie, tests globaux, rapports *(Phases 16 → 19)*

- Vue d'état centralisée avec provenance : `OBSERVED` / `INFERRED` / `UNKNOWN` / `STALE`, source + date par ligne.
- Aucune alerte ≠ absence de menace (mention explicite dans l'UI).
- Événements typés pour Hub, Action Registry, Model Allocation, trois Guards, alertes, santé des services ; **pas de double enregistrement**.
- Séparation conservée : observé / corrélé / interprété / décidé / exécuté.
- Suite de tests 1→19 du cahier des charges, y compris non-régression Pipeline Inspector / Feature Pool / Studio.
- Rapports (jamais d'écrasement silencieux) : `PERSONAL_HUB_IMPLEMENTATION`, `ACTION_REGISTRY`, `MODEL_ALLOCATION`, `SENTINEL_ARCHITECTURE`, `SENTINEL_AI_GUARD`, `SENTINEL_OS_GUARD`, `SENTINEL_NETWORK_GUARD`, `SENTINEL_SECURITY_COVERAGE`, `RANSOMWARE_EARLY_WARNING`, `TEST_RESULTS`, `IMPLEMENTATION_STATUS`, `NEXT_STEPS`.

**Porte de sortie** : `IMPLEMENTATION_STATUS.md` liste chaque critère d'acceptation en `DONE` / `PARTIAL` / `BLOCKED` **avec la preuve** (commande + sortie), et le noyau scientifique reste vert.

---

## Portes de non-régression (à chaque lot)

Avant de clôturer un lot, obligatoire :

```bash
.venv/Scripts/python -m pytest tests/ -q                    # noyau scientifique
.venv/Scripts/python -m pytest pipeline_inspector/tests -q  # inspector
```

Plus, selon le lot : dashboard HTTP smoke, tests Studio, tests Sentinel.

Seuil : **0 échec nouveau**. Un échec préexistant documenté reste documenté, jamais masqué.

---

## Ce que ce plan refuse de faire

- Terminer les 19 phases en une passe « pour faire bonne figure ».
- Déclarer `OPERATIONAL` un composant qui n'a pas été importé et exercé.
- Remplacer une implémentation fonctionnelle par une version simplifiée.
- Modifier un format de package, d'expérience ou de dataset sans migration testée.
- Toucher à Windows (services, Defender, pare-feu, processus) autrement qu'en lecture.
- Présenter une émulation comme une exécution réelle.
