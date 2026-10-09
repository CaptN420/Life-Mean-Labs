# Design Update Summary — AUTONOMOUS_SYNTHETIC_DATA_GENERATOR.md

**Date:** 2026-10-07  
**Status:** ✅ DESIGN UPDATED

---

## What Changed

The design document was extended from 25 sections to **47 sections**, adding critical architectural principles and constraints for the Synthetic Data Lab.

### New Sections Added

| Section | Title | Key Contribution |
|---------|-------|------------------|
| 25 | The Lab as a Synthetic Data Lab | Complete research lifecycle: Generate → Diversify → Solve → Validate → Build Dataset → Train Candidate → Benchmark → Analyze Weaknesses → Generate Next Curriculum |
| 26 | Multi-Agent Layer as Solver/Teacher Engine | Existing multi-agent system becomes the execution engine; generator creates work, solver solves it |
| 27 | Human Tasks and Generated Tasks Share Execution Path | `result = await orchestrator.run(task)` — no special logic for generated tasks |
| 28 | Experiment Context / Provenance | Complete traceability from dataset example → run → task → generator config → router → workers → tools → validation evidence |
| 29 | Multi-Agent Trajectories Are Data | Final answer is NOT the only useful output; one run produces multiple training signals (SFT, preference, critic, repair, verifier, router, difficulty, tool-use) |
| 30 | Agent Roles During Data Generation | PROPOSER, SOLVER, CRITIC, ADVERSARY, REVIEWER, JUDGE, VERIFIER — roles distinct from implementations |
| 31 | Generator-Side Multi-Agent System | V1: Python Task Generator → Multi-Agent Solver; Future: Generator Agents; WARNING: evaluation leakage risk |
| 32 | Deterministic Oracles | Code oracle, math oracle, structured data oracle; LLM Judge NEVER silently replaces deterministic oracle |
| 33 | Failure Bank as First-Class Data | Failed trajectories stored for repair/critic/preference/adversarial/weakness datasets |
| 34 | Autopilot by Generations | Bounded generations with quality gates; stable model NOT automatically overwritten |
| 35 | Potentially Indefinite Autopilot | INDEFINITE EXECUTION ≠ INDEFINITE IMPROVEMENT; system may plateau, overfit, lose diversity, amplify errors, experience model collapse |
| 36 | Autopilot Stop Conditions | Explicit stop/pause conditions: GPU budget, generation count, wall-clock, disk space, quality thresholds, novelty thresholds, benchmark regression, manual emergency stop |
| 37 | Model Registry / Candidate Promotion | STABLE MODEL vs CANDIDATE MODEL vs REJECTED MODEL; full model lineage tracking |
| 38 | Training Must Remain Separate from Generation | Six distinct stages: GENERATION → VALIDATION → DATASET BUILD → TRAINING → BENCHMARK → PROMOTION |
| 39 | Dataset Versioning | Immutable/versioned datasets; never silently mutate training data |
| 40 | Adaptive Curriculum (Expanded) | Weakness analysis from held-out evaluation; NOT from same synthetic tasks used for training |
| 41 | Diversity Pressure | Track lexical/structural/semantic novelty, domain/difficulty/reasoning-type/tool-use distributions, worker utilization, solution-path diversity |
| 42 | Experimental A/B Testing | Controlled comparisons to answer whether deterministic tools actually improve synthetic dataset |
| 43 | Lab UI Evolution | Three major areas: GENERATION controls, DATASETS display/actions, TRAINING/MODELS display/actions |
| 44 | Full Target Architecture | Complete Mermaid diagram showing all components and their relationships |
| 45 | Scientific Principle | "The goal is NOT to make a system that continuously convinces itself that it is improving" — test against independent evidence |
| 46 | Updated Implementation Phases | 12 phases (0-12) with explicit acceptance criteria, tests, rollback considerations, observability, reproducibility requirements |

---

## Concepts Mapping to Existing Code

| Concept | Existing Component | Location |
|---------|-------------------|----------|
| Orchestrator | `core/runtime/orchestrator.py` | ✅ COMPLETE |
| EventBus | `core/events/event_bus.py` | ✅ COMPLETE |
| SmartRouter | `core/assignment/router.py` | ✅ COMPLETE |
| ToolWorker | `core/workers/tool.py` | ✅ COMPLETE |
| Deterministic Tools | 59 tools in `library/tools/{math,chemistry,physics,coding,logic}/` | ✅ COMPLETE |
| Personas | `library/personas/` (philosophy, science, data) | ✅ COMPLETE |
| Reflection Protocols | `library/protocols/reflection.py` | ✅ COMPLETE |
| Stagnation Detection | `library/protocols/stagnation.py` | ✅ COMPLETE |
| Reliability Layer | `library/reliability/{context,fallback,manager}.py` | ✅ COMPLETE |
| JudgeAgent | (assumed exists) | ✅ ASSUMED |
| Validators | (assumed exists) | ✅ ASSUMED |

---

## Concepts Requiring New Modules

| Concept | Proposed Module | Phase |
|---------|----------------|-------|
| Experiment Context | `experiments/context.py` | Phase 1 |
| Task Generator | `experiments/generation/task_generator.py` | Phase 1 |
| Diversifier | `experiments/generation/diversifier.py` | Phase 2 |
| Novelty/Dedup | `experiments/generation/novelty.py` | Phase 2 |
| Experiment Runner | `experiments/runner.py` | Phase 3 |
| Failure Bank | `experiments/failure_bank.py` | Phase 4 |
| Deterministic Oracle | `experiments/validation/oracle.py` | Phase 4 |
| Dataset Builder | `experiments/dataset_builder.py` | Phase 5 |
| Dataset Registry | `experiments/registry.py` | Phase 5 |
| Quality Gate | `experiments/quality_gate.py` | Phase 7 |
| Trainer Integration | `experiments/trainer.py` | Phase 8 |
| Model Registry | `experiments/model_registry.py` | Phase 8 |
| Promotion System | `experiments/promotion.py` | Phase 9 |
| Weakness Analyzer | `experiments/analysis/weakness.py` | Phase 10 |
| Curriculum Controller | `experiments/autopilot/curriculum.py` | Phase 10 |
| Autopilot | `experiments/autopilot/controller.py` | Phase 11-12 |

---

## Architectural Conflicts Identified

### 1. EventBus Propagation of Metadata
**Conflict:** The existing EventBus may not propagate experiment context/metadata cleanly.  
**Impact:** Requires investigation of whether current event schema supports `experiment_id`, `generation_id`, `task_id`, `run_id`.  
**Resolution:** Investigate in Phase 1; may require EventBus extension or parallel metadata tracking.

### 2. Role vs Implementation Distinction
**Conflict:** The design requires explicit role/implementation distinction, but existing workers may not support role-based behavior.  
**Impact:** May require adding a `role` parameter to worker initialization or creating role-specific wrappers.  
**Resolution:** Document as a V1 constraint; implement in Phase 3 if needed.

### 3. Deterministic Oracle Priority
**Conflict:** The design states "LLM Judge should NEVER silently replace deterministic oracle," but existing validation logic may not enforce this.  
**Impact:** Requires audit of current validation pipeline to ensure deterministic oracles are checked first.  
**Resolution:** Audit in Phase 4; may require validation layer reordering.

### 4. Failure Bank Storage
**Conflict:** The design requires storing failed trajectories, but RAW storage schema may not support trajectory metadata.  
**Impact:** May require extending RAW storage to include failure context (validator error, critique, corrected candidate).  
**Resolution:** Investigate in Phase 4; may require database schema extension.

### 5. Model Lineage Tracking
**Conflict:** The design requires full model lineage (parent model, training dataset, configuration, benchmark results, promotion decision), but no existing registry exists.  
**Impact:** Requires building a new model registry from scratch.  
**Resolution:** Implement in Phase 8; document as new module.

---

## What Should NOT Be Implemented As Originally Imagined

### 1. Naive Infinite Autopilot
**Original idea:** `while True: generate(); train()`  
**Why not:** System may plateau, overfit, lose diversity, amplify errors, exploit validator weaknesses, experience model collapse.  
**Correct approach:** Bounded generations with quality gates and explicit stop conditions (Section 34-36).

### 2. Generator-Side Multi-Agent in V1
**Original idea:** Generator agents create tasks and solve them.  
**Why not:** Evaluation leakage — same agent creates task, knows solution, appears successful.  
**Correct approach:** V1 = Python Task Generator → Multi-Agent Solver; future mode with generator agents (Section 31).

### 3. LLM Judge Replacing Deterministic Oracle
**Original idea:** Use LLM Judge for validation when available.  
**Why not:** Self-confirming data risk; deterministic oracles provide independent evidence.  
**Correct approach:** Deterministic oracle first, LLM Judge only as fallback (Section 32).

### 4. Curriculum from Synthetic Tasks
**Original idea:** Generate curriculum based on synthetic task performance.  
**Why not:** Contamination — same tasks used for training and weakness analysis.  
**Correct approach:** Weakness signals from held-out evaluation (Section 40).

### 5. Silent Dataset Mutation
**Original idea:** Update datasets as new information becomes available.  
**Why not:** Training data integrity; models trained on different versions become incomparable.  
**Correct approach:** Immutable/versioned datasets (Section 39).

---

## Next Smallest Implementation Step

**Phase 1: Experiment Schemas + Task Generator**

1. Create `experiments/context.py` with `ExperimentContext` dataclass
2. Create `experiments/generation/schemas.py` with `GeneratedTask` schema
3. Create `experiments/generation/task_generator.py` with `TaskGenerator` class
4. Implement provenance tracking (experiment_id → generation_id → task_id → run_id)
5. Write tests in `tests/test_phase1_task_generator.py`

**Acceptance Criteria:**
- [ ] TaskGenerator can generate 100 tasks with unique IDs
- [ ] Each task includes domain, difficulty, seed, generator_version
- [ ] ExperimentContext preserves all metadata
- [ ] Provenance chain is traceable: dataset_example → run → task → generator_config

**Rollback Considerations:**
- If EventBus cannot propagate metadata, implement parallel metadata tracking in ExperimentContext

**Observability Requirements:**
- Log every generated task with full provenance
- Track generation statistics (domain distribution, difficulty distribution)

**Reproducibility Requirements:**
- Same seed + same generator_version → same task sequence
- Store generator_version in dataset metadata

---

## Summary of Key Principles

1. **Reuse existing components** — SmartRouter, ToolWorker, Personas, Protocols
2. **Separate generation from training** — Export JSONL, no automatic fine-tuning
3. **Preserve provenance** — Every example traceable to its run
4. **Prevent contamination** — Strict data splits; held-out evaluation for weakness analysis
5. **Protect against self-confirming data** — Deterministic validation preferred over LLM Judge
6. **Separate solver from generator** — Avoid evaluation leakage
7. **Independent stage control** — Each phase runnable in isolation
8. **Model lineage tracking** — Promote/reject with full history
9. **Bounded generations** — No naive infinite loops; explicit stop conditions
10. **Immutable datasets** — Never silently mutate training data

---

*Design document updated: 2026-10-07*  
*Status: READY FOR PHASE 1 IMPLEMENTATION*
