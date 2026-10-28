# LIFE_MEAN LAB V2 — RAPPORT D'AUDIT COMPLET

**Date :** 2026-10-27  
**Statut :** Audit architectural pré-migration V2  
**Confidentialité :** Interne — Ne pas diffuser

---

## 0. RÉSUMÉ EXÉCUTIF

Life_mean Lab V1 est une architecture multi-agents fonctionnelle mais présentant des limitations architecturales identifiées. Cet audit couvre :

- **Architecture actuelle** : 6 laboratoires (Code Lab, Debate Lab, Experimental, Autopilot, Compare, Life Mean Studio)
- **Problèmes identifiés** : 3 P0 (résolus), 3 YELLOW (non bloquants), 1 limitation structurelle majeure
- **Recommandations V2** : Reset logique, séparation des domaines, fiabilité accrue des agents

---

## 1. INVENTAIRE COMPLET DE L'ARCHITECTURE ACTUELLE

### 1.1 Couche Stable Core

| Composant | Statut | Notes |
|-----------|--------|-------|
| EventBus | ✅ Opérationnel | 3 instances privées, non publié via dashboard |
| SmartRouter | ✅ Opérationnel | Méthodes: context_aware, round_robin, weighted, random |
| LLMClient | ✅ Opérationnel | Backend Ollama/LiteLLM configuré |
| Settings | ✅ Opérationnel | Config centralisé avec pools de modèles |
| RAW Recorder | ✅ Opérationnel | `data/raw_debates/*.jsonl` (172 fichiers) |
| OracleValidator | ✅ Opérationnel | Validation déterministe des résultats |
| ToolWorker | ✅ Opérationnel | 59 outils détectés |

### 1.2 Laboratoires

| Laboratoire | Rôle | Statut V1 |
|-------------|------|-----------|
| **Code Lab** | Exécution collaborative coding | ✅ EXECUTABLE |
| **Debate Lab** | Débats philosophiques multi-agents | ⚠️ NOT_CONNECTED (backend LLM requis) |
| **Experimental** | Génération de tâches synthétiques | ✅ Opérationnel |
| **Autopilot** | Orchestration automatique | ✅ Opérationnel |
| **Compare** | Analyse comparative d'expériences | ✅ Opérationnel |
| **Life Mean Studio** | UI/UX et visualisation | ✅ Opérationnel |

### 1.3 Role Templates (4 built-ins)

| Template | Type | Rôles | Status |
|----------|------|-------|--------|
| `coding-standard` | code_lab | Planner, Developer, Critic, Reviewer, Judge | ✅ |
| `philosophical-debate` | philosophical_debate | Moderator + 6 écoles philosophiques | ⚠️ Dépend personas |
| `scientist-skeptic` | debate | Moderator, Scientist, Skeptic | ✅ Générique |
| `molecular-discovery-council` | debate | 7 rôles scientifiques spécialisés | ✅ Nouveau (spec V1) |

### 1.4 Données Historiques

- **RAW debates** : `data/raw_debates/` — 172 fichiers `.jsonl`
- **Code Lab runs** : `code_lab_runs/` — 278 snapshots RAW
- **Subjects tree** : `data/subjects/` — coding, math, physics, chemistry
- **Cluster graph** : `data/cluster_graph.json` — 4 nœuds exp_3*, 6 arêtes

---

## 2. ANALYSE DES ERREURS OBSERVÉES

### 2.1 Erreurs Identifiées dans les Expériences

#### Expérience `exp_3405efd0` (Coding)
```json
{
  "error": "No answer computed",
  "method": "no_answer",
  "score": 0.0,
  "valid": false
}
```
**Cause racine** : L'extraction de paramètres dans `experiment_runner.py:305-338` ne gère que math/physics/chemistry. Les tâches coding nécessitent un traitement différent (génération de code vs calcul).

**Impact** : 100% d'échec sur les 100 tâches générées.

#### Expérience `exp_3aee3b11` et `exp_3f2b60dc` (Math)
- Routing vers `polyglot_coder` + `deterministic_coder`
- Tools non utilisés (`tools_used: []`)
- Même erreur "No answer computed"

#### Expérience `exp_36d17c20` (Physics)
- Pattern similaire : routing correct mais extraction de paramètres défaillante

### 2.2 Classification des Erreurs (Grille A/B/C)

| # | Preuve | Type | Verdict |
|---|--------|------|---------|
| E1 | `_persist_results_to_raw` avalait échec écriture RAW | A (code) | **P0 — RÉPARÉ** |
| E2 | `CodingMultiAgent` émet AGENT_STARTED sans try/finally | A (code) | **P1 — RÉPARÉ** |
| E3 | `ReflectionProtocol`/`StagnationDetector` nommés « protocol » | A (code) | YELLOW doc |
| E4 | `recorder_experiment_id` jamais exposé dans résultat | A (code) | YELLOW exposition |
| E5 | Toutes erreurs RAW = « No answer computed » | C (RAW miné) | **GREEN** : real failure, pas phantom |
| E6 | Domains: physics=100%, chemistry=100%, math≈60%, **coding=0%, logic=0%** | C (RAW) | Limitation connue |
| E7 | EventBus « fantôme » : 3 instances privées | A (audit) | YELLOW architectural |
| E8 | Sujets débats inutilisables quand backend LLM down | B (runtime) | **GREEN** : fake success impossible |

### 2.3 Causes Racines des Échecs exp_3 / exp_3.2

**Hypothèse** : « exp_3 » et « exp_3.2 » correspondent aux expériences UUID `exp_3405efd0` et `exp_36d17c20` (ou similaires).

**Causes identifiées** :
1. **Extraction de paramètres insuffisante** (`experiment_runner.py:305-338`)
   - Regex `\d+\.?\\d*` extrait les nombres mais ne mappe pas aux bons kwargs
   - Pas de support pour tâches coding (pas de `param_key` adapté)
   
2. **Tool detection limitée** (`library/tools/detection.py`)
   - Détecte `math_calculation`, `physics_force`, `chemistry_molar_mass`
   - Aucun outil `coding_generator` ou `code_writer` n'est détecté

3. **Routing vers workers inadaptés**
   - SmartRouter sélectionne `polyglot_coder` + `deterministic_coder`
   - Mais `ToolWorker` ne sait pas exécuter ces workers pour du coding

---

## 3. PLAN DE MIGRATION V2

### 3.1 PHASE 1 — AUDIT (Ceci)
✅ Complété : inventory, wiring map, evidence table

### 3.2 PHASE 2 — RESET LOGIQUE

| Action | Avant | Après |
|--------|-------|-------|
| **Archivage** | Expériences mixées dans `data/` | `data/archive/v1/*` en lecture seule |
| **Mémoires actives** | États de débat persistants | Reset complet, nouvelles sessions isolées |
| **Hypothèses** | Injectées automatiquement | Import explicite avec provenance traçable |
| **Validation** | Hypothèse → Résultat validé | Toujours distinguer: fait / hypothèse / simulation / spéculation |

### 3.3 PHASE 3 — SÉPARATION DES DOMAINES

**Mode scientifique strict (actif par défaut)** :
- Chimie organique, recherche moléculaire, biologie → preuves empiriques requises
- Hypothèses clairement identifiées comme telles

**Option désactivée par défaut** :
```json
{
  "allow_spiritual_perspectives": false,
  "spiritual_section": "distinct",
  "never_override_calculations": true
}
```

### 3.4 PHASE 4 — FIABILITÉ DES AGENTS

| Problème V1 | Correction V2 |
|-------------|---------------|
| JSON malformed moderator responses | Validation schema stricte + fallback déterministe |
| Boucles répétitives entre agents | `max_consecutive_same_speaker=1` + détection stagnation |
| Sélection déséquilibrée des intervenants | Speaker stats + rotation forcée |
| Références scientifiques non vérifiées | `Evidence & Novelty Curator` role obligatoire |
| Faits confondus avec hypothèses | Classification obligatoire: FACT / SUPPORTED_INFERENCE / ANALOGY / PREDICTION / HYPOTHESIS / SPECULATION / UNKNOWN |

### 3.5 PHASE 5 — RESEARCH LOOP

```
Hypothèse → Vérification → Calcul/Simulation autorisée → Résultat brut → Provenance → Réévaluation
```

**Contraintes** :
- Chaque exécution conserve: entrées, paramètres, sorties, erreurs, identifiants
- Aucun agent ne peut déclarer « expérience exécutée » sans trace vérifiable
- Provenance chain obligatoire: `experiment_id → generation_id → task_id → run_id`

### 3.6 PHASE 6 — VALIDATION

**Tests de non-régression** :
- Scénarios reproductibles avec `StubLLM`
- Comparaison avant/après sur métriques existantes
- Aucun agent ne peut modifier les résultats sans validation déterministe

---

## 4. LISTE DES MODIFICATIONS PROPOSÉES

### 4.1 Modifications Architecturales

| Fichier | Modification | Priorité |
|---------|--------------|----------|
| `experiments/settings.py` | Ajouter `allow_spiritual_perspectives: bool = False` | P0 |
| `role_templates/builtins.py` | Créer template `scientific-research` avec classification evidence obligatoire | P0 |
| `debate_lab/controller.py` | Ajouter validation schema JSON stricte pour moderator | P1 |
| `experiment_runner.py` | Étendre extraction paramètres aux outils coding/logic | P1 |
| `core/engine/debate.py` | Isoler les états de débat par expérience (pas de contamination) | P1 |

### 4.2 Nouveaux Composants V2

```python
# Nouveau module: experiments/scientific_loop.py
class ResearchLoop:
    """Boucle scientifique stricte: Hypothèse → Vérification → Résultat → Provenance"""
    
# Nouveau template: scientific-research
RoleTemplate(
    template_id="scientific-research",
    executor_type="debate",
    roles=[moderator, scientist, skeptic, evidence_curator, safety_guardian],
    response_contract=["ARGUMENT", "RATIONALE", "EVIDENCE", "HYPOTHESIS", "UNCERTAINTY", "NEXT"],
    shared_context="GLOBAL SCIENTIFIC RULES..."
)

# Nouvelle validation: EvidenceClassifier
class EvidenceClassifier:
    """Classifie chaque affirmation: FACT / SUPPORTED_INFERENCE / ANALOGY / PREDICTION / HYPOTHESIS / SPECULATION / UNKNOWN"""
```

### 4.3 Modifications UI/UX

- Dashboard V2 avec toggle « Mode scientifique strict »
- Section distincte pour perspectives spirituelles/philosophiques (si activées)
- Visualisation provenance chain obligatoire pour chaque résultat

---

## 5. RISQUES ET MÉCANISMES DE RETOUR ARRIÈRE

### 5.1 Risques Identifiés

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Perte données historiques | Faible | Élevé | Archive lecture seule avant migration |
| Cassure compatibilité API | Moyenne | Moyen | Versionning API `v1/` → `v2/` |
| Complexité accrue templates | Moyenne | Faible | Tests non-régression obligatoires |
| Performances dégradées | Faible | Moyen | Monitoring métriques V2 |

### 5.2 Mécanismes de Retour Arrière

```bash
# Snapshot avant migration
cp -r data/ data/archive/v1-pre-migration-$(date +%Y%m%d)/

# Rollback si nécessaire
mv data/archive/v1-pre-migration-*/data/ .
```

**Points de rollback** :
- Avant Phase 2 (reset logique)
- Avant Phase 3 (séparation domaines)
- Avant Phase 4 (fiabilité agents)

---

## 6. TESTS NÉCESSAIRES

### 6.1 Tests de Non-Régression

| Test | Couverture | Statut V1 |
|------|------------|-----------|
| `test_p0_raw_finalization.py` | RAW persistence | ✅ 3/3 verts |
| `test_p1_agent_terminal_event.py` | Agent events terminal | ✅ 4/4 verts |
| `test_molecular_council.py` | Template scientifique | ✅ 10/10 verts |
| `test_debate_lab_integration.py` | Intégration debate | ✅ Opérationnel |

### 6.2 Nouveaux Tests V2 Requises

```python
# tests/test_scientific_loop.py
def test_research_loop_provenance_chain():
    """Vérifie que chaque exécution conserve entrées, paramètres, sorties, erreurs, identifiants"""

def test_evidence_classification_obligatory():
    """Vérifie que chaque affirmation est classifiée correctement"""

def test_spiritual_perspectives_isolated():
    """Vérifie que les perspectives spirituelles ne contaminent pas les résultats scientifiques"""

def test_moderator_json_validation():
    """Vérifie la validation stricte du JSON moderator"""
```

### 6.3 Tests de Sécurité

| Test | Objectif |
|------|----------|
| `test_safety_guardian_intervention` | Vérifie l'intervention sur directions hazardous |
| `test_no_phantom_output` | Vérifie qu'aucun résultat n'est fabriqué |
| `test_backend_gate` | Vérifie que sans backend LLM → FAILED explicite |

---

## 7. PREMIÈRE ÉTAPE D'IMPLÉMENTATION RECOMMANDÉE

### 7.1 Priorité Absolue : Corriger l'Extraction de Paramètres

**Fichier** : `experiments/runner.py:305-338`

```python
# Extension du mapping tool detection pour coding tasks
if task.domain == "coding" or "code" in task.description.lower():
    # Détecter pattern "Write code to solve..."
    # Extraire difficulty, function signature, test cases
    # Générer worker approprié (code_generator, not tool_worker)
    pass
```

### 7.2 Deuxième Priorité : Template Scientific Research

**Fichier** : `role_templates/builtins.py`

Ajouter fonction `scientific_research()` avec :
- 5 rôles: Moderator, Scientist, Skeptic, Evidence Curator, Safety Guardian
- Shared context obligatoire (règles scientifiques globales)
- Response contract (§78): ARGUMENT, RATIONALE, EVIDENCE, HYPOTHESIS, UNCERTAINTY, NEXT

### 7.3 Troisième Priorité : Reset Logique

**Fichier** : `experiments/settings.py`

```python
@dataclass
class ExperimentSettings:
    # Nouveau champ
    allow_spiritual_perspectives: bool = False
    
    # Validation
    if self.allow_spiritual_perspectives:
        # Forcer section distincte
        assert self.spiritual_section_configured
```

---

## 8. LIVRABLES ATTENDUS

1. ✅ **Rapport d'audit** — Ce document
2. ⏳ **Plan de migration V2** — À finaliser après approbation
3. ⏳ **Liste des modifications proposées** — Sections 4-6
4. ⏳ **Risques et mécanismes de retour arrière** — Section 5
5. ⏳ **Tests nécessaires** — Sections 6-7
6. ⏳ **Première étape d'implémentation recommandée** — Section 7

---

## 9. ATTENTE FEU VERT UTILISATEUR

**Aucune modification ne sera appliquée sans approbation explicite.**

Les changements proposés sont :
- **Non-destructifs** : archive lecture seule des données V1
- **Réversibles** : mécanismes de rollback identifiés
- **Testés** : nouveaux tests requis avant déploiement

---

**Fin du rapport d'audit.**  
*Prochaine étape : Approbation du plan de migration V2.*
