# Philosophical Council

A local multi-agent philosophical debate application using LM Studio's OpenAI-compatible API.

## Overview

Philosophical Council runs 5 philosophical agents (Existentialist, Stoic, Nihilist, Spiritual Philosopher, Skeptic) plus an autonomous Moderator in a continuous debate about deep philosophical questions. The system features:

- **Three-level memory architecture** (short-term, mid-term, long-term)
- **Autonomous moderator** that selects speakers strategically
- **Persistent debate history** stored in SQLite
- **Responsive GUI** with turn-by-turn transcript and memory inspection
- **Full control** (start/pause/resume/stop/step)

## Requirements

- Python 3.11+
- LM Studio running locally with OpenAI-compatible API enabled
- At least one chat model loaded in LM Studio

## Installation

```bash
cd philosophical_council
pip install -r requirements.txt
```

## Running LM Studio

1. Download and install [LM Studio](https://lmstudio.ai/)
2. Load a chat model (e.g., Llama 3, Mistral, or any local model)
3. Start the local API server (usually on `http://localhost:1234/v1`)

## Running the Application

```bash
python main.py
```

## Project Structure

```
philosophical_council/
├── main.py                 # Entry point
├── config.py               # Configuration management
├── requirements.txt        # Dependencies
├── README.md               # This file
│
├── core/
│   ├── debate_engine.py    # Main debate orchestration
│   ├── debate_state.py     # State management
│   ├── turn_manager.py     # Turn sequencing
│   └── events.py           # Event definitions
│
├── agents/
│   ├── base_agent.py       # Base agent class
│   ├── existentialist.py   # Existentialist philosopher
│   ├── stoic.py            # Stoic philosopher
│   ├── nihilist.py         # Nihilist philosopher
│   ├── spiritual.py        # Spiritual/metaphysical philosopher
│   ├── skeptic.py          # Skeptic/critic
│   └── moderator.py        # Debate moderator
│
├── llm/
│   ├── client.py           # LM Studio API client
│   └── prompts.py          # System prompts
│
├── memory/
│   ├── short_term.py       # Short-term memory
│   ├── mid_term.py         # Mid-term memory
│   ├── long_term.py        # Long-term memory
│   ├── consolidation.py    # Memory consolidation
│   └── storage.py          # Pydantic models
│
├── database/
│   ├── database.py         # Database wrapper
│   ├── schema.py           # SQL schema
│   └── repositories.py     # Data access layer
│
├── ui/
│   ├── app.py              # Main application window
│   ├── debate_view.py      # Debate transcript view
│   ├── memory_view.py      # Memory inspection view
│   ├── agent_panel.py      # Agent status panel
│   ├── moderator_panel.py  # Moderator decisions
│   ├── controls.py         # Control buttons
│   └── settings_view.py    # Configuration
│
├── storage/
│   ├── debates/            # Saved debates
│   └── exports/            # Exported transcripts
│
└── tests/
    ├── test_memory.py
    ├── test_database.py
    ├── test_agents.py
    └── test_debate_engine.py
```

## Memory Architecture

### Short-Term Memory
- Holds the last ~20 turns
- Provides immediate conversational context
- Used for direct rebuttals and continuity

### Mid-Term Memory
- Structured summaries of debate sections
- Created every N turns (configurable)
- Contains arguments, counter-arguments, questions, contradictions

### Long-Term Memory
- Persistent knowledge that survives restarts
- Stores fundamental arguments, discoveries, unresolved questions
- Consolidated periodically from mid-term memories

## Database Schema

The application uses SQLite with the following tables:
- `debates` - Debate metadata
- `turns` - Complete turn history
- `memory_short` - Short-term memory snapshots
- `memory_mid` - Mid-term summaries
- `memory_long` - Persistent knowledge
- `moderator_decisions` - Moderator choices and reasoning
- `agents` - Agent definitions
- `events` - Lifecycle events

## Configuration

Edit `config.json` or use the settings panel in the GUI:

```json
{
  "lm_studio": {
    "base_url": "http://localhost:1234/v1",
    "api_key": "lm-studio"
  },
  "debate": {
    "topic": "What is the meaning of life?",
    "temperature": 0.8,
    "max_tokens": 700,
    "short_term_turns": 20,
    "mid_term_interval": 10,
    "long_term_interval": 50
  },
  "models": {
    "existentialist": "",
    "stoic": "",
    "nihilist": "",
    "spiritual": "",
    "skeptic": "",
    "moderator": ""
  }
}
```

## Running Tests

```bash
pytest tests/ -v
```

## Adding a New Philosopher

1. Create a new file in `agents/` following the pattern of existing agents
2. Define the agent's system prompt, focus areas, and color
3. Register it in `main.py` and the UI

## Extending to Other LLM Providers

The `llm/client.py` module can be extended to support other providers by implementing the same interface:
- `chat(messages, model, temperature, max_tokens)` -> str
- `chat_stream(messages, model, temperature, max_tokens)` -> generator
- `get_models()` -> list[str]

## Security

This application is local-first:
- No data sent to external APIs except your configured LM Studio endpoint
- No telemetry or tracking
- All debate history stored locally in SQLite
