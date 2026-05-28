# lib — Shared Python Libraries

Reusable Python libraries for projects in this workspace.

---

## `agent_output_parser`

Formats `claude_agent_sdk` message objects into human-readable terminal output and writes every displayed message to a timestamped log file in the calling project's `logs/` directory.

### What it handles

| Message type | Output |
|---|---|
| `SystemMessage` (init) | `[session] model=… session=…` |
| `AssistantMessage` | Text, thinking (truncated), tool calls, tool results |
| `UserMessage` (string) | `[user] …` |
| `RateLimitEvent` | Warning/rejection only; `allowed` is silent |
| `TaskStartedMessage` | `[task started] …` |
| `TaskNotificationMessage` | `[task completed/failed] …` |
| `MirrorErrorMessage` | `[mirror error] …` |
| `ResultMessage` | Summary block: status, turns, time, cost, tokens, result text |
| Everything else | Silent |

### Importing from a project in this workspace

Add the workspace `lib/` directory to `sys.path` at the top of your script using a path relative to the script's own location:

```python
import sys
from pathlib import Path

# Resolve lib/ relative to this file, regardless of where you run from
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from agent_output_parser import print_message, format_message
```

Adjust `parent.parent` to match how many levels deep your script is from the workspace root. For a script at `<workspace>/my_project/main.py`, `parent` is `my_project/` and `parent.parent` is the workspace root.

### Usage

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(prompt="...", options=ClaudeAgentOptions(...)):
    print_message(message)   # prints to stdout AND writes to logs/<timestamp>.log
```

Or inspect the formatted string yourself (no logging side effect):

```python
from agent_output_parser import format_message

text = format_message(message)     # str | None
if text is not None:
    my_logger.info(text)
```

### Automatic logging

`print_message` writes every non-silent message to a log file alongside stdout. The log file is created lazily on the first message of each run:

- **Location**: `<project_dir>/logs/<YYYY-MM-DDTHH-MM-SS>.log`
- **`<project_dir>`** is the directory containing the `__main__` script (e.g. `hello_world/` when running `hello_world/main.py`). Falls back to `cwd` if `__main__.__file__` is unset.
- **One file per run**: the timestamp is captured once on first write, so all messages from a single run land in the same file.
- `logs/` is created automatically if it does not exist.

`format_message` is unaffected — it only formats, never logs.

### File layout

```
lib/
  agent_output_parser/
    __init__.py      # exports format_message, print_message
    formatter.py     # message formatting + print_message (calls logger)
    _logger.py       # lazy file-based logger (internal)
  tests/
    test_formatter.py
```

### Requirements

`claude_agent_sdk` must be installed in the Python environment running your script. The library has no other dependencies.

---

## Running the tests

Tests live in `lib/tests/` and use `pytest`. Run from the **workspace root**:

```bash
pytest lib/tests/
```

Or with verbose output:

```bash
pytest lib/tests/ -v
```

The test suite covers `formatter.py` — all message types, truncation behaviour, tool input formatting, and `print_message` stdout behaviour. `_logger.py` is not exercised by the current tests; `print_message` tests patch `builtins.print` and the logger writes to a real file silently alongside.
