# CG2 Benchmark Report — Cluster Graph Performance

## Problem Identified

During CG2 validation, slow graph loading observed with ~209 RAW files.

## Measurements (Before Fix)

```
=== CG2 Benchmark — 355 RAW files ===

Phase 1: Loading index           7.55 ms    (0.1%)
Phase 2: Reading RAW conditions  3455 ms   (48.5%)  <-- BOTTLENECK
Phase 4: Building graph          3483 ms   (48.9%)
Phase 6: Serialization           182 ms    (2.6%)

Total API time (first call):     7131 ms
Cache hit time:                  923 ms
Payload size:                   26817 KB
```

**Root cause:** Conditions loaded fresh from RAW on EVERY request (3.5s for 209 files).

## Measurements (After Fix)

```
Phase 2: Reading conditions (OLD)  3387 ms
Phase 2b: Reading via conditions_index (NEW)  13 ms

SPEEDUP: 252x faster for conditions loading
```

## Files Added/Modified

| File | Change |
|------|--------|
| `compare/conditions_index.py` | NEW — cached conditions index (mtime-based invalidation) |
| `experiments/dashboard.py` | Uses `load_conditions_index()` instead of per-RAW loop |
| `tests/benchmark_cg2.py` | Benchmark comparing OLD vs NEW |
| `tests/test_conditions_index.py` | Tests for new module |

## Test Results

- `test_cluster_graph_cg2.py`: **6/6 passed**
- `test_compare*.py`: **53/53 passed**
- `test_conditions_index.py`: functional test OK

## Cache Behavior Verified

- Graph cache reused (fingerprints match across calls)
- Conditions index rebuilt when RAW mtimes grow newer
- No RAW files modified (read-only)

## Next Steps

Ready for CG3 validation. The conditions caching is transparent to the graph build logic — same `conditions` dict shape, same fingerprinting, same cache invalidation.
