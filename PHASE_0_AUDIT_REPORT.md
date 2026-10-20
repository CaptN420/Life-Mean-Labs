# Phase 0 — Audit et Architecture Life_mean

**Date :** 2025-10-15  
**Statut :** AUDIT COMPLET — EN ATTENTE D'APPROBATION POUR PHASE 1

---

## 1. État Git Initial

### Modifications non commitées
```
M code_lab/multiagent.py
M hermes-orchestrator/package-lock.json
M hermes-orchestrator/package.json
M hermes-orchestrator/src/index.ts
M run_server.bat
?? .dockerignore
?? AUDIT_COMPLET.md
?? Dockerfile
?? SECURITY_PHASE_D1_REPORT.md
?? SECURITY_PHASE_D_REPORT.md
?? code_lab/compression/
?? code_lab/compression_adapter.py
?? docker-compose.yml
?? docker/
?? hermes-orchestrator/audit_log.jsonl
?? hermes-orchestrator/src/codelab_adapter.ts
?? hermes-orchestrator/src/middleware/
?? hermes-orchestrator/src/security_gate/
?? hermes-orchestrator/tests/security-gate-integration.test.ts
?? hermes-orchestrator/tests/security-integration.test.ts
?? hermes-orchestrator/tests/security.test.ts
?? hermes_cronjob_manager/
?? life_mean_studio/
?? tests/compression_validation/
```

### Fichiers modifiés (5)
1. `code_lab/multiagent.py` — modifications non spécifiées
2. `hermes-orchestrator/package.json` — dépendances mises à jour
3. `hermes-orchestrator/package-lock.json` — lock file sync
4. `hermes-orchestrator/src/index.ts` — intégration codelab_adapter
5. `run_server.bat` — modifications du launcher Docker

### Fichiers nouveaux (17)
- **Sécurité** : `security_gate/`, `middleware/auth.ts`, `middleware/validation.ts`
- **Bridge** : `codelab_adapter.ts`, `audit_log.jsonl`
- **Docker** : `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- **Studio** : `life_mean_studio/` (launcher, engine, workflows, prompts)
- **Compression** : `code_lab/compression/` (context_budget, history_compressor, output_compressor)

### Commits récents
```
4487318 test(runtime-restore): fix env/probe for system python runs
a9fb83f feat: A/B v2 experiment with remediated DEVELOPER configuration
95d7d01 chore: change license from MIT to Apache-2.0
```

---

## 2. Inventaire de l'Architecture Existante

### Structure du projet (275 fichiers TS/Python)
```
Life_mean/
├── code_lab/                    # Moteur Python natif
│   ├── engine.py               # Pipeline planner→developer→verifier→critic→repair→validate
│   ├── config.py               # Configuration versionnée, slots IA par rôle
│   ├── workspace.py            # Isolation des exécutables dans workspace
│   ├── controller.py           # Orchestration multi-runs, events, timeline
│   └── compression/            # NEW — Compression de contexte (phase 0)
│       ├── context_budget.py
│       ├── history_compressor.py
│       └── output_compressor.py
├── hermes-orchestrator/         # Backend TypeScript
│   ├── src/
│   │   ├── index.ts            # Point d'entrée Express
│   │   ├── models/             # ModelRegistry, ModelManager, VRAMManager
│   │   ├── router/             # PhiloRouter (Clef + fallback)
│   │   ├── orchestrator/       # RequestQueue
│   │   ├── middleware/         # auth.ts, cors.ts, rate-limit.ts, validation.ts
│   │   ├── security_gate/      # adapter.ts, audit.ts
│   │   └── codelab_adapter.ts  # NEW — Routeur sécurisé Code Lab → Pi
│   └── tests/                  # Tests sécurité
├── life_mean_studio/           # Studio PySide6 (Phase C — UI only)
│   ├── launcher/app.py         # Widget principal
│   ├── engine/storage.py       # SQLite storage layer
│   └── workflows/              # WorkflowManager
├── library/                     # Bibliothèque de composants
│   ├── personas/               # Personas déterministes (Aristotle, Turing, etc.)
│   ├── tools/                  # Tools coding (loc, cyclomatic, type identification)
│   └── protocols/              # Protocoles existants
├── experiments/                 # Dashboard HTTP + UI controller
│   ├── dashboard.py            # Server HTTP avec routes API
│   └── ui_controller.py        # State management
├── docker/                      # Docker Pi sandbox (NEW)
│   └── docker-compose.pi.yml
└── code_lab_runs/              # Runs existants (non suivis Git)
```

### Composants clés identifiés

#### Backend Python (`code_lab/`)
| Module | Rôle | État |
|--------|------|------|
| `engine.py` | Pipeline multi-agent | ✅ Opérationnel |
| `config.py` | Configuration versionnée | ✅ Opérationnel |
| `workspace.py` | Isolation exécution | ✅ Opérationnel |
| `controller.py` | Orchestration runs | ✅ Opérationnel |
| `compression/` | Compression contexte | 🆕 Nouveau (Phase 0) |

#### Backend TypeScript (`hermes-orchestrator/`)
| Module | Rôle | État |
|--------|------|------|
| `index.ts` | Server Express | ✅ Opérationnel |
| `models/ModelRegistry.ts` | Registry modèles | ⚠️ Simulé (VRAM fake) |
| `models/ModelManager.ts` | Gestion chargement | ⚠️ Simulé |
| `router/PhiloRouter.ts` | Routage Clef | ✅ Opérationnel (fallback simu) |
| `middleware/auth.ts` | Auth JWT basique | ✅ Implémenté |
| `middleware/validation.ts` | Validation tâches | ✅ Implémenté |
| `security_gate/adapter.ts` | Adaptateur Pi | ✅ Implémenté |
| `security_gate/audit.ts` | Journal audit | ✅ Implémenté |
| `codelab_adapter.ts` | Routeur Code Lab | 🆕 Nouveau (Phase 0) |

#### Studio (`life_mean_studio/`)
| Module | Rôle | État |
|--------|------|------|
| `launcher/app.py` | UI PySide6 | ✅ Widget principal |
| `engine/storage.py` | SQLite storage | ✅ Schema workflows/prompts/sessions |
| `workflows/manager.py` | WorkflowManager | ✅ CRUD workflows |

#### Library (`library/`)
| Module | Rôle | État |
|--------|------|------|
| `personas/` | Personas déterministes | ✅ 20+ thinkers |
| `tools/coding/` | Tools pure Python | ✅ 6 tools (loc, cyclomatic, etc.) |

---

## 3. Vérification des Garanties Réelles de Phase D

### Authentification
- **Implémenté** : Middleware `authenticate()` avec tokens base64url JSON
- **Rôles** : `OBSERVER`, `RUNNER`, `ADMIN`
- **Expiration** : 24h par défaut
- **Révoqué** : Set in-memory (perd au restart)

### Autorisation
- **Implémenté** : Middleware `authorize('RUNNER')` / `authorize('ADMIN')`
- **Routes protégées** : `/inference`, `/models`, `/codelab/*`
- **Route publique** : `/health` uniquement

### Security Gate
- **Adaptateur** : `SecurityGateAdapter` avec modes AUDIT/DEV/APPROVAL
- **Permissions** : Registration par task_id, deadline, allowed_commands
- **Audit** : `AuditLogger` avec rotation 90 jours
- **Limitation** : Mode DEV auto-approuve (à durcir)

### Isolation Docker
- **Dashboard** : Container read-only, cap_drop ALL, tmpfs /tmp
- **Pi sandbox** : Container isolé, volumes séparés, restart unless-stopped
- **Réseau** : Private network `docker_pi-net`

### Lacunes identifiées
| Problème | Impact | Sévérité |
|----------|--------|----------|
| VRAMManager simulé | Pas de contrôle réel GPU | Moyenne |
| Token store in-memory | Perte tokens au restart | Faible |
| Mode DEV auto-approuve | Contourne Security Gate | Haute |
| Pas de binding réseau durci | Exposition localhost | Moyenne |
| Pas de test end-to-end | Couverture incertaine | Moyenne |

---

## 4. Composants à Réutiliser

### Python (existants, stables)
- `code_lab/engine.py` — Pipeline multi-agent
- `code_lab/config.py` — Configuration versionnée
- `code_lab/workspace.py` — Isolation exécution
- `code_lab/compression/` — Compression contexte (nouveau)
- `library/personas/` — Personas déterministes
- `library/tools/` — Tools pure Python

### TypeScript (existants, stables)
- `hermes-orchestrator/src/middleware/auth.ts` — Auth JWT
- `hermes-orchestrator/src/middleware/validation.ts` — Validation tâches
- `hermes-orchestrator/src/security_gate/audit.ts` — Journal audit
- `hermes-orchestrator/src/router/PhiloRouter.ts` — Routage Clef

### Studio (existants, stables)
- `life_mean_studio/engine/storage.py` — SQLite storage
- `life_mean_studio/workflows/manager.py` — WorkflowManager

---

## 5. Lacunes Techniques

### Données
- **Absence** de schémas Profile, Experience, Checkpoint, Branch, Cluster
- **Absence** de Context Graph (arbre de contexte)
- **Absence** de système de packs `.lmpack`
- **Absence** de Library locale (gestion archives)

### Providers
- **Absence** de ProviderRegistry (multi-provider)
- **Absence** de ModelRouter (routage par agent)
- **Absence** de CredentialStore (stockage sécurisé clés)
- **Absence** de ResourceManager (profils ressources)

### UI/UX
- **Absence** de Context Tree visuel
- **Absence** de Studio Builder (éditeurs persona/role/skill/workflow)
- **Absence** de Pack Builder
- **Absence** de sélection pré-RUN (workflow, profil, confidentialité)

### GitHub
- **Absence** de connecteur GitHub
- **Absence** de gestion dépôts/branches/commits
- **Absence** de découverte communautaire

### Identité/Prouvenance
- **Absence** de métadonnées créateur dans `.lmpack`
- **Absence** de traçabilité provenance composants
- **Absence** de fiches créateurs dans Library
- **Absence** de système d'attribution (original vs adapted)

---

## 6. Schémas Proposed pour Données Centrales

### Profile
```typescript
interface Profile {
  id: string;
  name: string;
  version: string;
  
  // Providers IA
  providers: ProviderProfile[];
  
  // Budgets ressources
  budgets: ResourceBudget;
  
  // Préférences
  preferences: {
    theme: 'light' | 'dark';
    language: string;
    auto_save: boolean;
  };
  
  // Politique confidentialité
  privacy: PrivacyPolicy;
  
  // Permissions (demandées, jamais accordées auto)
  requested_permissions: PermissionRequest[];
  
  created_at: string;
  updated_at: string;
}

interface ProviderProfile {
  agent_id: string;
  provider: 'lm_studio' | 'openrouter' | 'openai' | 'xAI' | string;
  model_id: string;
  api_endpoint: string;
  credentials_profile_id: string; // Référence au coffre
  fallback_chain: string[];
  budget?: ResourceBudget;
}

interface ResourceBudget {
  vram_target_mb: number;
  ram_limit_mb: number;
  cpu_limit: number;
  context_max_tokens: number;
  concurrency_limit: number;
  token_budget?: number;
  time_limit_seconds?: number;
  cost_estimate?: number;
  fallback_strategy: 'none' | 'next_provider' | 'local_fallback';
}

interface PrivacyPolicy {
  mode: 'private_session' | 'local_history' | 'full_observatory';
  cloud_allowed: boolean;
  raw_enabled: boolean;
  retention_days?: number;
}
```

### Experience
```typescript
interface Experience {
  id: string;
  name: string;
  note?: string;
  
  // Workflow et agents
  workflow_id: string;
  workflow_version: string;
  agents: AgentInstance[];
  
  // Profil utilisé
  profile_id: string;
  
  // Progression
  status: 'prepared' | 'pending_approval' | 'running' | 'completed' | 'interrupted' | 'failed' | 'archived';
  checkpoint_id?: string;
  branch_from?: string;
  
  // Résultats
  results?: ExperienceResult;
  
  // Liens Context Tree
  cluster_id?: string;
  parent_branch_id?: string;
  
  // Métadonnées
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

interface AgentInstance {
  agent_id: string;
  persona_id: string;
  role_id: string;
  provider_profile_id: string;
  resource_budget_id?: string;
}

interface ExperienceResult {
  success: boolean;
  artifacts: Artifact[];
  metrics: ExperienceMetrics;
  lessons_learned?: string;
}
```

### Checkpoint
```typescript
interface Checkpoint {
  id: string;
  experience_id: string;
  name: string;
  note?: string;
  
  // État workflow
  workflow_position: string;
  node_states: Record<string, NodeState>;
  intermediate_results?: Result[];
  
  // Contexte
  context_refs: ContextReference[];
  model_metadata: ModelMetadata[];
  
  // Sérialisation
  snapshot_path: string;
  checksum: string;
  
  created_at: string;
}

interface NodeState {
  node_id: string;
  status: 'pending' | 'running' | 'completed' | 'skipped';
  input?: any;
  output?: any;
  duration_ms?: number;
}

interface ContextReference {
  type: 'document' | 'experience' | 'checkpoint' | 'note';
  id: string;
  access_level: 'full' | 'summary' | 'none';
}
```

### Branch
```typescript
interface Branch {
  id: string;
  name: string;
  parent_id?: string;
  root_project_id: string;
  
  // Metadata
  description?: string;
  tags: string[];
  
  // Filiation
  lineage: string[]; // IDs des branches parentes
  
  // Clustering
  cluster_id?: string;
  auto_clustered: boolean;
  
  created_at: string;
  updated_at: string;
}
```

### Cluster
```typescript
interface Cluster {
  id: string;
  name: string;
  description?: string;
  
  // Members
  member_ids: string[]; // IDs des branches/expériences
  
  // Metadata
  tags: string[];
  auto_generated: boolean;
  manual_override: boolean;
  
  created_at: string;
  updated_at: string;
}
```

### Context Graph
```typescript
interface ContextGraph {
  nodes: Map<string,GraphNode>;
  edges: Map<string, GraphEdge>;
  
  // Index par type
  by_type: Record<string, string[]>;
  
  // Index par cluster
  by_cluster: Record<string, string[]>;
}

interface GraphNode {
  id: string;
  type: 'project' | 'cluster' | 'branch' | 'experience' | 'checkpoint' | 'note' | 'discovery' | 'pack' | 'archive';
  label: string;
  metadata: Record<string, any>;
  parent_id?: string;
  cluster_id?: string;
  created_at: string;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: 'classification' | 'lineage' | 'dependency' | 'reference';
  metadata?: Record<string, any>;
}
```

---

## 7. Schéma `.lmpack` Versionné Proposed

### Manifeste
```json
{
  "format": "lmpack",
  "version": "1.0.0",
  "type": "template" | "archive",
  "name": "Nom du Pack",
  "description": "Description...",
  
  // Créateur (facultatif)
  "creator": {
    "id": "uuid-v4",
    "display_name": "eddy1234",
    "profile_url": "https://github.com/eddy1234",
    "visibility": "public" | "anonymous" | "private"
  },
  
  // Provenance
  "provenance": {
    "original_pack_id": "uuid",
    "derived_from": "uuid",
    "license": "MIT-OR-CUSTOM",
    "attribution": "Créé par @eddy1234, adapté par @pixelcraft"
  },
  
  // Contenu
  "components": {
    "personas": ["persona_id_1", ...],
    "roles": ["role_id_1", ...],
    "skills": ["skill_id_1", ...],
    "workflows": ["workflow_id_1", ...],
    "profiles": ["profile_id_1", ...],
    "examples": ["example_id_1", ...]
  },
  
  // Métadonnées
  "metadata": {
    "tags": ["coding", "python", "game-dev"],
    "keywords": ["FPS", "3D", "Unity"],
    "difficulty": "beginner" | "intermediate" | "advanced",
    "estimated_time_minutes": 30,
    "prerequisites": ["basic_python", "git"]
  },
  
  // Préférences modèles (recommandations, pas obligations)
  "model_preferences": {
    "primary": "lm_studio/kwaipilot_kat-coder-v2.5-dev",
    "fallback": ["openrouter/deepseek-v3", "local/llama3"]
  },
  
  // Sécurité
  "security": {
    "requires_docker": false,
    "suggested_permissions": ["read_workspace", "run_tests"],
    "forbidden_operations": ["system_call", "network_access"]
  },
  
  "created_at": "2025-10-15T10:00:00Z",
  "updated_at": "2025-10-15T10:00:00Z"
}
```

### Structure ZIP
```
pack.lmpack
├── manifest.json
├── personas/
│   └── my_persona.txt
├── roles/
│   └── my_role.json
├── skills/
│   └── my_skill.py
├── workflows/
│   └── my_workflow.yaml
├── profiles/
│   └── my_profile.json
├── examples/
│   └── example_1.md
├── notes/
│   └── design_notes.md
└── discoveries/
    └── findings.json
```

---

## 8. Architecture ProviderRegistry / ModelRouter

### ProviderRegistry
```typescript
class ProviderRegistry {
  private providers: Map<string, ProviderDefinition>;
  private credentials: CredentialStore;
  
  register(provider: ProviderDefinition): void;
  get(id: string): ProviderDefinition | undefined;
  list(): ProviderDefinition[];
  testConnection(providerId: string): Promise<boolean>;
}

interface ProviderDefinition {
  id: string;
  type: 'lm_studio' | 'openrouter' | 'openai' | 'xAI' | 'custom';
  name: string;
  endpoint: string;
  auth_type: 'token' | 'oauth' | 'none';
  credentials_profile_id?: string;
  models: ModelInfo[];
  rate_limit?: RateLimit;
}
```

### ModelRouter
```typescript
class ModelRouter {
  private registry: ProviderRegistry;
  private resource_manager: ResourceManager;
  
  route(agentId: string, context: RoutingContext): Promise<RoutingDecision>;
}

interface RoutingContext {
  agent_id: string;
  task_type: 'coding' | 'research' | 'planning' | 'review';
  complexity: number;
  budget: ResourceBudget;
  privacy_level: 'local' | 'cloud_allowed';
}

interface RoutingDecision {
  provider_id: string;
  model_id: string;
  fallback_chain: string[];
  estimated_cost: number;
  estimated_time_ms: number;
}
```

### CredentialStore
```typescript
class CredentialStore {
  private store: SystemCredentialStore; // Windows Credential Manager, keyring, etc.
  
  save(profile_id: string, credentials: Credentials): Promise<void>;
  get(profile_id: string): Credentials | null;
  delete(profile_id: string): Promise<void>;
  list(): string[];
}

interface Credentials {
  api_key: string; // Chiffré, jamais en clair
  endpoint?: string;
  extra_headers?: Record<string, string>;
}
```

### ResourceManager
```typescript
class ResourceManager {
  private profiles: Map<string, ResourceProfile>;
  
  allocate(agent_id: string, budget: ResourceBudget): Promise<Allocation>;
  release(allocation_id: string): void;
  getUsage(agent_id: string): UsageReport;
}

interface ResourceProfile {
  id: string;
  name: string;
  mode: 'economy' | 'balanced' | 'performance' | 'custom';
  budgets: ResourceBudget;
}
```

---

## 9. Politique de Confidentialité et Impacts sur RAW / Audit

### Modes distincts
| Mode | Historique | RAW | Checkpoints | Indexation | Cloud |
|------|-----------|-----|-------------|------------|-------|
| `private_session` | ❌ | ❌ | ❌ (sans consentement) | ❌ | ❌ |
| `local_history` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `full_observatory` | ✅ | ✅ | ✅ | ✅ | ✅ (si autorisé) |

### Impacts sur RAW
- RAW doit respecter la politique de confidentialité de l'expérience
- En mode privé : pas d'écriture RAW, contexte temporaire en mémoire
- En mode local : RAW écrit localement, rétention configurable
- En mode observatoire : RAW + métriques + traces

### Impacts sur Audit
- Audit doit enregistrer les événements minimaux sans contenu sensible
- Les tokens API ne doivent jamais apparaître dans les logs
- Les chemins d'accès aux fichiers privés doivent être masqués
- Rétention audit : configurable (90 jours par défaut)

---

## 10. Plan du Context Tree et Choix Technologique

### Rendu
- **Bibliothèque** : `qgraphicscene` + `qgraphicsvIEW` (Qt native)
- **Virtualisation** : Rendering par tuiles pour grands graphes
- **Interaction** : Zoom/pan fluide, sélection multiple, recherche

### Types de nœuds
| Type | Icône | Action |
|------|-------|--------|
| Project | 📁 | Racine du graphe |
| Cluster | 🗂️ | Regroupement thématique |
| Branch | 🌿 | Branche d'exploration |
| Experience | 🧪 | Exécution identifiée |
| Checkpoint | 💾 | État versionné |
| Note | 📝 | Annotation |
| Discovery | 🔍 | Découverte |
| Pack | 📦 | Archive `.lmpack` |
| Archive | 🗃️ | Archive réduite |

### Clustering automatique
- **Sources** : note initiale, sujet, parent sélectionné, tags, métadonnées
- **Méthode** : Classificateur local (TF-IDF + KMeans) ou règles basées sur métadonnées
- **Correction manuelle** : Drag-drop, fusion, verrouillage

### Création d'expérience depuis un nœud
1. Clic sur nœud → bouton "+ Nouvelle expérience"
2. Fenêtre config s'ouvre
3. Note/objectif, workflow, agents, providers, ressources, confidentialité
4. Confirmation → nouveau nœud apparaît dans l'arbre

---

## 11. Plan Library Indépendante de Docker

### Fonctionnalités
- Parcourir archives `.lmpack`
- Rechercher (mots-clés, tags, créateurs)
- Filtrer (type, date, créateur, licence)
- Trier (nom, date, popularité)
- Lire résumés
- Afficher mots-clés, conclusions, branches, expériences
- Importer / Restaurer / Exporter / Dupliquer / Éditer / Comparer

### Index local
- **Stockage** : SQLite facultatif
- **Source** : Fichiers `.lmpack` (portables)
- **Reconstruction** : Scan répertoire + parsing manifestes

### Restore sans Docker
- Lecture archive ZIP
- Validation manifeste
- Injection dans Context Tree
- Création nœuds correspondants

### Export sans Docker
- Sélection pack → export vers dossier choisi
- Version nettoyée (sans secrets) ou privée (complet)
- Vérification données sensibles avant export

---

## 12. Liste des Fichiers à Créer ou Modifier

### Phase 1 — Fondations de données
| Fichier | Action | Description |
|---------|--------|-------------|
| `data/schemas/profile.ts` | CRÉER | Schéma Profile |
| `data/schemas/experience.ts` | CRÉER | Schéma Experience |
| `data/schemas/checkpoint.ts` | CRÉER | Schéma Checkpoint |
| `data/schemas/branch.ts` | CRÉER | Schéma Branch |
| `data/schemas/cluster.ts` | CRÉER | Schéma Cluster |
| `data/schemas/context_graph.ts` | CRÉER | Schéma Context Graph |
| `data/storage/profile_store.py` | CRÉER | Store Profiles |
| `data/storage/experience_store.py` | CRÉER | Store Experiences |
| `data/storage/checkpoint_store.py` | CRÉER | Store Checkpoints |
| `data/storage/context_graph_store.py` | CRÉER | Store Graph |
| `tests/test_schemas.py` | CRÉER | Tests schémas |
| `tests/test_storage.py` | CRÉER | Tests storage |

### Phase 2 — Providers et ressources
| Fichier | Action | Description |
|---------|--------|-------------|
| `hermes-orchestrator/src/providers/ProviderRegistry.ts` | CRÉER | Registry providers |
| `hermes-orchestrator/src/providers/ModelRouter.ts` | CRÉER | Routage modèles |
| `hermes-orchestrator/src/providers/CredentialStore.ts` | CRÉER | Stockage sécurisé |
| `hermes-orchestrator/src/providers/ResourceManager.ts` | CRÉER | Gestion ressources |
| `tests/test_providers.py` | CRÉER | Tests providers |

### Phase 3 — Context Tree
| Fichier | Action | Description |
|---------|--------|-------------|
| `life_mean_studio/context_tree/tree_widget.py` | CRÉER | Widget arbre |
| `life_mean_studio/context_tree/graph_renderer.py` | CRÉER | Rendu graphique |
| `life_mean_studio/context_tree/cluster_classifier.py` | CRÉER | Classificateur |
| `life_mean_studio/context_tree/experience_creator.py` | CRÉER | Créateur expérience |
| `tests/test_context_tree.py` | CRÉER | Tests tree |

### Phase 4 — LMPACK et Library
| Fichier | Action | Description |
|---------|--------|-------------|
| `library/pack_manager.py` | CRÉER | Gestion packs |
| `library/pack_library.py` | CRÉER | Library locale |
| `library/pack_builder.py` | CRÉER | Pack Builder UI |
| `library/pack_validator.py` | CRÉER | Validation manifests |
| `tests/test_packs.py` | CRÉER | Tests packs |

### Phase 5 — Studio Builder
| Fichier | Action | Description |
|---------|--------|-------------|
| `life_mean_studio/builder/persona_editor.py` | CRÉER | Éditeur persona |
| `life_mean_studio/builder/role_editor.py` | CRÉER | Éditeur rôle |
| `life_mean_studio/builder/skill_editor.py` | CRÉER | Éditeur skill |
| `life_mean_studio/builder/workflow_editor.py` | CRÉER | Éditeur workflow |
| `tests/test_builder.py` | CRÉER | Tests builder |

### Phase 6 — Launcher et Quick Try
| Fichier | Action | Description |
|---------|--------|-------------|
| `launcher/widget.py` | MODIFIER | Widget intégré |
| `launcher/pre_run_dialog.py` | CRÉER | Dialog pré-RUN |
| `launcher/quick_try.py` | CRÉER | Expérience Quick Try |
| `tests/test_launcher.py` | CRÉER | Tests launcher |

### GitHub API
| Fichier | Action | Description |
|---------|--------|-------------|
| `hermes-orchestrator/src/github/GitHubConnector.ts` | CRÉER | Connecteur GitHub |
| `hermes-orchestrator/src/github/RepositoryManager.ts` | CRÉER | Gestion dépôts |
| `life_mean_studio/github/github_panel.py` | CRÉER | Panneau GitHub |

### Identité/Prouvenance
| Fichier | Action | Description |
|---------|--------|-------------|
| `library/creator_registry.py` | CRÉER | Registre créateurs |
| `library/provenance_tracker.py` | CRÉER | Suivi provenance |
| `life_mean_studio/library/creator_panel.py` | CRÉER | Panneau créateurs |

---

## 13. Risques et Migrations

### Risques identifiés
| Risque | Impact | Atténuation |
|--------|--------|-------------|
| Double source de vérité | Corruption données | Un seul store maître (SQLite) |
| Migration schémas | Perte données | Migrations versionnées |
| Compatibilité Windows | Bugs platform | Tests multi-OS |
| Performance grands graphes | Lag UI | Virtualisation rendu |
| Sécurité packs malveillants | Exécution code | Validation stricte ZIP |

### Migrations
- **Phase 0 → 1** : Créer schémas, migrations auto
- **Phase 1 → 2** : Ajouter providers, pas de rupture
- **Phase 2 → 3** : Ajouter UI, backward compatible
- **Phase 3 → 4** : Ajouter packs, format stable
- **Phase 4 → 5** : Ajouter builders, extensions sûres

---

## 14. Tests Prévus

### Unitaires
- `tests/test_schemas.py` — Validation schémas
- `tests/test_storage.py` — CRUD stores
- `tests/test_providers.py` — Registry, routage, credentials
- `tests/test_packs.py` — Import/export, validation, sécurité
- `tests/test_builder.py` — Éditeurs UI
- `tests/test_launcher.py` — Widget, dialog pré-RUN

### Intégration
- `tests/test_context_tree.py` — Navigation, clustering
- `tests/test_github.py` — Connecteur, authentification
- `tests/test_identity.py` — Créateurs, provenance

### Sécurité
- `tests/test_security.py` — Auth, autorisation, Security Gate
- `tests/test_privacy.py` — Modes confidentialité
- `tests/test_packs_security.py` — ZIP bombs, exécution auto

---

## 15. Estimation de Complexité par Phase

| Phase | Complexité | Durée estimée | Dépendances |
|-------|-----------|---------------|-------------|
| 0 — Audit | Faible | 1 jour | — |
| 1 — Fondations | Moyenne | 3-5 jours | Phase 0 |
| 2 — Providers | Moyenne | 3-5 jours | Phase 1 |
| 3 — Context Tree | Haute | 7-10 jours | Phase 1 |
| 4 — LMPACK/Library | Moyenne | 5-7 jours | Phase 1 |
| 5 — Studio Builder | Haute | 7-10 jours | Phase 4 |
| 6 — Launcher | Moyenne | 3-5 jours | Phases 3-5 |
| 7 — Tests/Durcissement | Haute | 5-7 jours | Toutes phases |

**Total estimée : 6-8 semaines**

---

---

## ADDENDUM PHASE 0 — CORRECTIONS ET PRÉPARATION PHASE 1

**Date :** 2025-10-15  
**Statut :** EN ATTENTE D'APPROBATION EXPICITE POUR DÉMARRAGE PHASE 1

---

### 1. Context Graph — Distinction des Relations

Le schéma `ContextGraph` doit explicitement séparer quatre types de relations :

| Type | Nature | Impact | Immutable |
|------|--------|--------|-----------|
| `lineage` | Filiation historique | Expérience → Branche parente | ✅ Jamais modifié |
| `classification` | Cluster thématique | Regroupement sémantique | ❌ Reclassement possible |
| `dependency` | Référence entre connaissances | Dépendance technique | ⚠️ Modification avec précaution |
| `provenance` | Lien pack → composants | Traçabilité origine | ✅ Jamais invalidé |

**Règles d'intégrité :**
- Un reclassement manuel ou automatique ne doit **jamais** changer la filiation (`lineage`) d'une expérience.
- Un reclassement ne doit **jamais** invalider un checkpoint existant.
- Les relations `provenance` sont héritées du manifeste `.lmpack` et figées à l'import.

**Schéma corrigé :**
```typescript
interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: 'lineage' | 'classification' | 'dependency' | 'provenance';
  metadata?: {
    source_type: string;      // 'experience' | 'branch' | 'pack' | ...
    target_type: string;
    strength?: number;        // pondération (0-1)
    provenance_pack_id?: string; // si relation de provenance
  };
}
```

---

### 2. LMPACK et Communauté — Schémas Phase 1

#### Identifiants stables
```typescript
interface PackManifest {
  id: string;                    // UUID v4, stable, jamais modifié
  format_version: '1.0';
  type: 'template' | 'archive';
  name: string;
  description?: string;
  
  // Créateur original (facultatif)
  creator?: CreatorMetadata;
  
  // Provenance et adaptations
  provenance?: ProvenanceChain;
  
  // Contributeurs et adaptations
  contributors?: Contributor[];
  
  // Composants avec licence individuelle
  components: ComponentManifest[];
  
  // Notes distinctes
  notes: {
    creator_note?: string;       // Note du créateur original
    adaptation_note?: string;    // Note d'adaptation (si pack dérivé)
    personal_note?: string;      // Note personnelle (locale, jamais exportée)
  };
  
  // Documentation intégrée
  documentation?: {
    readme: string;
    license_text?: string;
    asset_attribution?: Record<string, string>;  // asset_path → attribution
  };
  
  // Métadonnées de recherche
  search_metadata: SearchMetadata;
  
  // Options d'import
  import_options: ImportOptions;
  
  // Liens communautaires
  community_links?: CommunityLinks;
  
  created_at: string;
  updated_at: string;
}

interface CreatorMetadata {
  id: string;                    // UUID stable, distinct du pseudonyme
  display_name?: string;         // Pseudonyme facultatif
  profile_url?: string;          // Lien GitHub ou communautaire (facultatif)
  visibility: 'public' | 'anonymous' | 'private';
}

interface ProvenanceChain {
  original_pack_id?: string;
  derived_from?: string;         // ID du pack d'origine
  license: 'Apache-2.0' | 'MIT' | 'Custom' | 'Unknown';
  attribution?: string;          // "Créé par @eddy1234, adapté par @pixelcraft"
}

interface Contributor {
  id: string;
  display_name?: string;
  role: 'original_author' | 'contributor' | 'adapter';
  contribution_type: 'persona' | 'role' | 'skill' | 'workflow' | 'asset' | 'documentation';
  license?: string;
}

interface ComponentManifest {
  id: string;                    // UUID stable du composant
  type: 'persona' | 'role' | 'skill' | 'workflow' | 'profile' | 'example' | 'asset' | 'documentation';
  path: string;
  license: 'Apache-2.0' | 'MIT' | 'Custom' | 'Unknown' | 'Proprietary';
  redistributable: boolean;      // Peut-il être redistribué ?
  
  // Assets non redistribuables
  asset_refs?: AssetReference[];
  
  // Métadonnées de recherche pour ce composant
  search_metadata?: SearchMetadata;
}

interface AssetReference {
  path: string;
  type: 'texture' | 'model_3d' | 'sound' | 'music' | 'image' | 'font' | 'other';
  license: string;               // Licence spécifique (ex: "CC-BY-NC-SA-4.0")
  attribution: string;           // Texte d'attribution obligatoire
  redistributable: false;        // Toujours false pour assets externes
}

interface SearchMetadata {
  title: string;
  description?: string;
  tags: string[];
  keywords: string[];
  conclusions?: string;          // Résumé des conclusions/importance
}

interface ImportOptions {
  store_in_library: boolean;     // Conserver le pack complet même après import partiel
  allow_selective_import: boolean;
  require_approval: boolean;
}

interface CommunityLinks {
  original_repository?: string;  // URL GitHub du repo original
  adapted_versions?: string[];   // IDs des adaptations communautaires
  related_packs?: string[];      // IDs des packs liés
}
```

#### Distinction des types de contenu
| Type | Licence | Redistribuable |
|------|---------|----------------|
| Code (`.py`, `.ts`, `.yaml`) | Apache-2.0, MIT | ✅ Oui |
| Documentation (`.md`, `.txt`) | Apache-2.0, MIT | ✅ Oui |
| Données (`.json`, `.csv`) | Variable | ⚠️ Vérifier licence |
| Assets (`.png`, `.fbx`, `.wav`) | Variable | ❌ Par défaut non |

**Règle :** Les assets dont les droits de redistribution sont inconnus ou insuffisants doivent être **exclus par défaut** d'un export communautaire.

---

### 3. Licences et Assets — Règles de Gestion

#### Prise en charge des licences logicielles
- **Apache-2.0** : Requiert attribution, autorise modifications, clause de brevet.
- **MIT** : Plus permissive, attribution seulement.
- **Custom** : Licence spécifique à documenter dans `documentation.license_text`.
- **Unknown** : Interdit export communautaire sans vérification manuelle.

#### Assets — Distinction critique
Les licences Apache-2.0 et MIT **ne couvrent pas automatiquement** :
- Textures (`.png`, `.tga`)
- Modèles 3D (`.fbx`, `.obj`, `.gltf`)
- Sons (`.wav`, `.mp3`)
- Musiques (`.ogg`, `.flac`)
- Polices (`.ttf`, `.otf`)

**Règle :** Chaque asset doit avoir sa propre licence déclarée dans `asset_refs[].license`.

#### Interface d'importation
```typescript
// Ordre d'affichage avant le README
1. AVIS DE LICENCE — Bloc visible en premier
   - Pack license: Apache-2.0
   - Assets non redistribuables: 3 (exclus de l'export)
   - Composants sous licence différente: 2
   
2. README — Documentation du pack
   
3. COMPOSANTS — Liste avec licences individuelles
```

#### Export communautaire
- Assets avec `redistributable: false` → **exclus par défaut**
- Assets avec `license: 'Unknown'` → **exclus par défaut**
- Utilisateur peut surcharger manuellement (avec confirmation)
- **Aucune licence imposée** pour les archives locales privées

---

### 4. Sécurité et Confidentialité — État Vérifié

#### Avant toute implémentation, vérifier :

| Contrôle | État actuel | Action requise |
|----------|-------------|----------------|
| **Authentification routes sensibles** | ✅ Implémenté (`authenticate()`) | Tester avec tokens expirés/révocés |
| **Autorisation backend** | ✅ Implémenté (`authorize()`) | Vérifier rôles OBSERVER/RUNNER/ADMIN |
| **Binding réseau** | ⚠️ localhost only | Confirmer pas d'exposition publique |
| **CORS** | ✅ Strict (origines locales) | Vérifier liste blanche |
| **Security Gate** | ⚠️ Mode DEV auto-approuve | Durcir : exiger approbation manuelle |
| **Politique logs** | ✅ Rotation 90 jours | Vérifier pas de fuites secrets |
| **RAW sessions privées** | ⚠️ Non implémenté | Définir comportement (ne pas écrire) |

#### Politique RAW par mode
| Mode | RAW écrit | Checkpoints | Historique |
|------|-----------|-------------|------------|
| `private_session` | ❌ Non | ❌ Non | ❌ Mémoire only |
| `local_history` | ✅ Local | ✅ Oui | ✅ Oui |
| `full_observatory` | ✅ Local + cloud | ✅ Oui | ✅ Oui |

#### Audit — Ce qui doit être enregistré
- Événements : `AUTH_REQUIRED`, `AUTH_SUCCESS`, `AUTHZ_DENIED`, `SECURITY_GATE_DENY`
- **Jamais** : tokens API, clés, mots de passe, chemins absolus sensibles

---

### 5. Périmètre Phase 1 — Strict

#### Ce qui sera implémenté
| Élément | Fichiers | Description |
|---------|----------|-------------|
| Schémas données | `data/schemas/*.ts` | Profile, Experience, Checkpoint, Branch, Cluster, ContextGraph, PackManifest |
| Stores SQLite | `data/storage/*_store.py` | CRUD pour chaque entité |
| Migrations | `data/migrations/` | Versionning schémas (001_initial.sql) |
| Tests | `tests/test_schemas.py`, `tests/test_storage.py` | Validation schémas, CRUD, intégrité relationnelle |

#### Ce qui NE sera PAS implémenté
- ❌ Docker (pas de build/run/restart)
- ❌ Agents Pi (pas de lancement)
- ❌ Context Tree visuel (UI Phase 3)
- ❌ Library complète (Phase 4)
- ❌ Intégration GitHub (Phase séparée)
- ❌ Configuration LM Studio
- ❌ Modifications routes Hermes existantes

#### Préserver les modifications Git existantes
- Ne pas modifier `code_lab/multiagent.py`
- Ne pas modifier `hermes-orchestrator/src/index.ts`
- Ne pas modifier `run_server.bat`
- Les nouveaux fichiers seront ajoutés sans toucher aux existants

---

### 6. Fichiers Précis à Créer pour Phase 1

#### Schémas Python (`data/schemas/`) — SOURCE DE VÉRITÉ
| Fichier | Contenu |
|---------|---------|  
| `profile.py` | Dataclass Profile, ProviderProfile, ResourceBudget, PrivacyPolicy |
| `experience.py` | Dataclass Experience, AgentInstance, ExperienceResult |
| `checkpoint.py` | Dataclass Checkpoint, NodeState, ContextReference |
| `branch.py` | Dataclass Branch + lineage |
| `cluster.py` | Dataclass Cluster + members |
| `context_graph.py` | Dataclass ContextGraph, GraphNode, GraphEdge (4 types) |
| `pack_manifest.py` | Dataclass PackManifest, CreatorMetadata, ProvenanceChain, ComponentManifest, AssetReference |

#### Types TypeScript générés (`data/schemas/types.ts`)
| Fichier | Contenu |
|---------|---------|  
| `types.ts` | Interfaces TS générées automatiquement depuis Python (script de génération) |

#### Stores Python (`data/storage/`) — Avec politique de confidentialité
| Fichier | Contenu |
|---------|---------|  
| `profile_store.py` | CRUD Profile + ProviderProfile + isolation private_session |
| `experience_store.py` | CRUD Experience + AgentInstance + politique persistance |
| `checkpoint_store.py` | CRUD Checkpoint + NodeState + écriture conditionnelle |
| `branch_store.py` | CRUD Branch + lineage (immutable) |
| `cluster_store.py` | CRUD Cluster + members (classification indépendante) |
| `context_graph_store.py` | CRUD GraphNode + GraphEdge (4 types, indépendants) |
| `pack_store.py` | CRUD PackManifest + validation manifeste + règles redistribution |
| `privacy_policy.py` | Gestion politique confidentialité par store |

#### Migrations SQL (`data/migrations/`)
| Fichier | Contenu |
|---------|---------|
| `001_initial.sql` | Création tables profiles, experiences, checkpoints, branches, clusters, context_graph, pack_manifests |

#### Tests (`tests/`)
| Fichier | Contenu |
|---------|---------|  
| `test_schemas.py` | Validation dataclasses Python, génération types TS, compatibilité |
| `test_storage.py` | CRUD stores, intégrité relationnelle, migrations, politique confidentialité |
| `test_pack_manifest.py` | Validation manifeste, licences, assets, provenance, redistribution |
| `test_privacy.py` | Sessions privées non persistées, isolation RAW/checkpoints, logs séparés |

---

### 7. Checklist Approbation Phase 1

Avant démarrage, confirmer :
- [ ] Schémas Python comme source de vérité (pas de duplication TS manuelle)
- [ ] Distinction lineage/classification/dependency/provenance validée
- [ ] Règles licences : pas de déduction par extension, droits établis par composant
- [ ] Politique confidentialité intégrée dès les stores (private_session, local_history, observability, local_only)
- [ ] Périmètre Phase 1 strict (données uniquement, pas UI, pas Docker)
- [ ] Modifications Git existantes préservées

---

### 8. Validation Avant Livraison Phase 1

Avant déclaration de terminaison, fournir :
- [ ] Fichiers réellement créés et modifiés (liste complète)
- [ ] Tests exécutés avec résultats (`pytest tests/`)
- [ ] Schémas Python et migrations SQL
- [ ] Preuve que `lineage` et `classification` sont indépendants (test relation)
- [ ] Test démontrant qu'une session `private_session` n'écrit pas dans les stores
- [ ] Tests règles de redistribution (assets inclus/exclus selon licence)
- [ ] Limitations connues documentées

---

## PHASE 0 TERMINÉE — EN ATTENTE D'APPROBATION EXPICITE POUR PHASE 1

**Principe central :** Chaque passionné peut partager ses créations, les autres peuvent les réutiliser et les améliorer, et Life_mean conserve une provenance claire sans imposer d'identité publique.

**Note sécurité :** Le Security Gate est implémenté mais le mode DEV auto-approuve doit être durci avant mise en production. Les routes sensibles sont authentifiées mais nécessitent tests de pénétration.
