# AI Debate Research Laboratory — Architecture

**Version:** 1.0  
**Date:** 2026-10-05  
**Status:** Active

---

## 1. Purpose

This document defines the architectural principles and structure for the AI Debate Research Laboratory (`Life_mean`). The goal is to create a **sustainable, modular, traceable, and replaceable** system capable of supporting years of research without the decay patterns observed in previous projects (Mia_Brain, PyBR0S).

The system must enable:
- Rapid experimentation in isolated zones
- Strict stability in core components
- Full provenance tracing from results back to code and configuration
- Human-gated promotion of experimental features

---

## 2. Architectural Principles

| Principle | Description |
|-----------|-------------|
| **High cohesion, low coupling** | Each module has one clear responsibility. Modules communicate via explicit interfaces, not internal implementation details. |
| **Replaceability** | Any component can be swapped for another implementation respecting the same contract, with minimal system impact. |
| **Explicit interfaces** | Dependencies are declared and visible. No implicit coupling. |
| **Deterministic where possible, agentic where useful** | Core logic is deterministic; agent behavior is bounded by contracts. |
| **Traceability** | Every result can be traced back to its code version, configuration, and input data. |
| **Reproducibility** | Experiments can be re-run with identical results given the same inputs. |
| **Human governance** | Promotion of experimental features requires explicit human decision. |

**Architectural Question:**  
*If this component is removed tomorrow and replaced by another implementation respecting the same contract, can the rest of the system continue functioning with minimal modifications?*

If the answer is **no**, document why.

---

## 3. System Map

```
Life_mean/
├── philosophical_council/     # STABLE MODULE — Current working system
│   ├── core/                  # Core: debate orchestration, state, events
│   ├── agents/                # Stable: philosophical agent implementations
│   ├── llm/                   # Stable: LLM provider abstraction
│   ├── memory/                # Stable: multi-tier memory system
│   ├── database/              # Stable: data persistence layer
│   ├── ui/                    # Stable: GUI presentation layer
│   └── config.py              # Stable: configuration management
│
├── hermes-debate/             # LEGACY — Previous iteration
│   └── (kept for reference)
│
├── hermes-orchestrator/       # LEGACY — TypeScript orchestrator
│   └── (kept for reference)
│
├── data/                      # DATA LAYER — Separated from code
│   ├── raw/                   # Immutable experiment outputs
│   ├── processed/             # Derived analysis results
│   ├── metrics/               # Quantitative measurements
│   └── reports/               # Human-readable summaries
│
├── docs/                      # Documentation
│   ├── ARCHITECTURE.md        # This document
│   └── adr/                   # Architecture Decision Records
│
└── tests/                     # Integration and regression tests
```

---

## 4. Core

The Core contains capabilities that are **fundamentally necessary** for the laboratory to function. New features do not enter the Core simply because they work — they must be genuinely foundational.

### Current Core Components

| Module | Responsibility | Stability |
|--------|----------------|-----------|
| `core/debate_engine.py` | Orchestrates debate lifecycle, turn management, moderator decisions | Stable |
| `core/debate_state.py` | Represents debate state (topic, turns, phase) | Stable |
| `core/turn_manager.py` | Manages turn sequencing and round tracking | Stable |
| `core/events.py` | Defines event types for system communication | Stable |

### What Does NOT Belong in Core

- LLM provider implementations (go in `llm/`)
- Agent personality definitions (go in `agents/`)
- Memory consolidation logic (go in `memory/`)
- GUI components (go in `ui/`)
- Experimental protocols (go in `experimental/`)

---

## 5. Stable Modules

These components have reached sufficient maturity and are replaceable via explicit contracts.

### Agents (`agents/`)

Each agent implements the `BaseAgent` interface:

```python
class BaseAgent:
    config: AgentConfig
    name: str
    role: str
    system_prompt: str
    
    def format_response(challenge: str, context: str, ...) -> str
    def add_to_history(response: str) -> None
    def get_history() -> list[str]
```

**Agents:** Existentialist, Stoic, Nihilist, Spiritual, Skeptic, Pragmatist, Moderator

### LLM Provider (`llm/`)

Interface contract:

```python
class LLMClient:
    def chat(messages, model, temperature, max_tokens) -> tuple[str, str]
    def chat_stream(messages, model, temperature, max_tokens) -> Generator[str, None, None]
    def get_models() -> list[str]
```

Current implementation: LM Studio (OpenAI-compatible API)

### Memory System (`memory/`)

Three-tier architecture:

| Tier | Purpose | Lifetime |
|------|---------|----------|
| Short-term | Recent turns for immediate context | Current debate session |
| Mid-term | Structured summaries of debate sections | Created periodically |
| Long-term | Persistent knowledge across sessions | Survives restarts |

### Database (`database/`)

SQLite with repository pattern. Tables:
- `debates` — Debate metadata
- `turns` — Complete turn history (RAW data)
- `memory_short/mid/long` — Memory storage
- `moderator_decisions` — Moderator choices
- `agents` — Agent definitions
- `events` — Lifecycle events

---

## 6. Experimental Zone

**Location:** To be created as `experimental/` when needed.

### Rules

1. Experimental features develop in isolation
2. Stable system never silently depends on experimental code
3. Experiments produce traceable outputs in `data/raw/`
4. Promotion requires human review and ADR documentation

### Current Status

No experimental zone exists yet. The current system (`philosophical_council/`) represents the stable baseline. Future experimental work should be placed in `experimental/` following the lifecycle defined in Section 13.

---

## 7. Legacy Zone

### Components

| Component | Source | Status | Action |
|-----------|--------|--------|--------|
| `hermes-debate/` | Previous Python iteration | LEGACY | Keep for reference, do not modify |
| `hermes-orchestrator/` | TypeScript orchestrator | LEGACY | Keep for reference, do not modify |

### Migration Classification

Components from legacy systems should be classified:

- **KEEP** — Directly usable as-is
- **ADAPT** — Needs modification for new architecture
- **REWRITE** — Fundamental redesign required
- **LEGACY** — Historical reference only
- **IGNORE** — Not relevant
- **SECURITY_REVIEW** — Needs credential audit
- **UNKNOWN** — Requires investigation

---

## 8. Dependency Rules

### Allowed Dependencies

```
Core ← Stable Modules ← Experimental
 ↑           ↑              ↑
 │           │              │
 └──── Data Layer ────────┘
```

### Forbidden Dependencies

- Core MUST NOT depend on Experimental
- Stable modules MUST NOT silently depend on Legacy
- UI MUST NOT depend on LLM implementation details
- Database MUST NOT depend on UI components

### Current Violations

| Violation | Location | Severity |
|-----------|----------|----------|
| `memory/debate_state.py` imports from `core.debate_engine` | Circular import risk | Medium |
| `main.py` hardcodes agent registration | Tight coupling | Low |

---

## 9. Data Architecture

### Directory Structure

```
data/
├── raw/           # Immutable experiment outputs (JSONL)
├── processed/     # Derived analysis results
├── metrics/       # Quantitative measurements
└── reports/       # Human-readable summaries
```

### RAW Data Rules

- RAW data is **immutable** after writing
- If analysis contains an error: create new analysis, do not modify RAW
- Derived data should be reconstructable from RAW
- RAW represents what actually happened during a run

### Run Structure

Each experiment run produces:

```
data/raw/EXP-{id}/RUN-{id}/
├── events.jsonl      # Structured event log
├── config.json       # Experiment configuration
└── metadata.json     # Component versions, timestamps
```

---

## 10. Event Architecture

### Event Format

```json
{
  "event_id": "uuid",
  "experiment_id": "EXP-001",
  "run_id": "RUN-001",
  "event_type": "model_call_completed",
  "timestamp": "2026-10-05T18:30:00Z",
  "component_id": "stoic",
  "component_version": "1.0.0",
  "payload": { ... }
}
```

### Event Types

| Event | Description |
|-------|-------------|
| `debate_started` | New debate initiated |
| `turn_completed` | Agent response generated |
| `moderator_decision` | Speaker selection made |
| `memory_consolidated` | Memory tier updated |
| `error_occurred` | System error |
| `debate_finished` | Debate completed |

---

## 11. Provenance

The laboratory must answer:

- What code produced this result? → Git commit hash
- What version? → Component version in metadata
- What configuration? → `config.json` in run directory
- What models? → Model names in turn records
- What parameters? → Temperature, max_tokens in config
- What tools? → Tool calls in events
- What protocol? → Protocol version in metadata
- What assignment strategy? → Strategy name in config
- What orchestrator? → Orchestrator version in metadata
- What prompts/personas? → Prompt versions in agent config
- What data sources? → Input file paths in metadata
- What RAW? → RAW file references in analysis
- What analysis version? → Analysis version in report
- What metrics? → Metric calculation method in report

### Target Chain

```
Code version + Experiment configuration + Component versions + RAW + Analysis version
→ Metrics → Report
```

---

## 12. Versioning

### Components to Version

- Protocols
- Personas (agent configurations)
- Roles
- Prompts
- Assignment strategies
- Tools
- Analysis methods
- Schemas
- Experiment configurations

### Current Strategy

Simple versioning: semantic versioning for major components, git commits for traceability.

### Future Direction

Consider content-addressable storage for prompts and configurations to enable exact reproducibility.

---

## 13. Feature Lifecycle

```
Idea
  → Experimental implementation
  → Unit tests
  → Integration tests
  → Benchmarks / experiments
  → Results
  → Human review
  → Promote / Modify / Reject / Archive
```

### Promotion Requirements

A feature must document:
- Origin
- Experimental version
- Tests performed
- Relevant benchmarks/experiments
- Results
- Observed limitations
- Reason for promotion
- Date
- New stable destination

**Promotion is never automatic.** Positive benchmarks inform but do not decide.

---

## 14. Testing Strategy

### Test Types

| Type | Purpose | When |
|------|---------|------|
| Unit tests | Verify individual components | Always |
| Contract tests | Verify interfaces | When interfaces change |
| Integration tests | Verify component interaction | Before promotion |
| Characterization tests | Capture legacy behavior | When refactoring legacy |
| Regression tests | Prevent regressions | After bug fixes |

### Current Tests

Located in `philosophical_council/tests/`:
- `test_agents.py` — Agent behavior
- `test_database.py` — Database operations
- `test_debate_engine.py` — Engine logic
- `test_debate_engine_fixes.py` — Bug fix verification
- `test_memory.py` — Memory system
- `test_moderator_flow.py` — Moderator decisions

---

## 15. Architectural Decision Process

### When to Create an ADR

- New major component or module
- Significant change to existing architecture
- Decision with long-term consequences
- Trade-off between alternatives
- Security or privacy decision

### ADR Template

See `docs/adr/ADR_TEMPLATE.md`.

### Decision Record

Major architectural decisions should be recorded in `docs/adr/`.

---

## 16. Anti-patterns

### God Object

An object knows or controls almost everything in the system.

**Avoid:** Monolithic classes that depend on all other modules.

### Hidden Dependency

A module depends implicitly on another.

**Avoid:** Hardcoded paths, implicit globals, undocumented side effects.

### Experimental Leakage

The stable system silently depends on experimental components.

**Avoid:** Importing experimental code in stable paths.

### Persona/Role/Model Fusion

Persona, Role, and Model are coded as a single entity.

**Avoid:** `persona.model = model` — prefer explicit composition.

### Provider Lock-in

The lab depends directly on a specific provider without abstraction.

**Avoid:** Hardcoding LM Studio/Ollama specifics in core logic.

### Mutable RAW

Original results are modified after the experiment.

**Avoid:** Overwriting RAW data to "fix" analysis errors.

### Silent Recovery

An error is corrected without leaving a trace.

**Avoid:** Swallowing exceptions without logging or event recording.

### Magic Configuration

Important parameters are hidden in code.

**Avoid:** Hardcoding temperatures, token limits, thresholds.

### Unversioned Research Artifact

A prompt/protocol/tool changes but experiments don't track which version was used.

**Avoid:** Modifying prompts without version tracking.

### Architecture by Accumulation

A new idea is simply added where it's convenient without checking architectural responsibility.

**Avoid:** Adding features to Core because it's practical.

---

## 17. Feature Checklist

Before implementing a feature, answer:

- [ ] What is its responsibility?
- [ ] Which module does it belong to?
- [ ] Is it Stable or Experimental?
- [ ] What interfaces does it use?
- [ ] What dependencies does it introduce?
- [ ] Can it be replaced?
- [ ] Can it be tested alone?
- [ ] Does it produce events?
- [ ] What data must be preserved?
- [ ] Should it be versioned?
- [ ] Can it affect reproducibility?
- [ ] Does it require an architectural decision?
- [ ] How will it be validated?
- [ ] What criteria would allow promotion?
- [ ] How can it be disabled or removed?

---

## 18. Human-in-the-Loop

The Lab may:
- Measure
- Analyze
- Detect anomalies
- Generate diagnostics
- Propose changes
- Create candidate configurations

The Lab must NOT automatically:
- Modify the Core
- Promote an experimental feature
- Change the official baseline
- Declare a hypothesis scientifically true
- Silently replace a validated method

These actions require **explicit human decision**.

---

## 19. Durability

**Question:** Can this project still be understood and modified reasonably in 5 or 10 years?

This does NOT mean predicting all future technologies. It means stabilizing boundaries.

Example:
- The Lab depends on `ModelProvider`
- Today: `LMStudioProvider`
- Tomorrow: `AnotherProvider`
- Replacing the provider must not require rebuilding `ExperimentEngine`

---

## 20. Do Not Over-Architect

This task does NOT transform the project into a gigantic abstract architecture.

**Avoid:**
- Interfaces without reason
- Dozens of empty directories
- Unnecessary micro-modules
- Complex plugin systems before they're needed
- Speculative abstractions
- Mass migration without tests

**Principle:** Introduce the minimum structure necessary to guarantee good boundaries and enable future evolution.

---

## 21. Data Separation from Code

### Conceptual Architecture

```
data/
├── raw/          # What actually happened
├── processed/    # Derived analysis
├── metrics/      # Quantitative measurements
└── reports/      # Human-readable summaries
```

### RAW Immutability Rule

RAW data represents what actually occurred during a run. It must be treated as immutable after writing.

If the analysis contains an error:
```
RAW original
→ new version of analysis
→ new metrics
→ new report
```

Derived data should ideally be reconstructable from RAW.

---

## 22. Run Structure

Minimum structure for a run:

```
data/raw/EXP-0042/RUN-0001/
├── events.jsonl      # Structured event log
├── config.json       # Experiment configuration
└── metadata.json     # Component versions, timestamps
```

### Required Fields

- Experiment ID
- Run ID
- Repetition ID
- Timestamps
- Configuration
- Component versions
- Events
- Model calls
- Tool calls
- Assignment decisions
- Errors
- Retries
- Recovery events
- Results
- Provenance

---

## 23. Next Steps

1. Create `experimental/` directory when first experimental feature is needed
2. Migrate existing tests to `tests/` root level
3. Add event JSONL logging to debate engine
4. Create run metadata templates
5. Document first ADR for experimental zone creation

---

*This document is living. Review and update with each major architectural decision.*
