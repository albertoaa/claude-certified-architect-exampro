# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Study repository for the Claude Certified Architect certification. Each top-level directory is a self-contained module implementing a progressively more advanced agent architecture pattern using the Anthropic API and Claude Agent SDK.

## Commands

```bash
# Run tests for the shared library
pytest lib/tests/
pytest lib/tests/ -v

# Run any module
cd <module>
pip install -r requirements.txt
python main.py
```

Each module manages its own `requirements.txt`. The root has no unified build step.

## Architecture

### Module progression

| Module | Pattern |
|--------|---------|
| `hello_world/` | Agent SDK basics, bug-fixing demo |
| `stop_reason/` | Raw Messages API tool loop |
| `decision_making/` | Code-driven vs. model-driven routing |
| `end_loop_correctly/` | Proper loop termination |
| `coordinator_agent_basic/` | Hub-and-spoke coordinator with specialist tools |
| `dynamic_selection/` | Pipeline classification before coordinator dispatch |
| `research_partitioning/` | Non-overlapping scope generation for parallel research |
| `refinement_loop/` | Self-evaluating coordinator with iteration guard |
| `coordinator_observability/` | Logging, error resilience, parallel dispatch |

### Shared library (`lib/agent_output_parser`)

Reusable formatter/logger for Agent SDK messages. Imported in modules via:
```python
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from agent_output_parser import print_message, format_message
```

- `format_message(message)` — formats without side effects
- `print_message(message)` — prints to stdout AND writes to `logs/<YYYY-MM-DDTHH-MM-SS>.log`

Log files are created lazily; one per run, under the calling module's `logs/` directory.

### Two API styles used across modules

**Raw Messages API** (`stop_reason/`, `decision_making/`):
```python
client = AsyncAnthropic()
while response.stop_reason == "tool_use":
    # append tool result and call again
```

**Claude Agent SDK** (`hello_world/`, coordinators):
```python
async for message in query(...):
    print_message(message)
```

### Coordinator pattern

Specialists are modeled as tools. The coordinator calls a tool → the tool handler runs a full sub-agent (isolated history) → result is appended to coordinator history. Coordinators never share history between specialists.

Key implementation details:
- `MAX_REFINEMENT_ITERATIONS` guards coordinator loops
- `COVERAGE_THRESHOLD` (8/10) as a stopping condition in refinement modules
- `asyncio.gather()` for concurrent specialist dispatch in observability module
- `run_id = str(uuid.uuid4())` for correlating logs across a single run

## Environment

`ANTHROPIC_API_KEY` must be set in `.env` (loaded via `python-dotenv`).
