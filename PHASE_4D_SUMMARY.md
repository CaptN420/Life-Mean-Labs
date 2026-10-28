# Phase 4D — Real Debate Experiments & Emergence Benchmarks

## Status

| Component | Status | Tests |
|-----------|--------|-------|
| ArgumentLedger | ✅ Complete | 8 passed |
| DebateExperimentRunner | ✅ Complete | 5 passed |
| StrategyLearning | ✅ Complete | 5 passed |
| RealBenchmarkRunner | ✅ Complete | 3 passed |
| Smoke test (real LLM) | ⚠️ Skipped | Requires local model |

**Total:** 970 passed, 13 skipped, 0 failed

## Files Created

| File | Purpose |
|------|---------|
| `life_mean_lab/orchestrator/debate_ledger.py` | Structured debate event recording with repetition detection |
| `life_mean_lab/orchestrator/debate_experiment.py` | Multi-agent debate experiment engine |
| `life_mean_lab/orchestrator/strategy_learning.py` | Strategy performance tracking and recommendations |
| `life_mean_lab/orchestrator/benchmark_real.py` | Real experiment runner with provenance tracking |
| `tests/test_phase4d.py` | 21 deterministic tests |
| `scripts/smoke_test_debate.py` | CLI for real LLM debate smoke test |

## Usage: Real Debate with LM Studio

```bash
# Start LM Studio, load a model (e.g., llama-3.2-1b), enable local server on port 1234

# Run a 3-agent debate on shared memory condition
python scripts/smoke_test_debate.py \
    --question "Is free will compatible with determinism?" \
    --condition shared \
    --rounds 3 \
    --agents 3

# Run independent agents (no shared memory)
python scripts/smoke_test_debate.py \
    --question "Should AI be regulated?" \
    --condition independent \
    --rounds 2
```

## Experimental Conditions

| Condition | Description | Memory |
|-----------|-------------|--------|
| A | Independent agents | Individual |
| B | Shared memory | All agents see same history |
| C | Adaptive rules | Shared + role specialization |

## Emergence Measures

| Metric | Description |
|--------|-------------|
| `argument_diversity` | Unique argument types / total |
| `novelty_score` | New concepts per round |
| `position_stability` | Ratio of stable positions |
| `specialization_index` | Degree of role specialization |
| `disagreements_resolved` | Count of resolved conflicts |

## Limitations

1. **Token counting is estimated** — LM Studio doesn't expose real token counts
2. **Semantic repetition detection is heuristic** — uses token overlap, not embeddings
3. **Emergence measures are exploratory** — not statistically validated
4. **No automatic model download** — requires pre-configured local endpoint
5. **Small sample sizes** — recommendations require 5+ records

## Next Steps

1. Run comparative experiments across conditions A/B/C
2. Collect strategy learning data from multiple debates
3. Validate emergence measures against human-coded annotations
4. Add streaming support for real-time debate observation
