# Life-Mean Labs

**An extensible research laboratory for building, running and reproducing AI experiments.**

Most synthetic-data pipelines are one model, one pass, no second opinion — and no way to tell a
sample is wrong. This lab inverts that: a multi-agent council **proposes**, deterministic code
**decides**. An LLM is an opinion; a test is a verdict.

The engine is meant to stay put. Researchers design experiments **on top of it** — through a
versioned HTTP API and a design contract — without patching the core.

```
prompt ─► design (DRAFT → FROZEN) ─► generate ─► route ─► execute ─► validate ─► export
                                        │          │        │         │
                                     tasks   SmartRouter  tools    tests + shape
                                                                      │
                                              RAW jsonl + manifest ◄──┘
```

---

## Design rules

These are enforced in code and covered by tests, not aspirational prose.

| Rule | What it means |
|---|---|
| **Deterministic authority** | A passing test wins. An LLM can suggest an answer; it cannot override a failing check. |
| **No silent fallback** | If the backend is down, or no tool serves a task, the run says so (`UNSUPPORTED_TASK`, `NO_ANSWER`) instead of returning a plausible `None`. |
| **Traceability** | Every agent turn carries a monotonic `trace_index` and provenance hashes (prompt, settings, context, response). RAW evidence is append-only. |
| **Reproducibility** | Each run states what produced it: engine version, git commit, dependency hashes, seed, models, tools — plus a fingerprint. |
| **Human governance** | Experiments execute only from a **FROZEN** design; promoting a model needs explicit human approval. Training is strictly separated from generation. |

---

## What's inside

| Layer | Role |
|---|---|
| `philosophical_council/` | Stable multi-agent core: `DebateEngine`, philosophical agents (skeptic, stoic, nihilist, pragmatist, …), `EventBus`, RAW storage |
| `core/`, `library/` | Routing, workers, personas, protocols, 60 deterministic tools (math, physics, chemistry, logic, coding) with automatic task detection |
| `experiments/` | Generation → routing → execution → validation pipeline, dashboard and HTTP API, reproducibility manifest |
| `experimental/` | The researcher-facing layer: design contract, durable design store, sandboxed harness, capability registry |
| `code_lab/` | Code-generation experiments: PLANNER → generator → real `pytest` → compile validation, with event provenance |
| `analysis/`, `autopilot/` | Weakness analysis, curriculum control, model lifecycle (stable / candidate / rejected) |
| `benchmarks/` | Held-out evaluation, isolated from generation and training |

---

## The experiment contract

A **design** is the frozen contract of one experiment: agents and model assignments, stages,
budgets, seed, and the acceptance criteria.

```
DRAFT ──► REVIEWED ──► APPROVED ──► FROZEN ──► run
```

- Execution is **forbidden** unless the design is `FROZEN`.
- Freezing computes a `frozen_hash` over the content; a frozen snapshot is never mutated in place —
  changes mean a **new version**.
- Every snapshot `(design_id, version, status)` is one atomically written file under
  `data/experiments/designs/`, reloaded at startup, and listed by `history()`.
- A write failure raises `DesignStoreError`. There is no such thing as a silently unsaved design.

---

## Reproducibility

Every exported manifest answers *"what exactly produced this result?"*:

```json
{
  "engine":        { "name": "life_mean_lab", "version": "1.0.0" },
  "environment":   { "python": "3.12", "system": "Windows", "machine": "AMD64" },
  "dependencies":  { "combined_sha256": "4ba90b152122…" },
  "git":           { "commit": "b9602bb", "dirty": false },
  "seed":          21,
  "deterministic": true,
  "models":        { "…": "…" },
  "tools":         ["math_trig", "math_log"],
  "reproducibility_fingerprint": "…"
}
```

No secrets are collected — versions, ids and hashes only (there is a test that traps environment
variables to prove it).

**Runs survive a restart.** Each finished run writes an atomic summary under
`data/experiments/runs/`; the registry rehydrates at startup and marks those entries
`rehydrated: true`, never `running`.

**Honest boundary.** Events and traces live in memory. After a restart a rehydrated manifest
returns the exact config and seed but declares `events: []` / `traces: []` and points to the RAW
file for evidence. It does not pretend to carry what it lost.

---

## Quick start

### Docker (dashboard + API)

```bash
docker compose up -d --build
# → http://127.0.0.1:8080/dashboard
```

The image bakes the source in (no bind mounts), so **rebuild after changing code** — otherwise
the container keeps serving the old revision.

### Local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -e .
python -m pytest -q             # deterministic suite, no LLM backend required
python -m experiments.dashboard # local dashboard
```

Requires Python ≥ 3.10. Docker is optional; the suite runs without network access.

---

## Dashboard & HTTP API

The dashboard is a thin client over the same API researchers use.

| Endpoint | Purpose |
|---|---|
| `GET /api/experimental/capabilities` | What this lab can actually execute (declared, not implied) |
| `GET/POST /api/experimental/designs` | List / create designs |
| `POST /api/experimental/designs/{id}/transition` | Move a design toward `FROZEN` |
| `POST /api/experimental/harness/start` | Start a sandboxed harness run |
| `POST /api/experiments` · `/start` · `/stop` | Pipeline runs |
| `GET /api/experiments/{id}/manifest` | Reproducibility manifest |
| `GET /api/experiments/{id}/observability` | Live events and traces |
| `GET /api/code-lab/runs` · `GET /api/training/runs` · `GET /api/models` | Code Lab, training, model registry |

State-changing calls require the CSRF cookie/header pair issued by `GET /dashboard`. Raw evidence
is not an API endpoint: it is the append-only file `data/raw_debates/<experiment_id>.jsonl`.

```bash
curl -s localhost:8080/api/experimental/capabilities | jq
```

---

## Status

| | |
|---|---|
| **Engine version** | 1.0.0 |
| **Tests** | **1694 passing**, 13 skipped (external dependencies), 0 failing |
| **Phase** | P0 complete — durable designs, complete manifests, restart-safe runs. P1 in progress |
| **Next** | Declarative executor catalog, public SDK, sandbox hardening |

A green suite is not a proof of correctness. Defects here are found by **running the thing** and
reading the artifacts — for example, a real run scoring 1/3 exposed that `sin(…)` and `log(…)`
tasks had no detection pattern and answered a silent `None`; fixing it moved the same seed from
`pass_rate 0.333` to `1.0`.

---

## Known limits

- **Debate mode needs a live LLM backend** (LM Studio / OpenRouter / OpenAI-compatible). When it is
  down, the system refuses explicitly — it never runs a "debate" deterministically and calls it one.
- **No determinism guarantee for LLM paths.** Seeds pin the generator, not a remote model.
- **Observability is in-memory** — see the reproducibility boundary above.
- **One open gate**: the executor catalog is still partly hard-coded; that is P1.1.

---

## Repository map

```
experiments/            pipeline, dashboard, HTTP API, reproducer
experimental/           design contract, durable store, harness, capabilities
philosophical_council/  multi-agent core + RAW protocol
library/ core/          tools, routing, workers
code_lab/               code-generation experiments
analysis/ autopilot/    weakness analysis, curriculum, model lifecycle
tests/                  1694 deterministic tests
docs/                   architecture, ADRs, project catalog
```

---

## License

[Apache-2.0](LICENSE) © 2026 CaptN420
