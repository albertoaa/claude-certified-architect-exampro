# Job Application Screener

Hub-and-spoke coordinator that screens a candidate against a job posting. Four spokes run in isolated context; the coordinator delegates via tools (Messages API) or Task (Claude Code).

## Layout

```
job_application_screener/
  CLAUDE.md                 # Coordinator (hub) instructions
  .claude/agents/           # Spoke definitions for Claude Code
  fixtures/                 # Sample job, resume, application
  main.py                   # Programmatic coordinator (Anthropic API)
```

## Spokes

| Spoke | Phase | Role |
|-------|-------|------|
| `keyword-scanner` | A | Must-have skills / qualifications |
| `deep-evaluator` | A | Experience depth and seniority fit |
| `red-flag-detector` | A | Disqualifiers and inconsistencies |
| `score-aggregator` | B | Final `hire` / `pass` / `maybe` |

Phase A evaluators can run in parallel (multiple tool calls in one coordinator turn). Phase B runs only after all three return JSON.

## Run with Python (Messages API)

From the workspace root, ensure `.env` contains `ANTHROPIC_API_KEY`.

```bash
cd coordinator_agent_basic/job_application_screener
pip install -r requirements.txt
python main.py
```

`main.py` loads coordinator rules from `CLAUDE.md` and spoke prompts from `.claude/agents/*.md`, then screens the `fixtures/` trio.

## Run with Claude Code

```bash
cd coordinator_agent_basic/job_application_screener
claude
```

Example prompt:

> Screen the candidate using files in `fixtures/`. Run keyword, deep, and red-flag evaluation, then aggregate a final decision.

Use `/agents` to confirm all four subagents loaded. Restart the session after editing agent files on disk.

## Sample fixtures

The bundled candidate (Alex Chen) is intentionally mixed: strong Python and distributed-systems fit, no production PostgreSQL, and a **years-of-experience** mismatch (resume implies ~6 years; application claims 8).
