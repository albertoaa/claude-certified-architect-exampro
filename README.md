# Claude Certified Architect — Exam Practice

Study repo for the [Claude Certified Architect](https://www.anthropic.com) certification. Each folder is a standalone exercise covering a core architectural concept.

## Progress

| # | Module | Concept | Status |
|---|--------|---------|--------|
| 1 | [`hello_world/`](#hello_world) | Claude Agent SDK — autonomous bug-fixing agent | ✅ Done |
| 2 | [`stop_reason/`](#stop_reason) | Anthropic Messages API — `stop_reason`-driven tool loop | ✅ Done |
| 3 | [`decision_making/`](#decision_making) | Code-driven vs model-driven routing | ✅ Done |
| 4 | [`end_loop_correctly/`](#end_loop_correctly) | Safe loop termination (max iterations + exit conditions) | ✅ Done |
| 5 | [`coordinator_agent_basic/`](#coordinator_agent_basic) | Hub-and-spoke coordinator + job application screener | ✅ Done |
| 6 | [`dynamic_selection/`](#dynamic_selection) | Pipeline selection — classify request, expose only needed specialists | ✅ Done |

---

## Modules

### `hello_world/`

First contact with the **Claude Agent SDK**. An agent is given the tools `Read`, `Edit`, and `Bash` and tasked with finding and fixing a bug in `hello_world.rb`. The `lib/agent_output_parser` library pretty-prints and logs all agent messages.

```bash
cd hello_world
pip install -r requirements.txt
python main.py
```

---

### `stop_reason/`

Uses the raw **Anthropic Messages API** (`AsyncAnthropic`) to drive a tool-use loop. The loop continues as long as `response.stop_reason == "tool_use"`, executing the requested tool on each iteration, appending the result to the message history, and calling the API again.

```bash
cd stop_reason
pip install -r requirements.txt
python main.py
```

---

### `decision_making/`

Side-by-side comparison of two routing architectures using the same "Magic Eyeball" domain:

- **`code-driven.py`** — The application classifies the user's question (`FORTUNE` / `GENERAL` / `UNCLEAR`) with a small LLM call, then branches with `if/elif` in Python.
- **`model-driven.py`** — Routing logic lives in the tool descriptions and system prompt; the model decides which tool to call.

```bash
# no separate requirements.txt — uses the same deps as stop_reason/
python decision_making/code-driven.py
python decision_making/model-driven.py
```

---

### `end_loop_correctly/`

Extends the model-driven loop with proper exit conditions: a `for iteration in range(max_iterations)` guard (max 10) combined with a `break` when `stop_reason != "tool_use"`. Demonstrates safe, bounded agentic loops.

```bash
python end_loop_correctly/main.py
```

---

### `coordinator_agent_basic/`

**Coordinator–subagent** orchestration with the Messages API (`main.py`) and a full **job application screener** example:

- **`job_application_screener/`** — Claude Code subagents (`.claude/agents/`), coordinator `CLAUDE.md`, fixtures, and `main.py` that loads the same spoke definitions for API runs.

```bash
cd coordinator_agent_basic/job_application_screener
pip install -r requirements.txt
python main.py
```

For Claude Code, start a session in `job_application_screener/` and use `/agents` to verify the four spokes. See `job_application_screener/README.md`.

---

### `dynamic_selection/`

Extends the coordinator pattern with **pipeline selection**: before the coordinator runs, a cheap classifier call maps the user's request to one of four pipelines (`DIRECT`, `RESEARCH_ONLY`, `WRITING_ONLY`, `RESEARCH_AND_WRITE`). The coordinator is then offered only the tools that pipeline needs — irrelevant specialists are never reachable.

Combines the code-driven routing pattern from `decision_making/` with the hub-and-spoke coordinator from `coordinator_agent_basic/`.

```bash
python dynamic_selection/main.py
```

---

## Shared Library — `lib/`

`agent_output_parser` is a reusable module for the Agent SDK exercises. It formats and logs all SDK message types to stdout and to `<project>/logs/<timestamp>.log`.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from agent_output_parser import print_message
```

Run the test suite from the workspace root:

```bash
pytest lib/tests/
```

---

## Setup

Most exercises rely on the Anthropic API. Create a `.env` file in the workspace root (already git-ignored):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Agent SDK exercises additionally require:

```bash
pip install claude-agent-sdk
```

Anthropic Messages API exercises require:

```bash
pip install "anthropic[aiohttp]" python-dotenv
```

---

## Reference Materials

- `Claude-Certified-Architect-Slides.pdf` — official exam slide deck
- `claude-certified-architect-cheatsheets.pdf` — quick-reference cheatsheets
