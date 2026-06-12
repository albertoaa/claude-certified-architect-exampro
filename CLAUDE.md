# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Study repo for the Claude Certified Architect certification. Nine progressive modules, each teaching a distinct agentic architecture pattern. Every module is a self-contained, runnable Python exercise.

## Setup

Create `.env` in the workspace root (already git-ignored):
```env
ANTHROPIC_API_KEY=sk-ant-...
```

## Running Modules

Each module is independent. The typical pattern:
```bash
cd <module_name>
pip install -r requirements.txt
python main.py
```

Modules 3 and 4 share the `stop_reason/` deps and run from the workspace root:
```bash
python decision_making/code-driven.py
python decision_making/model-driven.py
python end_loop_correctly/main.py
```

The `coordinator_agent_basic/job_application_screener` module can also run as a Claude Code session (start `claude` from that directory; the `.claude/agents/` definitions wire up the four subagents automatically).

## Tests

```bash
# From workspace root
pytest lib/tests/
pytest lib/tests/ -v               # verbose
pytest lib/tests/test_formatter.py # single file
```

## Architecture Progression

Modules build on each other in a straight line:

| Module | Pattern added |
|--------|--------------|
| `hello_world/` | Agent SDK — autonomous loop with tools |
| `stop_reason/` | Raw Messages API — `stop_reason == "tool_use"` loop |
| `decision_making/` | Code-driven vs model-driven routing |
| `end_loop_correctly/` | Bounded loop: `for i in range(max)` + `break` |
| `coordinator_agent_basic/` | Hub-and-spoke: coordinator delegates to isolated specialists |
| `dynamic_selection/` | Pipeline classifier limits which specialist tools are exposed |
| `research_partitioning/` | `generate_partitions()` pre-flight produces non-overlapping scopes with `covers`/`excludes` |
| `refinement_loop/` | `evaluate_coverage` tool drives a score-gated re-delegation loop |
| `coordinator_observability/` | `_log()` to stdout + file, `run_id`, token totals, `asyncio.gather()` parallel dispatch, `APIError` resilience |

## Key Patterns

**Standard coordinator loop** (modules 5–9): coordinator receives tools for each specialist; spokes are called via `run_specialist()` which makes a one-shot Messages API call with no tools, returns plain text.

**Dynamic tool exposure** (`dynamic_selection/`): `PIPELINES` dict maps classifier output to a subset of `ALL_TOOLS`. The coordinator system prompt is built at runtime from only the relevant tools.

**Partition generation** (`research_partitioning/`): A pre-flight `generate_partitions()` call produces `{ partitions: [{topic, covers, excludes}] }`. The JSON is injected into the coordinator's system prompt so each `research_specialist` call stays in its lane.

**Refinement loop** (`refinement_loop/`, `coordinator_observability/`): Four tools replace the earlier specialist pair — `delegate_research`, `delegate_synthesis`, `evaluate_coverage`, `submit_final`. `evaluate_coverage` returns `SUFFICIENT` or `NEEDS_REFINEMENT`; the loop continues until the threshold (`COVERAGE_THRESHOLD = 8`) or budget (`MAX_REFINEMENT_ITERATIONS = 4`) is hit.

**Observability** (`coordinator_observability/`): All output goes through `_log()` which writes to stdout and `logs/<timestamp>.log`. Each API turn is summarized as `stop=end_turn  tokens=412↑/87↓`. A `run_id` (uuid4) in the loop header correlates runs in shared log files.

## Shared Library — `lib/`

`lib/agent_output_parser` formats and logs Agent SDK messages. Import pattern used in Agent SDK modules:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from agent_output_parser import print_message
```

The `_logger.py` lazy file logger in `lib/agent_output_parser/` is reused by `coordinator_observability/` for its `_log()` wrapper.

## Models Used

- Most modules: `claude-haiku-4-5-20251001` for cost efficiency
- `hello_world/` (Agent SDK): model set in `main.py` agent config
- `coordinator_agent_basic/job_application_screener` spokes: `claude-haiku-4-5-20251001` per agent `.md` file
