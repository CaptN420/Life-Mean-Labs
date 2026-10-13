# Architecture Notes: MIA v0 Prototype

## Design Philosophy

MIA was built on the **Captn** framework principle: separate "The Brain" (orchestration) from "The Hands" (execution). This is documented in `ARCHITECTURE.md`:

> "Project Captn is a Deterministic Agent Runtime designed to move beyond simple AI prompts toward a robust execution ecosystem."

## Key Architectural Patterns

### 1. The Brain and Hands Model
- **Brain**: `BaseDebateCore` — handles planning, state management, routing
- **Hands**: Orchestrator classes (`EquationDebateOrchestrator`, etc.) — execute specific tasks
- **Bloodstream**: JSON messages between components (strict structure)

### 2. Plugin System
Capabilities provided via plugins:
- **Logic Plugins**: Debate, Evolution, Repair behaviors
- **Tool Plugins**: File system, web search, code execution

### 3. Deterministic Runtime Guarantees
- Session isolation (each project has own workspace/memory)
- Rollback mechanism (failed changes can be reverted)
- State persistence (`shared_research_memory.json`)

## Module Responsibility Map

| Module | Responsibility | Historical Note |
|--------|----------------|-----------------|
| `base_debate_core.py` | Core orchestration loop | 953 lines — the "brain" |
| `equation_debate_orchestrator.py` | Equation-level debate | 49KB — most complex orchestrator |
| `variable_debate_orchestrator.py` | Variable validation | 51KB — parallel to equation debates |
| `repair_equation_orchestrator.py` | Automated repair | 14KB — "Chymicus" role |
| `mutation_equation_orchestrator.py` | Directed evolution | 36KB — "mutation" operator |
| `shared_memory.py` | Persistent state | 1.2MB — memory corruption risk |
| `ollama_client.py` | LLM interface | Includes truncation detection |

## Data Flow

```
User Input
    ↓
BaseDebateCore.__init__()
    ↓
Random theme + question selection (themes.py)
    ↓
Debate loop:
    1. Generate candidate (Aurelius role)
    2. Validate (HermesValidator role)
    3. If rejected → Repair (Chymicus role)
    4. If valid → Archive (Archiviste role)
    5. If promising → Mutate (Mutation role)
    ↓
Update shared_research_memory.json
    ↓
Next turn or session end
```

## Known Architectural Debt

1. **Tight coupling**: Orchestrators directly import from `base_debate_core`
2. **Memory bloat**: No cleanup of stale candidates
3. **Hardcoded roles**: Agent names tied to alchemy metaphor
4. **No versioning**: Memory format not versioned — migration risk

## Evolution Path

This architecture directly influenced modern Life_mean:
- `BaseDebateCore` → `DebateLab` executor pattern
- `SharedResearchMemory` → Experiment layer with versioning
- Hardcoded roles → `RoleTemplate` system with `executor_type` dispatch

---

*Preserved as-is. Do not modernize.*
