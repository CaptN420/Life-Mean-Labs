# MIA — Historical Snapshot: v0 Alchemy Multi-Agent Prototype

## 1. WHAT THIS VERSION WAS

**MIA (Multi-Agent Intelligence Alchemy)** was the earliest experimental prototype in the Life_mean lineage. It explored whether multiple specialized AI agents could collaboratively generate, validate, repair, and evolve symbolic equations through a structured debate process.

This was **not** a production system — it was a research laboratory built to answer: *Can we create an autonomous alchemical workflow where agents play distinct philosophical roles (generator, validator, repairer, mutator, archivist) and produce emergent mathematical insights?*

The prototype used local LLMs via Ollama (Qwen 2.5:3b quantized) and ran on a Windows workstation with dual GPUs (3080 12GB + 3070 Ti 8GB).

---

## 2. WHAT IT WAS TRYING TO LEARN

| Hypothesis | Method |
|------------|--------|
| Multi-agent debate produces more robust equations than single-agent generation | Structured debate rounds with role specialization |
| Agents can self-correct through repair/mutation cycles | Automated repair orchestrators + mutation operators |
| Persistent memory enables cumulative learning | `shared_research_memory.json` tracking approved/rejected candidates |
| Deterministic orchestration reduces LLM randomness | Session isolation, rollback mechanisms, validation gates |

**Key experimental question:** Could the "alchemy" metaphor (generate → validate → repair → mutate → archive) produce genuinely novel equation candidates, or merely recombine existing knowledge?

---

## 3. ARCHITECTURE AT THE TIME

```
┌─────────────────────────────────────────────────────────────┐
│                    MIA ORCHESTRATION LAYER                   │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  Generator   │  │  Validator   │  │  Repairer    │       │
│  │ (Aurelius)   │  │(HermesVal.) │  │ (Chymicus)   │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
│         │                 │                  │               │
│         ▼                 ▼                  ▼               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           BASE_DEBATE_CORE (Orchestration)            │   │
│  │  - Manages debate turns                               │   │
│  │  - Routes to appropriate orchestrator                 │   │
│  │  - Enforces prompt guardrails                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              SHARED RESEARCH MEMORY                   │   │
│  │  - approved_variables/                                │   │
│  │  - candidate_variables/                               │   │
│  │  - approved_equations/                                │   │
│  │  - rejected_fragments/                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Agent Roles (Philosophical Archetypes)

| Agent | Role | Function |
|-------|------|----------|
| **Aurelius** | Generator | "What if we tried this?" — proposes new equation candidates |
| **HermesValidator** | Validator | "Non." — checks units, causal roles, consistency |
| **Chymicus** | Repairer | "I can fix that." — repairs rejected equations |
| **Archiviste** | Archivist | "I'll keep this just in case." — persistent memory management |
| **Sentinelle** | Sentinel | "I told you this would break." — monitors chaos, logs failures |

### Core Modules

- `base_debate_core.py` — Main orchestration loop, turn management
- `equation_debate_orchestrator.py` — Equation-level debate logic
- `variable_debate_orchestrator.py` — Variable definition/validation debates
- `repair_equation_orchestrator.py` — Automated repair attempts
- `mutation_equation_orchestrator.py` — Directed evolution of promising candidates
- `shared_memory.py` — Persistent state management (the "bloodstream")
- `memory_store.py` — Debate state persistence
- `ollama_client.py` — Local LLM interface with truncation detection

---

## 4. IMPORTANT FAILURES / LIMITATIONS OBSERVED

### Failure 1: LLM Output Truncation
**Symptom:** Models would cut off mid-equation, producing malformed output ending in `:` or `-`.
**Impact:** Validation failures, corrupted memory state.
**Evidence:** `_looks_truncated()` method in `ollama_client.py` with extensive heuristics for detecting incomplete outputs.

### Failure 2: Non-Deterministic Agent Routing
**Symptom:** Same input could produce different agent assignments due to defaultdict mutation.
**Impact:** Unreliable debate outcomes, difficult to reproduce experiments.
**Evidence:** Commit `808fa51` in current Life_mean history references "Fix nondeterministic should_prevent_speaker (defaultdict mutation)" — a direct descendant of this issue.

### Failure 3: Memory State Corruption
**Symptom:** Long-running sessions would accumulate stale candidate variables that never got cleaned up.
**Impact:** Memory bloat, degraded performance, false positives in validation.
**Evidence:** Multiple `*_memory.json` files in `JEFF_MEMORIES/` showing accumulation patterns.

### Failure 4: GPU VRAM Exhaustion
**Symptom:** 12-agent discussions would OOM on the 3080 12GB.
**Impact:** Crashes during critical debate phases.
**Evidence:** Config注释 "EXCLUSIVE VRAM USAGE: No RAM offloading" — workaround was reducing to 3B models.

---

## 5. WHAT THOSE FAILURES LED TO

| Failure | Modern Life_mean Solution |
|---------|---------------------------|
| Truncation detection | `debate_code` executor with symmetric trace (commit `987eb67`) |
| Non-deterministic routing | Deterministic `ModelRegistry.get_by_name()` (commit `6a899b8`) |
| Memory corruption | RoleTemplate system with strict validation (commit `cb4ccbf`) |
| VRAM exhaustion | Unified per-domain model pools (commit `35fda90`) |

**Key insight:** The failures revealed that **determinism and traceability** were more important than raw generative power. This led to the modern "debate_code" pattern where every debate step is logged, reversible, and symmetric across modes.

---

## 6. CONCEPTS THAT SURVIVED INTO MODERN LIFE_MEAN

| Historical Concept | Modern Equivalent | Evidence |
|--------------------|-------------------|----------|
| `SharedResearchMemory` | `experiments/memory/` + `role_templates/` | Architecture lineage preserved |
| Agent role specialization | `executor_type` dispatch (code_lab/debate/general_reasoning) | Commit `cb4ccbf` |
| Prompt guardrails | `prompt_guard.py` → modern validation layer | Direct code evolution |
| Session isolation | Workspace-per-experiment pattern | Core design principle |
| Repair/mutation cycles | `debate_code` chain: DEBATE→SPEC→CODE→VERIFY | Commit `5635d83` |

---

## 7. CONCEPTS THAT WERE LATER REPLACED

| Historical Concept | Why Replaced | Modern Replacement |
|--------------------|--------------|-------------------|
| Hardcoded agent names (Aurelius, Chymicus) | Too specific to alchemy metaphor; not generalizable | Generic `executor_type` dispatch |
| Ollama-specific client | Vendor lock-in; limited model selection | Abstract `ModelRegistry` with multiple backends |
| Single shared memory file | Scalability issues; corruption risk | Distributed experiment state + versioning |
| Manual theme selection | Limited experimental scope | Automated topic generation + hypothesis testing |
| Windows-only UI (wxPython) | Portability constraints | Web-based UI (modern Life_mean dashboard) |

---

## 8. WHAT IS HISTORICAL CONTEXT VS SCIENTIFIC CLAIM

### Historical Context (Experimental Setup)
- Dual GPU workstation (3080 + 3070 Ti) — machine-specific
- Qwen 2.5:3b quantized models — model choice reflects VRAM constraints
- Alchemy/philosophical terminology — metaphorical framing, not scientific claim
- "Vibe coding" development approach — informal, exploratory methodology

### Scientific Claims (What the Experiment Demonstrated)
- Multi-agent debate can produce novel equation candidates ✓
- Role specialization improves validation rigor ✓
- Persistent memory enables cumulative learning (with caveats) △
- Automated repair reduces rejection rates ✓

**Important:** The equations produced were **not** validated as scientifically true. They are historical artifacts of an experimental process, not results claiming scientific validity.

---

## Source References

- Original source: `legacy/MIA-LABS-main/MIA-LABS-main/MIA-LABS-main/mia/`
- Architecture documentation: `ARCHITECTURE.md`, `README.txt`
- Memory state examples: `JEFF_MEMORIES/alchemy_session_*/`
- Git history lineage: Current Life_mean commits `808fa51` through `987eb67`

---

*This snapshot preserves the architectural evolution. The mistakes are documented because they explain why the modern architecture changed.*
