# Claude Certified Architect — Exam Practice

Study repo for the [Claude Certified Architect](https://www.anthropic.com) certification. Each folder is a standalone exercise covering a core architectural concept.

## Progress

| # | Module | Concept | Status |
| --- | -------- | --------- | -------- |
| 1 | [`hello_world/`](#hello_world) | Claude Agent SDK — autonomous bug-fixing agent | ✅ Done |
| 2 | [`stop_reason/`](#stop_reason) | Anthropic Messages API — `stop_reason`-driven tool loop | ✅ Done |
| 3 | [`decision_making/`](#decision_making) | Code-driven vs model-driven routing | ✅ Done |
| 4 | [`end_loop_correctly/`](#end_loop_correctly) | Safe loop termination (max iterations + exit conditions) | ✅ Done |
| 5 | [`coordinator_agent_basic/`](#coordinator_agent_basic) | Hub-and-spoke coordinator + job application screener | ✅ Done |
| 6 | [`dynamic_selection/`](#dynamic_selection) | Pipeline selection — classify request, expose only needed specialists | ✅ Done |
| 7 | [`research_partitioning/`](#research_partitioning) | Partition generation — non-overlapping task scopes with explicit covers/excludes | ✅ Done |
| 8 | [`refinement_loop/`](#refinement_loop) | Self-evaluating refinement loop — coordinator scores its own synthesis and re-delegates until coverage is sufficient | ✅ Done |
| 9 | [`coordinator_observability/`](#coordinator_observability) | Observability layer — structured logging, error resilience, parallel dispatch, token tracking, and run correlation IDs | ✅ Done |

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

### `research_partitioning/`

Extends the dynamic-selection coordinator with a **partition generation** step that eliminates token waste from overlapping research agents. Before the coordinator runs, a dedicated call decomposes the request into non-overlapping partitions — each with an explicit `covers` list (its bounded scope) and an `excludes` list (the other partitions' topics). The coordinator receives the partition JSON in its system prompt and is instructed to call `research_specialist` exactly once per partition, staying within its scope.

Key additions over `dynamic_selection/`:

- `generate_partitions()` — cheap pre-flight call that produces the `{ partitions: [...] }` JSON structure and strips markdown fences before parsing
- Partition JSON is printed at startup so the human can verify scope boundaries before any specialist runs
- `run_coordinator()` builds a dynamic system prompt: base instructions plus the partition map when research is involved

```bash
python research_partitioning/main.py
```

### `refinement_loop/`

Extends the research-partitioning coordinator with a **self-evaluating refinement loop** for `RESEARCH_AND_WRITE` requests. Instead of delegating once and stopping, the coordinator iterates — scoring its own synthesis and re-delegating targeted gap-filling queries — until coverage is sufficient or the iteration budget is exhausted.

The key forcing function is the `evaluate_coverage` tool: the coordinator must commit to a numeric score (0–10) and an explicit gap list in structured output before the loop can advance. The tool result (`SUFFICIENT` / `NEEDS_REFINEMENT`) then drives loop control, and the score + gaps are recorded in conversation history so later iterations know exactly what was already tried.

Four tools replace the previous specialist pair:

| Tool | Role |
| ------ | ------ |
| `delegate_research` | Send a targeted query to the research specialist |
| `delegate_synthesis` | Send all collected findings to the writer for a draft |
| `evaluate_coverage` | Score the draft and list gaps — controls whether the loop continues |
| `submit_final` | Terminate the loop and deliver the final answer |

Key additions over `research_partitioning/`:

- `REFINEMENT_COORDINATOR_PROMPT` — instructs the coordinator to evaluate after each synthesis and only call `submit_final` when confident
- `run_refinement_coordinator()` — agentic loop that handles all four tools; `evaluate_coverage` returns either `SUFFICIENT` or `NEEDS_REFINEMENT` with remaining iteration count
- `MAX_REFINEMENT_ITERATIONS = 4` / `COVERAGE_THRESHOLD = 8` — configurable loop guards
- `_bar()` — renders a `█`/`░` block-character score bar so coverage progress is visible at a glance
- Terminal output uses `[RESEARCH]` / `[SYNTHESIS]` / `[EVALUATE]` step labels; the evaluate line shows iteration number, score, bar, and decision on one line; gaps are printed as a bullet list; the final answer header includes the full score trail (e.g. `scores: 6/10 → 9/10`)
- `main()` routes `RESEARCH_AND_WRITE` to the refinement coordinator; other pipelines fall through to `run_coordinator()` as before

Example terminal output for a two-iteration run:

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  REFINEMENT LOOP  (max 4 iterations · threshold 8/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [RESEARCH]   What are the cardiovascular benefits of morning exercise?
               Reduces resting heart rate, lowers blood pressure...

  [SYNTHESIS]  Rise early and move — morning exercise is one of the...

  [EVALUATE]   iteration 1/4  ·  score  6/10  [████████████░░░░░░░░]  NEEDS REFINEMENT  (3 left)
               gaps:
                 • No specific statistics cited
                 • Long-term vs short-term effects not distinguished

  [RESEARCH]   Specific statistics on cardiovascular and metabolic benefits...
               A 2023 meta-analysis found 150 min/week reduces cardiac...

  [SYNTHESIS]  Science backs every sunrise sprint: regular morning...

  [EVALUATE]   iteration 2/4  ·  score  9/10  [██████████████████░░]  SUFFICIENT ✓
               no gaps identified

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FINAL ANSWER  (scores: 6/10 → 9/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```bash
python refinement_loop/main.py
```

---

### `coordinator_observability/`

Extends the refinement-loop coordinator with a production-quality **observability layer** and several resilience fixes. All output now flows through `_log()` — a thin wrapper that writes to stdout and persists to `logs/<timestamp>.log` via the shared `lib/agent_output_parser/_logger` — so every run can be replayed from disk.

Key additions over `refinement_loop/`:

- `_log()` — replaces all bare `print()` calls; writes to stdout **and** `coordinator_observability/logs/<timestamp>.log`
- Structured per-turn logging — replaces the noisy raw JSON dump (`response.to_dict()`) with a one-liner: `stop=end_turn  tokens=412↑/87↓`
- `run_id` — `uuid4` hex prefix added to the refinement loop header so multiple runs in the same log file can be correlated
- `total_tokens` — cumulative input + output token count accumulated across all turns; shown in the final answer block
- `asyncio.gather()` — all specialist calls within a single coordinator turn are dispatched concurrently instead of sequentially; applies to both `run_coordinator` and `run_refinement_coordinator`
- Error resilience in `run_specialist` — `try/except APIError` returns a structured error string instead of crashing; unknown tool names are caught before the dict lookup
- Clean final output — when `stop_reason != "tool_use"`, text blocks are extracted and logged rather than dumping the full response object

```bash
python coordinator_observability/main.py
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

```env
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
