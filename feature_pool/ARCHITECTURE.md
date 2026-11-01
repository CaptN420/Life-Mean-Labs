# FeaturePool Engine — Architecture Proposée

## Audit du Dépôt

| Métrique | Valeur |
|----------|--------|
| Fichiers Python modernes | 191 |
| Fichiers Python legacy (projet) | ~10,400 |
| Tests existants | 131+ |
| Features découvertes | 147 |

### Distribution par Catégorie

| Catégorie | Count | Exemples Clés |
|-----------|-------|---------------|
| AGENTS | 43 | BaseAgent, CodingAgent, CrawlerWorker, MirrorAgent... |
| DEBATE | 27 | DebateEngine, DebateSessionFactory, ConfigurableDebateAgent... |
| EXPERIMENTS | 15 | ContextEngine, ExperienceEngine, TelemetryEngine... |
| STUDIO | 18 | AgentManager, WorkflowManager, ExperimentManager... |
| ROUTING | 10 | ModelRouter, AdaptiveRouter, SmartRouter... |
| PROVIDERS | 11 | LmStudioProvider, OpenRouterProvider, ProviderFactory... |
| SAFETY | 8 | Sentinel, SafetyGate, IncidentManager... |
| VALIDATION | 7 | EvidenceValidator, OracleValidator, PatchValidator... |
| GENERATION | 3 | FixGenerator, PatchGenerator, TaskGenerator... |

---

## Architecture FeaturePool

```
feature_pool/
├── __init__.py          # exports: FeaturePool, discover_features, get_registry
├── schemas.py           # Data models (Feature, FeatureLocation, etc.)
├── registry.py          # Central registry - single source of truth
├── scanner.py           # Static discovery (read-only, no execution)
├── analyzer.py          # Capability analysis & similarity detection
├── dependencies.py      # Module relationship graph
├── compatibility.py     # Conflict detection & integration readiness
├── integration_planner.py  # Safe integration planning
├── history.py           # Audit trail & change tracking
└── studio_interface.py  # Dashboard page for Feature Pool
```

---

## Cycle de Vie des Features

```
DISCOVERED → ANALYZED → VALIDATED → READY → INTEGRATED
    ↑          ↓           ↓         ↓         ↓
ARCHIVED   BLOCKED     BROKEN    (rollback)  (completed)
    ↑___________________________________________↓
                 EXPERIMENTAL
```

### Séparation des Statuts

| Aspect | Status | Description |
|--------|--------|-------------|
| **Technique** | DISCOVERED, ANALYZED, VALIDATED, BROKEN, BLOCKED | État du code |
| **Intégration** | READY, INTEGRATED, ARCHIVED, EXPERIMENTAL | Prêt à intégrer |

---

## Modules Détaillés

### 1. `schemas.py` — Modèles de Données

```python
@dataclass
class FeatureLocation:
    path: str          # Chemin relatif au projet
    module: str        # Nom du module Python
    line_start: int    # Ligne de début
    line_end: Optional[int]
    symbol: str        # Class/Function name

@dataclass  
class Feature:
    id: str                    # UUID stable: feat_<category>_<name>
    name: str
    category: FeatureCategory
    status: FeatureStatus = DISCOVERED
    integration_status: str = "NOT_STARTED"  # Separate from technical status
    locations: List[FeatureLocation]
    dependencies: Set[str]     # Other feature IDs
    test_paths: List[str]
    metadata: Dict[str, str]   # Extra info (author, date, notes)
    confidence: float          # 0.0-1.0 analysis confidence
    history: List[HistoryEntry]
    
    @property
    def is_legacy(self) -> bool: ...
    
    @property  
    def source(self) -> str: ...
```

### 2. `scanner.py` — Découverte Statique (Read-Only)

**Principe**: Lecture seule, aucune exécution de code.

```python
class FeatureScanner:
    """Scans project for features without executing code."""
    
    EXCLUDE_PATTERNS = {'.venv', '__pycache__', 'node_modules', '.git', 
                       'site-packages', 'crawled'}
    
    PROJECT_KEYWORDS = {
        'engine': FeatureCategory.EXPERIMENTS,
        'controller': FeatureCategory.STUDIO,
        'manager': FeatureCategory.STUDIO,
        'worker': FeatureCategory.AGENTS,
        'agent': FeatureCategory.AGENTS,
        'router': FeatureCategory.ROUTING,
        'provider': FeatureCategory.PROVIDERS,
        # ... etc
    }
    
    def discover(self) -> Dict[str, Feature]:
        """Returns all discovered features."""
        
    def _classify_feature(self, name: str, path: Path, line_no: int) -> Optional[Feature]:
        """Classify class/function as a feature."""
```

### 3. `registry.py` — Registre Central

```python
class FeatureRegistry:
    """Central registry - single source of truth for all features."""
    
    def __init__(self, storage_backend: str = "sqlite"):
        # Reuses existing persistence if available
        self._features: Dict[str, Feature] = {}
        self._history = HistoryTracker()
        
    def add(self, feature: Feature) -> None: ...
    def get(self, feature_id: str) -> Optional[Feature]: ...
    def search(self, query: str) -> List[Feature]: ...
    def filter_by_status(self, status: FeatureStatus) -> List[Feature]: ...
    def filter_by_category(self, category: FeatureCategory) -> List[Feature]: ...
    def get_dependencies(self, feature_id: str) -> Set[str]: ...
    
    # Persistence
    def save(self) -> None: ...
    def load(self) -> None: ...
```

### 4. `analyzer.py` — Analyse des Capacités

```python
class FeatureAnalyzer:
    """Analyzes capabilities and detects similar features."""
    
    def analyze(self, feature: Feature) -> Feature:
        """Perform full analysis, update confidence."""
        
    def detect_similar(self, feature_id: str) -> List[str]:
        """Find features with similar names/capabilities."""
        
    def assess_readiness(self, feature: Feature) -> str:
        """Determine READY/BROKEN/BLOCKED status."""
        
    def _check_tests(self, feature: Feature) -> bool: ...
    def _check_dependencies(self, feature: Feature) -> bool: ...
```

### 5. `dependencies.py` — Relations entre Modules

```python
class DependencyGraph:
    """Tracks relationships between modules and features."""
    
    def build_graph(self) -> Dict[str, Set[str]]: ...
    def find_cycles(self) -> List[List[str]]: ...
    def get_impact_analysis(self, feature_id: str) -> Set[str]: ...
    def detect_orphans(self) -> List[str]: ...  # Features with no dependents
```

### 6. `compatibility.py` — Compatibilité

```python
class CompatibilityChecker:
    """Checks integration compatibility."""
    
    def check_compatibility(self, feature_a: str, feature_b: str) -> CompatibilityResult:
        """Check if two features can coexist."""
        
    def detect_conflicts(self) -> List[Conflict]: ...
    def assess_integration_readiness(self, feature_id: str) -> bool: ...
```

### 7. `integration_planner.py` — Plans d'Intégration

```python
class IntegrationPlanner:
    """Plans safe integration without modifying code."""
    
    def plan_integration(self, feature_id: str) -> IntegrationPlan:
        """Generate a step-by-step integration plan."""
        
    def simulate_integration(self, plan: IntegrationPlan) -> SimulationResult: ...
    def generate_test_plan(self, feature_id: str) -> TestPlan: ...
```

### 8. `history.py` — Traçabilité

```python
@dataclass
class HistoryEntry:
    timestamp: datetime
    action: str           # DISCOVERED, ANALYZED, VALIDATED, etc.
    actor: str            # System or user
    details: Dict[str, Any]

class HistoryTracker:
    def record(self, feature_id: str, action: str, details: Dict) -> None: ...
    def get_history(self, feature_id: str) -> List[HistoryEntry]: ...
    def get_changes_since(self, timestamp: datetime) -> List[HistoryEntry]: ...
```

---

## Persistance

**Décision**: Réutiliser le mécanisme existant de `life_mean_studio/engine/storage.py` si compatible, sinon utiliser SQLite local.

| Option | Avantage | Inconvénient |
|--------|----------|---------------|
| Existing storage | Pas de duplication | Peut ne pas supporter nouveaux modèles |
| SQLite local | Simple, portable | Nécessite migration schema |

**Recommandation**: Commencer avec SQLite local (`feature_pool.db`) pour isolation, migrer vers storage existant si besoin.

---

## Interface Studio

Page `Feature Pool` dans le dashboard avec:

| Fonctionnalité | Description |
|----------------|-------------|
| **Liste filtrable** | Par statut, module, catégorie |
| **Vue dépendances** | Graphique des relations |
| **Tests associés** | Liens vers tests existants |
| **Comparaison versions** | Diff entre états |
| **Plan d'intégration** | Étapes avant intégration |
| **Conflits** | Alertes de compatibilité |
| **Historique** | Timeline des changements |

---

## Sécurité

| Règle | Implémentation |
|-------|----------------|
| Scanner read-only | Pas d'import/exec de code découvert |
| Pas d'exécution auto | Features ne sont jamais exécutées par le scanner |
| Validation requise | Status VALIDATED seulement après tests |
| Pas de modification destructive | Integration planner propose, n'exécute pas |
| Confirmation explicite | UI demande confirmation avant intégration |

---

## Livrable Final

Format CSV/JSON avec colonnes:

```
ID | Nom | Source | Capacité | Statut | Dépendances | Tests | Action recommandée
```

Roadmap priorisée basée sur:
1. Features critiques (Routing, Safety)
2. Features legacy stables
3. Features expérimentales prometteuses

---

## Prochaines Étapes

1. **Implémenter** `schemas.py` + `registry.py` (fondations)
2. **Implémenter** `scanner.py` (découverte)
3. **Implémenter** `analyzer.py` (analyse)
4. **Implémenter** `dependencies.py` + `compatibility.py` (relations)
5. **Implémenter** `integration_planner.py` + `history.py` (traçabilité)
6. **Créer** interface studio (`feature_pool_page.py`)
7. **Générer** rapport final + roadmap

---

*Architecture validée pour implémentation.*
