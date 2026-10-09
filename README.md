# Life_mean Lab

Multi-agent system & synthetic data lab. `philosophical_council` is the stable
multi-agent core (DebateEngine, LLMClient, agents, SmartRouter, EventBus,
RAW storage); `experiments` is the deterministic generation/validation/runner
layer; `code_lab` is the experimental code-generation layer that REUSES the
stable core.

## Install & run from the repository root (documented supported command)

Requires Python >= 3.10. From `C:/Users/celes/Documents/Hermes-Workspace/Life_mean`:

```bash
# 1. create a fresh environment and install the package + deps
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e .

# 2. import check
python -c "import philosophical_council, experiments, code_lab; print('OK')"

# 3. run the tests (deterministic suite + philosophical_council tests)
python -m pytest -q
# or explicitly:
python -m pytest tests/ philosophical_council/tests/ -q
```

`pyproject.toml` sets `[tool.pytest.ini_options] pythonpath = ["."]`, so a fresh
environment collects the same tests without any `sys.path` hacks in tests.

## Notes

- `openai` is a **runtime dependency** (OpenAI-compatible client for
  LM Studio / OpenRouter). The deterministic paths run without a live backend;
  LLM calls are gated on `code_lab.multiagent.probe_llm()` and honest about
  availability (never a fake run).
- `hermes-debate/` is a **separate project** (packages as `hermes_debate`, its
  own `setup.py`) and is intentionally not part of this package. Tests that
  import it (`tests/test_model_pool.py`) are skipped when it is not installed.
- LLM credentials live in `.env` (git-ignored). See `.env.example`.
- RAW evidence is append-only/immutable under `data/` and run workspaces.
