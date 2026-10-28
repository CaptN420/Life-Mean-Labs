# LIFE_MEAN LAB V2 — PLAN DE MIGRATION

**Date :** 2026-10-27  
**Statut :** En attente d'approbation utilisateur  
**Référence :** Audit complet `LIFE_MEAN_LAB_V2_AUDIT_REPORT.md`

---

## 0. APPROCHE GLOBALE

**Principe directeur :** Ne rien supprimer sans sauvegarde vérifiée.  
**Garantie :** Snapshot V1 intact, migration réversible, tests de non-régression obligatoires.

---

## 1. ARCHIVAGE V1 (Phase 1 — Avant toute modification)

### 1.1 Structure d'archive

```
data/
├── archive/
│   └── v1-pre-migration-20261027/
│       ├── raw_debates/          # 172 fichiers .jsonl
│       ├── subjects/             # Tree sujets (coding, math, physics)
│       ├── cluster_graph.json
│       └── settings.json         # Config actuelle
```

### 1.2 Commande d'archivage

```bash
mkdir -p data/archive/v1-pre-migration-$(date +%Y%m%d)
cp -r data/raw_debates data/archive/v1-pre-migration-$(date +%Y%m%d)/
cp -r data/subjects data/archive/v1-pre-migration-$(date +%Y%m%d)/
cp data/cluster_graph.json data/archive/v1-pre-migration-$(date +%Y%m%d)/
cp overrides/settings.json data/archive/v1-pre-migration-$(date +%Y%m%d)/
```

### 1.3 Vérification d'intégrité

```bash
# Calculer hash des fichiers archivés
find data/archive/v1-pre-migration-*/ -type f -exec md5sum {} \; > archive_checksums.md5

# Vérifier avant suppression
md5sum -c archive_checksums.md5
```

---

## 2. RESET LOGIQUE (Phase 2)

### 2.1 Mémoires actives → Reset

**Fichier modifié :** `experiments/settings.py`

```python
@dataclass
class ExperimentSettings:
    # Nouveau champ
    reset_active_memories: bool = True
    
    def __post_init__(self):
        if self.reset_active_memories:
            # Clear debate states
            self._clear_debate_states()
            # Prevent auto-injection of old hypotheses
            self._isolate_new_experiments()
```

### 2.2 Isolement des expériences

**Nouveau mécanisme :** `ExperimentIsolation`

```python
class ExperimentIsolation:
    """Empêche l'injection automatique des anciennes hypothèses."""
    
    def __init__(self, experiment_id: str):
        self.experiment_id = experiment_id
        self.allowed_hypotheses: List[str] = []  # Import explicite seulement
    
    def import_hypothesis(self, source: str, provenance: ProvenanceChain):
        """Import explicite avec traçabilité."""
        if not provenance.valid:
            raise ValueError("Provenance invalid")
        self.allowed_hypotheses.append((source, provenance))
```

---

## 3. SÉPARATION DES DOMAINES (Phase 3)

### 3.1 Mode scientifique strict (actif par défaut)

**Fichier modifié :** `experiments/settings.py`

```python
@dataclass
class ExperimentSettings:
    scientific_mode: bool = True  # Actif par défaut
    
    # Option désactivée par défaut
    allow_spiritual_perspectives: bool = False
    
    # Configuration section distincte (si activée)
    spiritual_section_config: Optional[Dict] = None
```

### 3.2 Validation des domaines

**Nouveau module :** `experiments/domain_validation.py`

```python
class DomainValidator:
    """Valide que les perspectives sont séparées."""
    
    SCIENTIFIC_DOMAINS = {"chemistry", "molecular", "biology", "physics"}
    SPIRITUAL_DOMAINS = {"philosophy", "spirituality"}
    
    def validate(self, domain: str, perspective: str) -> bool:
        if domain in self.SCIENTIFIC_DOMAINS and perspective in self.SPIRITUAL_DOMAINS:
            return False  # Jamais mélanger
        return True
```

---

## 4. FIABILITÉ DES AGENTS (Phase 4)

### 4.1 Validation JSON stricte du modérateur

**Fichier modifié :** `debate_lab/controller.py`

```python
class DebateLabController:
    MODERATOR_JSON_SCHEMA = {
        "type": "object",
        "required": ["selected_speaker", "challenge", "reason"],
        "properties": {
            "selected_speaker": {"type": "string", "enum": VALID_SPEAKERS},
            "challenge": {"type": "string", "minLength": 50},
            "reason": {"type": "string", "minLength": 10}
        }
    }
    
    def _validate_moderator_decision(self, decision: dict) -> bool:
        """Validation schema stricte avant utilisation."""
        return validate_against_schema(decision, self.MODERATOR_JSON_SCHEMA)
```

### 4.2 Prévention boucles répétitives

**Fichier modifié :** `core/engine/debate.py`

```python
class DebateEngine:
    def _check_stagnation(self) -> bool:
        """Détecte stagnation = même candidate sans nouveau evidence."""
        recent_turns = self.turn_manager.get_recent_turns(10)
        unique_arguments = set(t.response[:50] for t in recent_turns)
        return len(unique_arguments) < 3  # Trop de répétitions
```

### 4.3 Sélection équilibrée des intervenants

**Fichier modifié :** `core/engine/debate.py`

```python
class DebateEngine:
    def _get_moderator_decision(self) -> Optional[dict]:
        # Statistiques de participation obligatoires
        speaker_stats = self.argument_state.speaker_turn_count
        min_turns = min(speaker_stats.values())
        
        # Forcer rotation si déséquilibre
        if max(speaker_stats.values()) > min_turns * 2:
            return self._force_balanced_selection()
```

---

## 5. RESEARCH LOOP (Phase 5)

### 5.1 Structure de la boucle

**Nouveau module :** `experiments/scientific_loop.py`

```python
class ResearchLoop:
    """Boucle scientifique stricte."""
    
    def __init__(self, hypothesis: str, experiment_id: str):
        self.hypothesis = hypothesis
        self.experiment_id = experiment_id
        self.provenance_chain: ProvenanceChain = None
    
    def execute(self) -> ResearchResult:
        """Exécute: Hypothèse → Vérification → Calcul → Résultat → Provenance."""
        # 1. Enregistrer hypothèse
        self._record_hypothesis()
        
        # 2. Vérification (outils déterministes)
        verification = self._verify_hypothesis()
        
        # 3. Calcul/simulation autorisée
        result = self._compute_or_simulate(verification)
        
        # 4. Conserver provenance complète
        self.provenance_chain = self._build_provenance(result)
        
        # 5. Réévaluation par les agents
        reevaluation = self._reevaluate_by_agents(result)
        
        return ResearchResult(
            hypothesis=self.hypothesis,
            verification=verification,
            result=result,
            provenance=self.provenance_chain,
            reevaluation=reevaluation
        )
```

### 5.2 Contrainte : Trace vérifiable obligatoire

**Règle absolue :**

```python
class ResearchResult:
    @property
    def is_verified(self) -> bool:
        """Aucun agent ne peut déclarer 'expérience exécutée' sans trace."""
        return (
            self.provenance is not None and
            self.provenance.experiment_id and
            self.provenance.generation_id and
            self.provenance.task_id and
            self.provenance.run_id
        )
```

---

## 6. VALIDATION (Phase 6)

### 6.1 Tests de non-régression

**Fichier :** `tests/test_v2_migration.py`

```python
class TestV2Migration:
    def test_scientific_mode_default(self):
        """Mode scientifique strict actif par défaut."""
        settings = ExperimentSettings()
        assert settings.scientific_mode == True
    
    def test_spiritual_perspectives_disabled_by_default(self):
        """Perspectives spirituelles désactivées par défaut."""
        settings = ExperimentSettings()
        assert settings.allow_spiritual_perspectives == False
    
    def test_moderator_json_validation(self):
        """Validation JSON stricte du modérateur."""
        controller = DebateLabController()
        invalid_decision = {"selected_speaker": "Invalid"}
        assert controller._validate_moderator_decision(invalid_decision) == False
    
    def test_stagnation_detection(self):
        """Détection de stagnation fonctionne."""
        engine = DebateEngine(...)
        # Simuler 10 tours identiques
        assert engine._check_stagnation() == True
    
    def test_research_loop_provenance(self):
        """Provenance chain obligatoire."""
        loop = ResearchLoop("Hypothesis", "exp_test")
        result = loop.execute()
        assert result.is_verified == True
```

### 6.2 Tests de sécurité

**Fichier :** `tests/test_v2_security.py`

```python
class TestV2Security:
    def test_no_phantom_output(self):
        """Aucun résultat fabriqué."""
        # Sans backend LLM → FAILED explicite
        settings = ExperimentSettings()
        result = run_experiment(settings)
        assert result.status == "FAILED"  # Pas de COMPLETED fantôme
    
    def test_safety_guardian_intervention(self):
        """Safety Guardian intervient sur directions hazardous."""
        guardian = SafetyGuardian()
        hazardous_direction = "optimize_poisoning"
        verdict = guardian.evaluate(hazardous_direction)
        assert verdict == "QUARANTINED_DIRECTION"
```

---

## 7. PREMIÈRE ÉTAPE D'IMPLÉMENTATION

### 7.1 Priorité 1 : Corriger l'Extraction de Paramètres

**Fichier :** `experiments/runner.py`  
**Lignes :** 305-338

```python
# Extension du mapping tool detection pour coding tasks
if task.domain == "coding" or "code" in task.description.lower():
    # Détecter pattern "Write code to solve..."
    match = re.search(r'difficulty (\d+)', task.description)
    difficulty = int(match.group(1)) if match else 2
    
    # Générer worker approprié (pas tool_worker)
    routing_decision = {
        "selected": ["code_generator"],
        "scores": {"code_generator": 8.0},
        "difficulty": difficulty
    }
    
    # Exécuter via CodeLabEngine, pas ToolWorker
    answer = self._execute_coding_task(task, routing_decision)
```

### 7.2 Priorité 2 : Template Scientific Research

**Fichier :** `role_templates/builtins.py`

```python
def scientific_research(version: str = "1.0.0") -> RoleTemplate:
    """Template recherche scientifique V2."""
    roles = [
        RoleSpec(
            role_id="moderator",
            name="Research Director",
            instructions_template="Scientific coordinator...",
            model_slot="GENERAL_REASONING_MODEL"
        ),
        RoleSpec(
            role_id="scientist",
            name="Scientist",
            instructions_template="Evidence-based reasoning...",
            model_slot="GENERAL_REASONING_MODEL"
        ),
        RoleSpec(
            role_id="skeptic",
            name="Skeptic",
            instructions_template="Pressure-test every claim...",
            model_slot="GENERAL_REASONING_MODEL"
        ),
        RoleSpec(
            role_id="evidence-curator",
            name="Evidence Curator",
            instructions_template="Classify every claim: FACT / HYPOTHESIS / SPECULATION...",
            model_slot="GENERAL_REASONING_MODEL"
        ),
        RoleSpec(
            role_id="safety-guardian",
            name="Safety Guardian",
            instructions_template="Protect research direction...",
            model_slot="GENERAL_REASONING_MODEL"
        ),
    ]
    
    return RoleTemplate(
        template_id="scientific-research",
        name="Scientific Research",
        version=version,
        executor_type="debate",
        roles=roles,
        response_contract=["ARGUMENT", "RATIONALE", "EVIDENCE", "HYPOTHESIS", "UNCERTAINTY", "NEXT"],
        shared_context=_SCIENTIFIC_SHARED_CONTEXT,
    )
```

### 7.3 Priorité 3 : Reset Logique

**Fichier :** `experiments/settings.py`

```python
@dataclass
class ExperimentSettings:
    # Nouveau champ
    reset_active_memories: bool = True
    
    def __post_init__(self):
        if self.reset_active_memories:
            self._clear_debate_states()
    
    def _clear_debate_states(self):
        """Reset mémoires actives."""
        from philosophical_council.memory.debate_state import DebateState
        self.argument_state = DebateState(topic=self.topic)
    
    def _isolate_new_experiments(self):
        """Empêche injection automatique anciennes hypothèses."""
        self.allowed_hypotheses = []  # Import explicite seulement
```

---

## 8. CALENDRIER D'IMPLÉMENTATION

| Phase | Durée estimée | Dépendances |
|-------|---------------|-------------|
| 1. Archivage V1 | 5 min | Aucune |
| 2. Reset logique | 30 min | Phase 1 complétée |
| 3. Séparation domaines | 1h | Phase 2 complétée |
| 4. Fiabilité agents | 2h | Phase 3 complétée |
| 5. Research loop | 3h | Phase 4 complétée |
| 6. Validation | 1h | Toutes phases |

**Total estimé :** 7.5 heures de développement  
**Tests inclus :** Oui, dans chaque phase

---

## 9. VALIDATION UTILISATEUR REQUISE

**Avant toute modification, l'utilisateur doit approuver :**

1. ✅ Plan d'archivage V1 (section 1)
2. ✅ Structure reset logique (section 2)
3. ✅ Séparation domaines (section 3)
4. ✅ Fiabilité agents (section 4)
5. ✅ Research loop (section 5)
6. ✅ Tests de validation (section 6)

**Répondre par :**
- `APPROVE` pour démarrer l'implémentation
- `MODIFY section_X` pour demander des changements
- `SKIP phase_X` pour sauter une phase

---

**Fin du plan de migration.**  
*En attente d'approbation utilisateur.*
