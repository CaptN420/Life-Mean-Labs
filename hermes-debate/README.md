# Hermes Multi-Agent Debate Orchestrator

A production-ready multi-agent philosophical debate system using:
- **Hermes**: Orchestration, policy, state management
- **CLEF**: Structured decisions (not content generation)
- **27B Models**: Deep reasoning agents
- **ModelManager**: VRAM lifecycle management

## Architecture

```
                         USER
                           │
                           ▼
                    ┌─────────────┐
                    │    HERMES   │
                    │ Orchestrator│
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    CLEF     │
                    │ Decision    │
                    │   Model     │
                    └──────┬──────┘
                           │
                  structured decision
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      ┌──────────────┐            ┌──────────────┐
      │   MODEL A    │            │   MODEL B    │
      │     27B      │            │     27B      │
      │ Reasoning    │            │ Reasoning    │
      └──────────────┘            └──────────────┘
             │                           │
             └─────────────┬─────────────┘
                           ▼
                    ┌─────────────┐
                    │ Debate State│
                    └──────┬──────┘
                           │
                           ▼
                         CLEF
                           │
                           ▼
                      next action
```

## Installation

```bash
cd Life_mean/hermes-debate
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
# Edit .env with your credentials
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLEF_ACCOUNT_ID` | Cloudflare account ID | - |
| `CLEF_API_KEY` | Cloudflare API key | - |
| `SIMULATION` | Enable simulation mode | false |
| `GPU_DEVICE` | GPU device ID | 0 |

### Config File

Edit `config.yaml`:

```yaml
runtime:
  mode: strict  # "strict" or "performance"
  max_turns: 8
  request_timeout_seconds: 600

models:
  clef:
    role: decision_model
    vram_class: decision
  
  model_a:
    role: philosopher
    vram_class: reasoning
  
  model_b:
    role: critic
    vram_class: reasoning
```

## Usage

### CLI

```bash
python -m hermes_debate.cli "What is the meaning of life?"
```

### Simulation Mode (no GPU required)

```bash
python -m hermes_debate.cli "What is the meaning of life?" --dry-run
```

### With Custom Config

```bash
python -m hermes_debate.cli "What is the meaning of life?" --config /path/to/config.yaml
```

### Debug Mode

```bash
python -m hermes_debate.cli "What is the meaning of life?" --debug
```

## Python API

```python
from hermes_debate.config import load_config
from hermes_debate.orchestrator.hermes import HermesOrchestrator

async def main():
    config = load_config()
    orchestrator = HermesOrchestrator(config)
    
    result = await orchestrator.run("What is the meaning of life?")
    
    print(result.answer)
    print(f"Turns: {len(result.turns)}")
    print(f"Metrics: {result.metrics}")

asyncio.run(main())
```

## VRAM Management

The system uses a strict mode by default to minimize VRAM usage:

1. Load CLEF for decision
2. Unload CLEF
3. Load reasoning model (A or B)
4. Generate response
5. Unload reasoning model
6. Repeat

### Performance Mode

If you have sufficient VRAM, set `mode: performance` in config.yaml to keep models resident.

## Testing

```bash
pytest tests/ -v
```

### Run Specific Tests

```bash
pytest tests/test_all.py::TestOrchestrator -v
pytest tests/test_all.py::TestModelManager -v
```

## Architecture Decisions

### Why CLEF for Decisions, Not Content?

CLEF is a decision model, not a chatbot. It excels at:
- Routing decisions
- Pattern detection
- Structured output
- Confidence scoring

It should NOT be used for:
- Generating philosophical arguments
- Writing final answers
- Creative content

### Why Separate Agents?

Each agent has a distinct role:
- **Philosopher**: Deep reasoning, argument construction
- **Critic**: Challenge assumptions, find contradictions
- **Judge**: Synthesize, evaluate, conclude

This separation prevents:
- Circular reasoning
- Repetitive arguments
- Lack of progress

### Why VRAM Management Matters

Loading multiple 27B models simultaneously requires ~100GB VRAM. Most consumer GPUs have 8-24GB. Dynamic swapping allows:
- Running on hardware with limited VRAM
- Better resource utilization
- Predictable memory usage

## Troubleshooting

### CLEF API Fails

Check:
1. Account ID is correct
2. API key has proper permissions
3. Network connectivity to Cloudflare

### Model Loading Fails

Check:
1. GPU has sufficient VRAM
2. Model path is correct
3. Backend is properly configured

### Loop Detected

The system automatically detects and breaks loops. If you see frequent loop detection:
- Increase `loop_threshold` in config
- Check if agents are generating similar content
- Consider adding more diverse agent prompts

## License

MIT License
