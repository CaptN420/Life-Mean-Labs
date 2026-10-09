# LIFE_MEAN LAB — RAW DEBATE DATA PROTOCOL

## IMPLEMENTATION STATUS: COMPLETE

This protocol implements the RAW DEBATE DATA PROTOCOL for recording complete debate experiments for future ML training (SFT, DPO, reward models, router training, etc.).

## FILES CREATED

### `philosophical_council/raw_protocol/__init__.py`
Main module with all data classes and the `RawDebateRecorder` class.

## DATA STRUCTURES

### ExperimentMeta
- `schema_version`: "1.0.0"
- `experiment_id`: UUID
- `task_id`: UUID
- `debate_id`: Optional
- `timestamp_start/end`: ISO format
- `lab_version`, `orchestration_version`
- `dataset_source`, `random_seed`

### InputOriginal
- `raw_prompt`: Original user input (never modified)
- `context`, `language`, `constraints`
- `generation_params`: Relevant generation settings
- `estimated_*`: Separate annotations (domain, difficulty, skills)

### RoutingDecision
- `router_id`, `router_version`
- `available_agents`, `considered_agents`, `selected_agents`
- `routing_scores`: Complete scores (not just winner)
- `detected_domain`, `sought_skills`
- `execution_order`, `strategy`

### AgentCall
- `agent_id`, `agent_version`, `role`, `specialty`
- `model_family`, `model_version`
- `input_sent`, `output_received`: Complete observables
- `status`: success/error/timeout/rejected
- `tokens_input/output`, `duration_seconds`, `estimated_cost`

### DebateEvent
- `event_id`, `parent_event_id`
- `timestamp`, `round_num`
- `agent_id`, `event_type`: proposal/critique/counterargument/etc.
- `content`: Original observable content

### Candidate
- `candidate_id`, `creator_agent_id`
- `content`, `critiques_received`, `corrections_proposed`
- `scores`, `status`: selected/rejected/superseded/invalid/unverified

### Disagreement
- `disagreeing_agents`, `propositions`
- `nature_of_disagreement`, `arguments_formulated`
- `evidence_invoked`, `resolution`, `final_result`

### VerificationResult
- `verifier_id`, `verification_method`
- `candidate_evaluated`, `criteria`
- `scores_by_criteria`, `errors_detected`
- `result`, `confidence_level`

### FinalSelection
- `considered_candidates`, `winner_candidate_id`
- `selection_method`, `votes_or_scores`
- `reasons_given`, `modifications_after_selection`
- `final_answer`

### DerivedLabels (separate from RAW)
- `domain`, `skills_required`
- `best_individual_agent`, `best_agent_combination`
- `cost_of_each_strategy`, `quality_obtained`

## USAGE EXAMPLE

```python
from philosophical_council.raw_protocol import RawDebateRecorder, EventType

recorder = RawDebateRecorder()

# Start experiment
meta = recorder.start_experiment(dataset_source='my_dataset')

# Record input (preserved unchanged)
recorder.record_input(meta.experiment_id, "What is the meaning of life?")

# Record routing decision
recorder.record_routing(
    meta.experiment_id,
    available_agents=['existentialist', 'stoic'],
    selected_agents=['existentialist'],
    routing_scores={'existentialist': 0.8, 'stoic': 0.6}
)

# Record agent call
recorder.record_agent_call(
    meta.experiment_id,
    agent_id='existentialist',
    input_sent="Challenge...",
    output_received="Response...",
    tokens_input=100,
    duration_seconds=2.5
)

# Record debate event
recorder.record_debate_event(
    meta.experiment_id,
    event_type=EventType.PROPOSAL.value,
    agent_id='existentialist',
    content="Meaning is self-created."
)

# Finalize
recorder.finalize_selection(
    meta.experiment_id,
    winner_candidate_id='candidate_123',
    final_answer='Meaning is created through commitment.'
)

# Save (immutable once saved)
recorder.end_experiment(meta.experiment_id)
filepath = recorder.save_experiment(meta.experiment_id)
```

## INTEGRATION WITH DEBATE ENGINE

The `DebateEngine` now automatically:
1. Creates a RAW experiment when `start_debate()` is called
2. Records each agent call with input/output/tokens/duration
3. Records each debate event (proposal, critique, etc.)
4. Saves RAW data when `stop_debate()` is called

## PRINCIPLES

- **RAW data is NEVER overwritten** - once saved, it's immutable
- **Provenance is preserved** - every piece of data can be traced back to its origin
- **Diversity is preserved** - losing candidates, disagreements, and errors are kept
- **Separation of concerns** - RAW events, evaluations, derived annotations, and final answer are stored separately

## STORAGE LOCATION

RAW data is stored in:
```
philosophical_council/storage/raw_data/<experiment_id>.json
```
