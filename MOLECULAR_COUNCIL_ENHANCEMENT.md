# MOLECULAR DISCOVERY COUNCIL — Enhancement Summary

## What Was Added

The `MOLECULAR_DISCOVERY_COUNCIL_V1` template in `role_templates/builtins.py` has been enhanced with the **Scientific Integrity & Research Scope Guardian V1.0** system prompt from the attached specification.

### New Components

| Component | Description |
|-----------|-------------|
| **Evidence Classification System** | 5-level hierarchy: `EXPERIMENTAL_FACT`, `SUPPORTED_HYPOTHESIS`, `THEORETICAL_PREDICTION`, `UNVERIFIED_CLAIM`, `CONTRADICTED` |
| **Research Domain Lock** | Immutable scope parameters: `PRIMARY_RESEARCH_DOMAIN`, `ORIGINAL_RESEARCH_QUESTION`, `TARGET_BIOLOGICAL_OR_CHEMICAL_SYSTEM`, etc. |
| **Source Integrity Rules** | Prohibits invented publications, DOIs, experimental results, binding affinities, toxicity measurements |
| **Molecular & Biochemical Validation** | 5-part evaluation: biological mechanism, chemical plausibility, equations, evidence, safety |
| **Anti-Hallucination Protocol** | 7-question adversarial review by Mechanistic Skeptic and Evidence Curator |
| **Candidate Registry Schema** | 13-field structured record with status tracking (PROPOSED → REJECTED) |
| **Moderator Control Protocol** | 5 mandatory checks before each turn: SCOPE, EVIDENCE, CONSISTENCY, PROGRESS, REPETITION |
| **Enhanced Output Contract** | 9 fields (added `EVIDENCE_CLASSIFICATION`, `FALSIFICATION`, `DOMAIN_CHECK`) |
| **Final Research Report** | 12-section consolidated report format |
| **Research Integrity Priority** | 7-level conflict resolution hierarchy |

### Changes Made

- **File**: `role_templates/builtins.py`
- **Lines added**: +252
- **Backward compatible**: Yes — existing tests pass unchanged
- **No breaking changes**: All 7 roles preserved, response contract extended (not replaced)

## Test Results

```
tests/test_molecular_council.py .............. 10 passed
tests/test_dashboard_ui.py ................... 25 passed
tests/test_phase7_autopilot.py ............... 8 passed
tests/test_observability.py .................. 20 passed
---------------------------------------------------
Total: 63 passed, 0 failed
```

## Integration Points

The enhanced template is now ready for:
1. **Debate engine integration** — via existing `executor_type="debate"`
2. **Dashboard UI** — observable via existing observability layer
3. **Security gating** — domain lock enforces research scope
4. **Scientific rigor** — evidence classification enforced at every turn

## Next Steps (Optional)

- Add integration tests for moderator control protocol
- Create dashboard panel for candidate registry visualization
- Implement automated domain drift detection in autopilot
- Extend test suite with falsification scenario testing
