# Failure-to-Knowledge Pipeline — Results Summary

## Pipeline Overview

```
FAILED Run
    │
    ▼
FailureAnalyzer (Phase 1)
    │
    ├─► Classifies failure
    ├─► Extracts errors
    └─► Generates candidate causes
    │
    ▼
ComparableRunFinder (Phase 2)
    │
    ├─► Finds similar successful runs
    ├─► Computes comparability scores
    └─► Identifies differences
    │
    ▼
CausalHypothesisEngine (Phase 3)
    │
    ├─► Formulates testable hypotheses
    ├─► Links to evidence
    └─► Proposes falsification tests
    │
    ▼
ControlledExperimentDesigner (Phase 4)
    │
    ├─► Designs minimal experiments
    ├─► Isolates single variables
    └─► Defines success criteria
    │
    ▼
ExperimentExecutionGate (Phase 5)
    │
    ├─► Requires human approval
    ├─► Enforces safety guards
    └─► Tracks execution state
    │
    ▼
ExperimentalKnowledgeExtractor (Phase 6)
    │
    ├─► Extracts immutable knowledge
    ├─► Preserves negative results
    └─► Links to hypotheses
    │
    ▼
FalseSuccessDetector (Phase 7)
    │
    ├─► Detects validator false positives
    ├─► Checks execution evidence
    └─► Explains reasoning
```

---

## New Components Created

| Component | File | Purpose |
|-----------|------|---------|
| `FailureAnalyzer` | `core/debate/failure_analyzer.py` | Classify failures, extract errors, generate causes |
| `ComparableRunFinder` | `core/debate/comparable_run_finder.py` | Find similar runs, compute scores |
| `CausalHypothesisEngine` | `core/debate/causal_hypothesis_engine.py` | Formulate testable hypotheses |
| `ControlledExperimentDesigner` | `core/debate/experiment_designer.py` | Design minimal controlled experiments |
| `ExperimentExecutionGate` | `core/debate/experiment_gate.py` | Control execution with authorization |
| `ExperimentalKnowledgeExtractor` | `core/debate/knowledge_extractor.py` | Extract immutable knowledge records |
| `FalseSuccessDetector` | `core/debate/false_success_detector.py` | Detect validator false positives |

---

## New Event Types (13)

```
FAILURE_ANALYSIS_STARTED
FAILURE_CLASSIFIED
COMPARABLE_RUN_FOUND
CAUSAL_HYPOTHESIS_CREATED
CONTROLLED_EXPERIMENT_PROPOSED
EXPERIMENT_APPROVED
CONTROLLED_EXPERIMENT_STARTED
CONTROLLED_EXPERIMENT_COMPLETED
KNOWLEDGE_RECORD_CREATED
HYPOTHESIS_REFUTED
FALSE_SUCCESS_SUSPECTED
REVALIDATION_REQUESTED
```

---

## Key Behaviors Verified

| Behavior | Status |
|----------|--------|
| No automatic experiment execution | ✅ |
| Authorization required before execution | ✅ |
| Immutable knowledge records | ✅ |
| Negative results preserved | ✅ |
| False success detection | ✅ |
| Comparable run scoring | ✅ |
| Hypothesis status tracking | ✅ |
| Resource limits enforcement | ✅ |

---

## Tests Executed

**Total: 252 passed, 0 failed**

| Test Suite | Count | Status |
|------------|-------|--------|
| test_debate_engine.py | 19 | ✅ |
| test_personas.py | 24 | ✅ |
| test_providers.py | 18 | ✅ |
| test_evidence_layer.py | 20 | ✅ |
| test_safety_layer.py | 20 | ✅ |
| test_debate_engine_comprehensive.py | 43 | ✅ |
| test_debate_engine_enhanced.py | 24 | ✅ |
| test_experience_investigation.py | 28 | ✅ |
| test_persistence_triggers.py | 18 | ✅ |
| test_failure_to_knowledge.py | 38 | ✅ |

---

## Files Created/Modified

| File | Action |
|------|--------|
| `core/debate/failure_analyzer.py` | Created |
| `core/debate/comparable_run_finder.py` | Created |
| `core/debate/causal_hypothesis_engine.py` | Created |
| `core/debate/experiment_designer.py` | Created |
| `core/debate/experiment_gate.py` | Created |
| `core/debate/knowledge_extractor.py` | Created |
| `core/debate/false_success_detector.py` | Created |
| `core/debate/events.py` | Extended (13 new event types) |
| `tests/test_failure_to_knowledge.py` | Created |
| `results/failure_to_knowledge/test_report.json` | Created |

---

## Known Limitations

1. **UI not extended** — `debate_monitor.html` needs Failure Lab view
2. **No external run data** — analysis uses synthetic test cases
3. **Keyword matching only** — semantic search not implemented for comparable runs
4. **No causal inference** — hypotheses require experimental verification
