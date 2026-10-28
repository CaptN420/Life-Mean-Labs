"""Configuration guide for AdaptiveRouter.

## Quick Start

```python
from core.router.adaptive import AdaptiveRouter, EngineType, CostConfig

# Create router with custom cost config
router = AdaptiveRouter(
    cost_config=CostConfig(
        reliability_weight=2.0,
        compute_weight=1.0,
        token_weight=0.01,
        latency_weight=0.5,
    ),
    max_fallbacks=3,
)

# Register engines
router.register_engine(EngineType.DETERMINISTIC, my_deterministic_fn)
router.register_engine(EngineType.COMPUTATIONAL, my_computational_fn)
router.register_engine(EngineType.LLM, my_llm_fn)

# Route a task
decision = router.route(
    task_id="task-001",
    description="Calculate gcd of 48 and 180",
    tool_name="math_gcd",
    kwargs={"a": 48, "b": 180},
    llm_available=True,
)

# Access results
print(decision.classification)  # DETERMINISTIC
print(decision.selected_engine)  # CACHE or DETERMINISTIC
print(decision.validation)  # VERIFIED
print(decision.to_dict())
```

## Classification Types

- `DETERMINISTIC`: Exact calculation, explicit rules (math, physics, chemistry)
- `COMPUTATIONAL`: Simulation, optimization, numerical methods
- `REASONING`: Complex analysis, multi-step reasoning
- `AMBIGUOUS`: Insufficient data, multiple interpretations
- `UNKNOWN`: Undetermined

## Engine Types

- `CACHE`: Cached result (fastest)
- `DETERMINISTIC`: Python worker for exact computation
- `COMPUTATIONAL`: Numerical/simulation worker
- `LLM`: Language model for reasoning
- `ERROR`: No reliable engine available

## Validation Status

- `VERIFIED`: Result passed all validations
- `PARTIAL`: Result partially validated
- `UNVERIFIED`: Result could not be validated
- `INVALID`: Result failed validation

## Fallback Chain

`CACHE → DETERMINISTIC → COMPUTATIONAL → LLM → ERROR`

The router automatically falls back when an engine fails.

## Statistics

```python
stats = router.get_stats()
# {
#   "total_tasks": 100,
#   "cache_hit_rate": 0.45,
#   "classification_distribution": {"DETERMINISTIC": 60, ...},
#   "worker_stats": {"DETERMINISTIC": {...}, ...}
# }
```

## Cost Optimization

The router minimizes: `reliability_weight * (1 - success_rate) + compute_cost + token_cost + latency`

Configure weights in `CostConfig` to prioritize different aspects.
"""
