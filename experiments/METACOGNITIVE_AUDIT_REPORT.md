# Metacognitive Architecture Audit Report

**Project**: Life_mean  
**Date**: 2026-10-27  
**Version**: v1.3 (metacognitive evolution)

---

## Phase 1: Architecture Cartography

### Current Code Lab Pipeline

```
PLANNER → DEVELOPER → VERIFIER → CRITIC → REPAIR → VALIDATE → RAW
    ↓         ↓           ↓        ↓        ↓          ↓
  Template  LLM/Gen     pytest   Critique Fix       Compile
              Code                      Attempts
```

**Key Components**:
- `code_lab/engine.py`: Orchestrates the pipeline (1138 lines)
- `code_lab/config.py`: Configuration with versioned role templates
- `code_lab/workspace.py`: Isolated workspace management
- `code_lab/event_logger.py`: Structured event logging
- `experiments/metacognition/`: NEW - Metacognitive analysis layer

### Data Flow Architecture

| Layer | Component | Purpose |
|-------|-----------|---------|
| **Input** | CodeLabConfig | Prompt, constraints, template selection |
| **Routing** | SmartRouter | Keyword-based task classification |
| **Execution** | CodeLabEngine | Pipeline orchestration |
| **Validation** | OracleValidator | Deterministic compile checks |
| **Provenance** | EventLogger + RAW | Immutable run snapshots |
| **Analysis** | MetacognitiveMonitor | Post-hoc pattern detection |

### Identified Gaps

1. **No persistent memory**: Run outcomes not stored for cross-run analysis
2. **No error pattern detection**: Recurring failures not tracked
3. **No strategy comparison**: Router effectiveness unmeasured
4. **No agent disagreement tracking**: Multi-agent conflicts unrecorded

---

## Phase 2: Metacognitive Memory Module (COMPLETED)

### New Module: `experiments/metacognition/`

```
experiments/metacognition/
├── __init__.py          # Package exports
├── schemas.py           # RunMemory, ErrorPattern, StrategyComparison
├── memory.py            # MetacognitiveMemory (persistent storage)
├── monitor.py           # MetacognitiveMonitor (analysis engine)
└── analysis.py          # Analysis utilities (similarity, root causes)
```

### Key Classes

**RunMemory**: Stores complete run metadata
- Run ID, project, status
- Prompt, constraints, domain classification
- Agent traces, judge decisions
- Errors detected, corrections applied
- Duration, iterations, timestamps

**MetacognitiveMemory**: Persistent storage
- Thread-safe JSON persistence
- Cross-run query by project/run
- Error pattern detection
- Strategy comparison storage

**MetacognitiveMonitor**: Analysis engine
- Run analysis (success/failure diagnostics)
- Recurring error detection
- Verdict-to-test comparison
- Domain effectiveness mapping
- Context drift detection

### Integration with Code Lab Engine

Modified `code_lab/engine.py`:
- Added `_save_metacognitive_memory()` method
- Hooked into `_finalize()` after result computation
- Graceful fallback if module unavailable

---

## Phase 3: Metacognitive Monitor (COMPLETED)

### Analysis Capabilities

| Analysis | Purpose | Output |
|----------|---------|--------|
| `analyze_run()` | Single run diagnostics | Issues + recommendations |
| `detect_recurring_errors()` | Cross-run error patterns | Error types with counts |
| `compare_verdicts_to_tests()` | Judge reliability | Accuracy metrics |
| `identify_domain_effectiveness()` | Configuration performance | Success rates by domain |
| `detect_context_drift()` | Prompt adherence | Drift severity |

### Example: Run Analysis Output

```json
{
  "run_id": "codelab_51410ad69b",
  "status": "failed",
  "success": false,
  "issues": [
    {
      "type": "empty_response",
      "agent": "DEVELOPER",
      "message": "DEVELOPER returned empty/phantom output"
    }
  ],
  "recommendations": [
    "Check DEVELOPER prompt and model context length"
  ]
}
```

---

## Phase 4: Cluster Tree Visualization (PLANNED)

### Design

Interactive visualization of run relationships:
- **Nodes**: Individual runs (colored by status)
- **Edges**: Similarity connections (computed via analysis)
- **Clusters**: Groups of similar runs (hierarchical)
- **Filters**: By domain, status, error type

### Implementation Plan

1. Export run data to JSON from MetacognitiveMemory
2. Compute similarity matrix using analysis utilities
3. Apply hierarchical clustering (sklearn or pure Python)
4. Render as interactive HTML with D3.js or similar

---

## Phase 5: Controlled Router Improvement (PLANNED)

### Current State

- SmartRouter uses keyword matching for task classification
- No feedback loop from run outcomes
- Template selection is manual

### Proposed Improvements

1. **Outcome-aware routing**: Use success/failure rates to adjust routing
2. **Template recommendation**: Suggest templates based on historical performance
3. **Configuration optimization**: Auto-tune role_models based on domain

### Implementation Plan

1. Extend SmartRouter with metacognitive feedback
2. Add routing decision history tracking
3. Implement A/B testing framework for strategy comparison

---

## Phase 6: Experimental Strategy Comparison (PLANNED)

### Design

Compare routing strategies across controlled experiments:
- **Strategy A**: Current SmartRouter (keyword-based)
- **Strategy B**: Metacognitive-enhanced router (outcome-aware)
- **Metrics**: Success rate, latency, error patterns

### Implementation Plan

1. Create experimental runner with strategy parameterization
2. Run controlled comparisons
3. Store results in MetacognitiveMemory
4. Generate comparison reports

---

## Phase 7: Metacognitive Dashboard (PLANNED)

### UI Components

1. **Run Timeline**: Chronological view of all runs
2. **Error Heatmap**: Visualize recurring failures
3. **Strategy Comparison**: Side-by-side performance charts
4. **Domain Effectiveness**: Success rates by project type
5. **Agent Disagreement**: Track multi-agent conflicts

### Integration

- REST API endpoints for metacognitive data
- WebSocket updates for real-time analysis
- Export to JSON/CSV for offline analysis

---

## Phase 8: Security and Integrity (IN PROGRESS)

### Current State

- RAW provenance ensures immutable run records
- Event logging provides structured audit trail
- Metacognitive memory is isolated from core engine

### Risks Identified

1. **Memory tampering**: JSON storage could be corrupted
2. **Data leakage**: Sensitive prompts stored in plaintext
3. **Analysis bias**: Pattern detection may reinforce existing biases

### Mitigations

1. Add checksums to metacognitive memory files
2. Sanitize sensitive data before persistence
3. Document analysis assumptions and limitations

---

## Phase 9: Tests (COMPLETED)

### Test Coverage

- **16 new tests** in `tests/test_metacognition.py`
- All existing tests passing (1058 total, 4 pre-existing failures)
- Metacognitive memory integration verified

### Test Categories

| Category | Tests | Coverage |
|----------|-------|----------|
| RunMemory schema | 3 | Roundtrip, defaults |
| MetacognitiveMemory | 6 | CRUD, patterns, comparisons |
| MetacognitiveMonitor | 5 | Analysis, detection, reporting |
| ErrorPattern schema | 1 | Serialization |
| StrategyComparison schema | 1 | Serialization |

---

## Summary

### Completed

- ✅ Phase 2: Metacognitive memory module
- ✅ Phase 3: Metacognitive monitor
- ✅ Phase 9: Tests for new modules

### In Progress

- 🔄 Phase 8: Security and integrity (documentation)

### Planned

- ⏳ Phase 1: Audit report (this document)
- ⏳ Phase 4: Cluster tree visualization
- ⏳ Phase 5: Controlled router improvement
- ⏳ Phase 6: Experimental strategy comparison
- ⏳ Phase 7: Metacognitive dashboard

### Key Decisions

1. **Isolated storage**: Metacognitive memory separate from RAW provenance
2. **Graceful degradation**: Engine continues if memory save fails
3. **Thread safety**: RLock for concurrent access
4. **Persistent JSON**: Simple, human-readable format

---

## Next Steps

1. Implement cluster tree visualization (Phase 4)
2. Add router feedback loop (Phase 5)
3. Create experimental runner (Phase 6)
4. Build dashboard UI (Phase 7)
5. Complete security documentation (Phase 8)
