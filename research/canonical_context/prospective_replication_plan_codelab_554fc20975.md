# Prospective Replication Plan: codelab_554fc20975

## Overview

This document outlines a plan for a **prospective replication** of the task conditions from historical run `codelab_554fc20975`, using the SAME Task Management System prompt INCLUDING the original context contamination.

**Important:** This is NOT a reproduction of model behavior. Model/backend conditions may differ. This is a **PROSPECTIVE_REPLICATION_OF_TASK_CONDITION**.

## Purpose

Compare a fully instrumented prospective run against the historical failed run to:
1. Verify that post-f3f7f42 instrumentation captures complete provenance
2. Test whether context contamination persists in task input
3. Establish a baseline for strict Canonical Context benchmark corpus
4. Enable comparative analysis between pre-instrumentation and post-instrumentation runs

## Task Specification

### Original Task Text (RETAINED UNCHANGED)

```
Intermediate Programming Task: Build a Task Management System
Intermediate Level
 Estimated time: 2–4 hours

Problem Statement
Create a Task Management System that allows users to organize, track, and manage their daily tasks efficiently.
The system should support adding, updating, deleting, searching, and filtering tasks.
Requirements
1. Add Task: Users can create tasks with a title, description, priority, due date, and status.
2. Update Task: Users can edit existing task information.
3. Delete Task: Users can remove tasks using their unique ID.
4. View Tasks: Display all tasks in a structured format.
5. Search Tasks: Search tasks by title or keywords.
6. Filter Tasks: Filter by status (Pending, In Progress, Completed) or priority (Low, Medium, High).
7. Sort Tasks: Sort by due date or priority.
8. Data Persistence: Save tasks to a JSON file or database so they remain available after restarting the program.
Example Input
===== TASK MANAGER =====
1. Add Task
2. View Tasks
3. Update Task
4. Delete Task
5. Search Tasks
6. Filter Tasks
7. Exit

Enter choice: 1

Task Title: Complete Python Project
Description: Build a task manager
Priority: High
Due Date: 2026-11-15
Status: Pending

Task added successfully!
Task ID: 101


Example Output
ID: 101
Title: Complete Python Project
Priority: High
Due Date: 2026-11-15
Status: Pending


Technical Constraints
- Use object-oriented programming (OOP).
- Implement proper error handling.
- Validate user inputs.
- Use functions and classes to keep the code modular.
- Prevent duplicate task IDs.
- Handle invalid dates gracefully.
Bonus Challenges
- Add user authentication.
- Implement task completion statistics.
- Create a graphical user interface (GUI).
- Add overdue task notifications.
- Write unit tests for the main features.
Evaluation Criteria
Criteria	Weight
Functionality	40%
Code quality and structure	25%
Error handling	15%
Data persistence	10%
Testing	10%
Expected Deliverable: A working application with clean, maintainable code, a README explaining how to run it, and at least five test cases.

Would you like the next intermediate programming task to focus on Python, JavaScript, Java, C++, or full-stack web development?




I can see your Discord screenshot from #hermes-projects, featuring several AI coding tools and projects:
- HuggingFace ColGrep-Agent-2B — A code-search model designed to reduce token usage.
- context-mode — A tool for optimizing context windows in AI coding agents.
- REA (Reverse Engineering Agent) — An open-source framework for reverse-engineering applications and binaries.
```

**Note:** The contamination section (last ~15%) is retained unchanged per research integrity requirements.

### Configuration Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| `project_name` | my_project | Original metadata |
| `language` | Python | Original metadata |
| `max_iterations` | 10 | Original metadata |
| `multi_agent` | true | Original metadata |
| `run_tests` | true | Original metadata |
| `deterministic_validation` | true | Original metadata |
| `reflection` | true | Original metadata |
| `template_id` | coding-standard | Original metadata |
| `seed` | 42 | Original metadata |
| `timeout_seconds` | 60 | Original metadata |
| `max_output_bytes` | 1000000 | Original metadata |

### Model Configuration (Same as Original)

| Role | Model | Source |
|------|-------|--------|
| planner | bonsai-4b | Original metadata.role_models |
| developer | google/gemma-4-12b | Original metadata.role_models |
| critic | granite-3.0-3b-a800m-instruct | Original metadata.role_models |
| reviewer | falcon-h1-3b-instruct | Original metadata.role_models |
| judge | lfm2.5-1.2b-thinking | Original metadata.role_models |

## Instrumentation Requirements

### Reference Commit
**f3f7f42** - Hash provenance wiring at model-call boundary

All instrumentation from this commit MUST be active and verified before execution.

### Required Provenance Fields

The prospective run must capture:

- `run_id` (NEW, not codelab_554fc20975)
- `trace_index` (monotonically increasing per agent attempt)
- `attempt_id` (UUID per agent attempt)
- `model_call_id` (UUID per model call)
- `configured_model` (from role_models mapping)
- `actual_model` (resolved at runtime)
- `system_prompt_hash` (SHA256 of exact system prompt)
- `input_context_hash` (SHA256 of serialized messages)
- `response_hash` (SHA256 of exact model response)
- `sampling_settings_hash` (SHA256 of temperature/max_tokens)

### Event Timeline Requirements

Expected events (minimum):
1. `TASK_RECEIVED` (seq=0)
2. `AGENT_STARTED` PLANNER (seq=1, trace_index=0)
3. `AGENT_RESPONSE` PLANNER (seq=2, trace_index=0)
4. `AGENT_STARTED` DEVELOPER attempt 1 (seq=3, trace_index=1)
5. `AGENT_RESPONSE` or `AGENT_FAILED` DEVELOPER attempt 1 (seq=4, trace_index=1)
6. `AGENT_STARTED` DEVELOPER attempt 2 (if retry needed) (seq=5, trace_index=2)
7. `AGENT_RESPONSE` or `AGENT_FAILED` DEVELOPER attempt 2 (seq=6, trace_index=2)
8. `FILE_CREATED` events (if files created)
9. `TEST_STARTED` / `TEST_RESULT` events (if tests run)
10. `RUN_COMPLETED` or `RUN_FAILED` (terminal event)

## Execution Plan

### Phase 1: Pre-Flight Verification

1. Verify instrumentation commit f3f7f42 is active
2. Confirm LLM backend availability (localhost:1234/v1)
3. Validate model endpoints for all configured models
4. Confirm EventLogger runtime integration
5. Run test suite: `pytest tests/test_code_lab_event_provenance.py tests/test_code_lab_visibility.py`

### Phase 2: Execute Prospective Run

1. Create NEW run_id (e.g., `codelab_replication_XXXXX`)
2. Load original task text UNCHANGED (including contamination)
3. Apply original configuration parameters
4. Execute run with full instrumentation active
5. Capture all events to events.jsonl
6. Archive raw run data to raw/run_<run_id>.json
7. Generate metadata.json with all configuration

### Phase 3: Post-Run Verification

1. Verify event sequence is contiguous (0, 1, 2, ...)
2. Verify all AGENT_STARTED events have matching terminal events
3. Verify hash fields are non-null for all agent responses
4. Verify trace_index monotonicity
5. Verify run_id consistency across all events
6. Archive audit report to research/canonical_context/prospective_corpus/

## Success Criteria

| Criterion | Target |
|-----------|--------|
| EVENT_SEQUENCE_CONTIGUOUS | YES |
| PROVENANCE_COMPLETENESS | PASS (all hash fields present) |
| STATE_T_RECONSTRUCTIBLE | YES (full reconstruction possible) |
| FUTURE_LEAKAGE | NO |
| CONTEXT_CONTAMINATION_PRESENT | YES (retained unchanged) |

## Output Artifacts

### Required Files

```
code_lab_runs/<new_run_id>/
    ├── metadata.json              # Run configuration
    ├── raw/
    │   └── run_<new_run_id>.json  # Complete run archive
    └── logs/
        └── <new_run_id>/
            └── events.jsonl       # Ordered event timeline

research/canonical_context/prospective_corpus/
    └── <new_run_id>_audit.md      # Audit report
```

### Audit Report Contents

The audit report must include:
1. Run identity and configuration
2. Evidence inventory (all artifacts)
3. Complete ordered event timeline
4. STATE_t reconstructions for each agent turn
5. Original context classification (same as historical)
6. Candidate canonical state (derived)
7. Context-size comparison (original vs canonical)
8. Actual outcome / validator results
9. Leakage audit
10. Research eligibility verdict

## Comparison with Historical Run

### Expected Differences

| Aspect | Historical (codelab_554fc20975) | Prospective (new run) |
|--------|--------------------------------|----------------------|
| Instrumentation | Pre-f3f7f42 (incomplete) | Post-f3f7f42 (complete) |
| Event timeline | 2 events | Expected 8-10 events |
| Hash fields | NULL | Should be present |
| STATE_t reconstruction | PARTIAL | Should be FULL |
| Context contamination | YES | YES (retained) |

### Analysis Goals

1. Verify that complete provenance enables full STATE_t reconstruction
2. Compare failure modes (if prospective run also fails)
3. Assess impact of context contamination on model behavior
4. Establish baseline for strict Canonical Context benchmark corpus

## Constraints

- **DO NOT** modify the task text (including contamination)
- **DO NOT** change model configuration
- **DO NOT** alter retry logic or routing
- **DO NOT** clean or preprocess the prompt
- **DO NOT** treat this as a "reproduction" - model conditions may differ
- **DO NOT** mix this run with historical corpus in strict benchmark analysis

## Naming Convention

Use NEW run_id format: `codelab_replication_<timestamp_hash>`

Example: `codelab_replication_a1b2c3d4`

This clearly distinguishes it from the historical run `codelab_554fc20975`.

---

## Final Notes

This prospective replication plan is a RESEARCH DOCUMENT only.

It does NOT execute any experiment.

The actual execution will be triggered in a future session with explicit approval.

All historical evidence remains unchanged:
- `code_lab_runs/codelab_554fc20975/` - untouched
- `research/canonical_context/historical_cases/codelab_554fc20975_audit.md` - untouched
