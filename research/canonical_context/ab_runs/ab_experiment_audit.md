# A/B Experiment Audit: Controlled Canonical Context Comparison

## 1. Experiment Identity

| Field | Value |
|-------|-------|
| **experiment_type** | CONTROLLED_CANONICAL_CONTEXT_AB |
| **historical_reference** | codelab_554fc20975 |
| **condition_a** | ORIGINAL_CONTEXT (codelab_ab_original_context) |
| **condition_b** | CANONICAL_STATE (codelab_ab_canonical_state) |
| **created_at** | 2026-10-13 |
| **status** | COMPLETED |

## 2. Frozen Configuration

```ini
GIT_COMMIT = b63fb89
BACKEND_URL = http://localhost:1234/v1
API_KEY_CONFIGURED = YES (length: 35)
SEED = 42
TEMPLATE_ID = coding-standard
TEMPLATE_VERSION = 1.0.0
MAX_ITERATIONS = 10
TIMEOUT_SECONDS = 60

ROLE_MODELS:
  PLANNER = bonsai-4b
  DEVELOPER = google/gemma-4-12b
  CRITIC = granite-3.0-3b-a800m-instruct
  REVIEWER = falcon-h1-3b-instruct
  JUDGE = lfm2.5-1.2b-thinking

MODELS_AVAILABLE = 46 (all required present)
```

## 3. Condition A — ORIGINAL_CONTEXT

| Metric | Value |
|--------|-------|
| **run_id** | codelab_ab_original_context |
| **prompt_length** | 2599 chars |
| **prompt_tokens_approx** | 391 words |
| **prompt_sha256** | f298913da508299e2e7e1bb99e979e773bd22e0658f70e34239c564aa8ba396b |
| **status** | FAILED |
| **duration** | 252.494s |
| **iterations** | 0 |
| **files_created** | 0 |
| **agent_trace_count** | 3 |

### Agent Trace Summary (Condition A)

| Index | Agent | Response Length | Duration | Finish |
|-------|-------|-----------------|----------|--------|
| 0 | PLANNER | 5397 chars | 100.9s | stop |
| 1 | DEVELOPER | 952 chars | 79.7s | length |
| 2 | DEVELOPER | 914 chars | 67.6s | length |

### Outcome (Condition A)

```ini
RUN_STATUS = FAILED
TEST_STATUS = NOT_REACHED
VALIDATOR_OUTCOME = NOT_REACHED
ERROR_CLASSIFICATION = AGENT_OUTPUT_FAILURE
ERROR_MESSAGE = DEVELOPER returned empty/phantom output after retry
```

## 4. Condition B — CANONICAL_STATE

| Metric | Value |
|--------|-------|
| **run_id** | codelab_ab_canonical_state |
| **prompt_length** | 1346 chars |
| **prompt_tokens_approx** | 204 words |
| **prompt_sha256** | 9745eb8970127686b6696df0bdafb389e3738045ab3f38716c1d29a89abf8587 |
| **status** | FAILED |
| **duration** | 205.38s |
| **iterations** | 0 |
| **files_created** | 0 |
| **agent_trace_count** | 3 |

### Agent Trace Summary (Condition B)

| Index | Agent | Response Length | Duration | Finish |
|-------|-------|-----------------|----------|--------|
| 0 | PLANNER | 3720 chars | 55.5s | stop |
| 1 | DEVELOPER | 0 chars | 80.9s | length |
| 2 | DEVELOPER | 0 chars | 65.9s | length |

### Outcome (Condition B)

```ini
RUN_STATUS = FAILED
TEST_STATUS = NOT_REACHED
VALIDATOR_OUTCOME = NOT_REACHED
ERROR_CLASSIFICATION = AGENT_OUTPUT_FAILURE
ERROR_MESSAGE = DEVELOPER returned empty/phantom output after retry
```

## 5. Context Reduction Analysis

| Metric | Condition A (Original) | Condition B (Canonical) | Difference |
|--------|------------------------|-------------------------|------------|
| **Prompt length** | 2599 chars | 1346 chars | -48.2% |
| **Approx tokens** | 391 words | 204 words | -47.8% |
| **PLANNER response** | 5397 chars | 3720 chars | -31.1% |
| **PLANNER duration** | 100.9s | 55.5s | -45.0% |
| **DEVELOPER attempt 1** | 952 chars | 0 chars | -100% |
| **DEVELOPER duration 1** | 79.7s | 80.9s | +1.5% |
| **DEVELOPER attempt 2** | 914 chars | 0 chars | -100% |
| **DEVELOPER duration 2** | 67.6s | 65.9s | -2.5% |
| **Total duration** | 252.5s | 205.4s | -18.6% |

## 6. Comparative Analysis

### Behavioral Comparability

| Aspect | Condition A | Condition B | Assessment |
|--------|-------------|-------------|------------|
| **PLANNER success** | YES (5397 chars) | YES (3720 chars) | Both succeeded, different output length |
| **DEVELOPER failure** | YES (truncated output) | YES (empty output) | Same failure stage, different manifestation |
| **Test execution** | NO | NO | Both NOT_REACHED |
| **Validator execution** | NO | NO | Both NOT_REACHED |

### Key Observations

1. **Both conditions failed at the same stage** (DEVELOPER) with the same classification (AGENT_OUTPUT_FAILURE).
2. **Condition B completed faster** (-18.6% total duration) due to shorter prompt processing.
3. **Condition A's DEVELOPER produced partial output** (952 + 914 chars) before truncation.
4. **Condition B's DEVELOPER produced no output** (0 chars) on both attempts.
5. **Context reduction did not improve outcome** — both conditions failed identically.

## 7. Provenance Audit

### Condition A Provenance

```ini
EVENT_SEQUENCE_INTEGRITY = PASS
START_TERMINAL_PAIRING = PASS
TRACE_INDEX_INTEGRITY = PASS
SYSTEM_PROMPT_PROVENANCE = PASS
INPUT_CONTEXT_PROVENANCE = PASS
RESPONSE_PROVENANCE = PASS
SAMPLING_PROVENANCE = PASS
MODEL_PROVENANCE = PASS
```

### Condition B Provenance

```ini
EVENT_SEQUENCE_INTEGRITY = PASS
START_TERMINAL_PAIRING = PASS
TRACE_INDEX_INTEGRITY = PASS
SYSTEM_PROMPT_PROVENANCE = PASS
INPUT_CONTEXT_PROVENANCE = PASS
RESPONSE_PROVENANCE = PASS
SAMPLING_PROVENANCE = PASS
MODEL_PROVENANCE = PASS
```

## 8. Limitations

1. **No decision-level comparison** — Neither run reached the test/validator stage, so decision preservation could not be evaluated.
2. **Single sample per condition** — Statistical significance cannot be established.
3. **Model nondeterminism** — Different responses expected even with same seed due to LLM stochasticity.
4. **Environmental factors** — Runtime resource availability may have influenced outcomes.

## 9. Final Verdict

```ini
EXPERIMENT_STATUS = COMPLETED
CONFIGURATION_MATCH = PASS
CONDITION_A_STATUS = FAILED
CONDITION_B_STATUS = FAILED
PROVENANCE_A = PASS
PROVENANCE_B = PASS
VALIDATOR_A = NOT_REACHED
VALIDATOR_B = NOT_REACHED
CONTEXT_REDUCTION = 48.2%
DECISION_PRESERVATION = NOT_TESTED
CAUSALITY_STATUS = UNKNOWN

BEHAVIORAL_COMPARABILITY = INCONCLUSIVE
```

**INTERPRETATION:** Both conditions failed at the same stage with identical error classification, suggesting the failure is environmental (LLM backend/resource limitation) rather than context-quality related. The 48.2% context reduction did not improve or worsen the outcome. Causal claims about context quality cannot be made without reaching the decision checkpoint.

---

## Artifacts

- `code_lab_runs/codelab_ab_original_context/metadata.json`
- `code_lab_runs/codelab_ab_original_context/raw/run_codelab_ab_original_context.json`
- `code_lab_runs/codelab_ab_original_context/logs/codelab_ab_original_context/events.jsonl`
- `code_lab_runs/codelab_ab_canonical_state/metadata.json`
- `code_lab_runs/codelab_ab_canonical_state/raw/run_codelab_ab_canonical_state.json`
- `code_lab_runs/codelab_ab_canonical_state/logs/codelab_ab_canonical_state/events.jsonl`
- `research/canonical_context/ab_runs/ab_experiment_audit.md`
