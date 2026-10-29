# Experience Investigation — Results Summary

## Architecture Identified

### Existing Components Reused
- `DebateEngine` — core debate logic
- `ProvenanceGraph` — evidence relationship tracking
- `DeterministicArbiter` — rule-based decision making
- `ContradictionDetector` — contradiction detection (v2)
- `PolicyGuard` / `ResourceGuard` / `IncidentManager` — safety layer

### New Modules Created
| Module | Purpose |
|--------|---------|
| `core/debate/experience_registry.py` | Immutable experience storage and retrieval |
| `core/debate/evidence_impact.py` | Trace consequences of evidence changes |
| `core/debate/deepening_engine.py` | Propose follow-up investigations |
| `core/debate/enhanced_contradiction_detector.py` | Precise contradiction classification |

### Existing Modules Extended
- `core/debate/engine.py` — `ReplayEngine` now supports `historical_replay()` and `deep_investigation()` modes
- `core/debate/events.py` — 13 new event types for experience lifecycle

---

## Tests Executed

**Total: 196 passed, 0 failed**

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

---

## Replay Results

### Historical Replay (Mode A)
```json
{
  "mode": "HISTORICAL_REPLAY",
  "deterministic": true,
  "original_decision": "VERIFIED",
  "replayed_decision": "VERIFIED"
}
```

### Deep Investigation (Mode B)
```json
{
  "mode": "DEEP_INVESTIGATION",
  "deterministic": true,
  "new_evidence_count": 1,
  "new_hypotheses_count": 1
}
```

---

## Evidence Impact Example

When evidence `e1` is invalidated:
- **Severity**: MEDIUM
- **Affected claims**: `c1`
- **Downstream dependencies**: `e2` (depends on `e1`)
- **Revalidation required**: true

Cycle detection correctly identifies circular dependencies and prevents artificial inflation of evidence strength.

---

## Contradiction Classification

| Type | Example | Confidence |
|------|---------|------------|
| `LOGICAL_CONTRADICTION` | "Life has meaning" vs "Life has no meaning" | 0.9 |
| `SEMANTIC_TENSION` | "Life has purpose" vs "Life is random" | 0.65 |
| `CONTEXT_DEPENDENT` | "Consciousness is real" vs "AI consciousness impossible" | 0.5 |
| `NO_CONTRADICTION` | "A" vs "B" | — |

All scores are heuristic and marked as such (`is_heuristic: true`).

---

## Interface Status

The `ui/debate_monitor.html` exists but has **not been extended** with the Experience Explorer view in this session. The backend data structures are ready for UI integration.

---

## Known Limitations

1. **No persistent storage** — experiences are in-memory only (JSONL export available)
2. **UI not extended** — `debate_monitor.html` needs enhancement for Experience Explorer
3. **Semantic search not implemented** — experience similarity uses keyword matching only
4. **No external model calls** — deep investigation only uses captured historical state

---

## Files Created/Modified

| File | Action |
|------|--------|
| `core/debate/experience_registry.py` | Created |
| `core/debate/evidence_impact.py` | Created |
| `core/debate/deepening_engine.py` | Created |
| `core/debate/enhanced_contradiction_detector.py` | Created |
| `core/debate/engine.py` | Extended (ReplayEngine) |
| `core/debate/events.py` | Extended (13 new event types) |
| `tests/test_experience_investigation.py` | Created |
| `results/experience_investigation/test_report.json` | Created |
