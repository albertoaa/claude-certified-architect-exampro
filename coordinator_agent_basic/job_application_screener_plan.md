# Job Application Screener — Claude Code Plan

Transform the hub-and-spoke sketch into a **Claude Code** project: the **main session is the coordinator**; each spoke is a **custom subagent** under `.claude/agents/`. The coordinator delegates with the **Task** tool (subagent spawning). Spokes never talk to each other; all data flows through the coordinator.

Reference: [Create custom subagents](https://code.claude.com/docs/en/sub-agents.md)

---

## Architecture (unchanged intent)

| Role | Claude Code mapping |
|------|---------------------|
| **Hub (coordinator)** | Main Claude Code session + project `CLAUDE.md` |
| **Spokes** | Files in `.claude/agents/*.md` (isolated context per Task) |
| **Routing** | Coordinator reads user request + subagent `description` fields; chooses which Tasks to run |
| **Aggregation** | Coordinator calls `score-aggregator` only after evaluator spokes finish |

### Spokes

| Spoke | Job |
|-------|-----|
| `keyword-scanner` | Fast must-have skills / qualifications check |
| `deep-evaluator` | Experience depth, context, seniority fit |
| `red-flag-detector` | Disqualifiers across application + resume |
| `score-aggregator` | Hire / pass / maybe from **all** spoke outputs |

---

## Project layout

Create under `coordinator_agent_basic/job_application_screener/` (or keep at `coordinator_agent_basic/` if you prefer one module):

```
job_application_screener/
  CLAUDE.md                    # Coordinator rules (hub behavior)
  .claude/
    agents/
      keyword-scanner.md
      deep-evaluator.md
      red-flag-detector.md
      score-aggregator.md
  fixtures/                    # Optional sample inputs for local runs
    job_posting.md
    candidate_resume.md
    application_answers.md
  logs/                        # Created by agent_output_parser if using SDK runner
```

Restart Claude Code after adding or editing `.claude/agents/*.md` on disk (or use `/agents` for immediate load).

---

## Phase 1 — Coordinator `CLAUDE.md`

The coordinator owns orchestration, not screening logic. Put this in `job_application_screener/CLAUDE.md`:

```markdown
# Job Application Screener (Coordinator)

You are the coordinator for hiring screening. You do not score candidates yourself.

## Inputs you need
- Job posting (requirements, seniority, must-haves)
- Candidate resume
- Application answers (cover letter, short answers, etc.)

If any input is missing, ask once; do not call spokes until you have all three.

## Orchestration (mandatory order)

### Phase A — Parallel evaluation (one turn, multiple Task calls)
Delegate in parallel when possible:
1. `keyword-scanner` — pass: job posting + resume + application text
2. `deep-evaluator` — pass: job posting + resume + application text
3. `red-flag-detector` — pass: job posting + resume + application text

Each Task prompt must include ONLY what that spoke needs (no full chat history).

### Phase B — Aggregation (after Phase A completes)
4. `score-aggregator` — pass: structured JSON summaries from all three spokes (see contracts below)

Never call `score-aggregator` before the three evaluators return.

## Hub-and-spoke rules
- Spokes never communicate with each other.
- Do not paste the entire coordinator thread into a spoke prompt.
- On red-flag `block` or keyword `fail`, you may skip deep evaluation only if the user asked for a fast path; default is still run all three, then let the aggregator decide.

## Final deliverable
Return to the user: decision (`hire` | `pass` | `maybe`), confidence, top 3 reasons, and any red flags — using the aggregator output as source of truth.
```

---

## Phase 2 — Subagent files

Each file: YAML frontmatter + markdown body (system prompt). Names use **lowercase + hyphens** (required by Claude Code).

### `keyword-scanner.md`

```markdown
---
name: keyword-scanner
description: Fast must-have skills and qualifications check. Use when screening whether a candidate meets hard requirements.
tools: Read, Grep, Glob
model: haiku
---

You are the keyword scanner spoke. You only check explicit must-haves.

Input (in the Task prompt): job posting, resume, application text.

Output **only** valid JSON:
{
  "status": "pass" | "fail" | "partial",
  "matched_must_haves": ["..."],
  "missing_must_haves": ["..."],
  "notes": "one short paragraph"
}
```

### `deep-evaluator.md`

```markdown
---
name: deep-evaluator
description: Assesses experience depth, context, and seniority fit against the role.
tools: Read, Grep, Glob
model: sonnet
---

You are the deep evaluator spoke. Judge quality of experience, not keyword presence.

Output **only** valid JSON:
{
  "seniority_fit": "under" | "match" | "over",
  "experience_depth_score": 1-10,
  "strong_signals": ["..."],
  "gaps": ["..."],
  "notes": "one short paragraph"
}
```

### `red-flag-detector.md`

```markdown
---
name: red-flag-detector
description: Finds disqualifiers and inconsistencies across resume and application data.
tools: Read, Grep, Glob
model: sonnet
---

You are the red-flag detector spoke. Be conservative; cite evidence.

Output **only** valid JSON:
{
  "severity": "none" | "low" | "high" | "block",
  "flags": [{"type": "...", "evidence": "...", "source": "resume|application|both"}],
  "notes": "one short paragraph"
}
```

### `score-aggregator.md`

```markdown
---
name: score-aggregator
description: Produces final hire/pass/maybe from evaluator spoke JSON. Use only after keyword, deep, and red-flag results exist.
tools: Read
model: sonnet
---

You are the score aggregator spoke. You do not re-read raw resumes unless the coordinator pasted evaluator JSON.

Input: JSON blobs from keyword-scanner, deep-evaluator, red-flag-detector.

Output **only** valid JSON:
{
  "decision": "hire" | "pass" | "maybe",
  "confidence": 0.0-1.0,
  "reasons": ["top reason 1", "top reason 2", "top reason 3"],
  "summary": "2-3 sentences for the hiring manager"
}
```

---

## Phase 3 — Coordinator permissions

In Claude Code settings for this project (or session), the **coordinator** must be able to spawn subagents:

- Ensure **Task** (subagent delegation) is allowed for the main session.
- Spokes inherit their own `tools` allowlists from frontmatter (read-only evaluators; no `Edit`/`Write` unless you add report generation later).

Optional: restrict coordinator to `Read`, `Grep`, `Glob`, and **Task** only so it cannot “screen” without delegating.

---

## Phase 4 — Context passing (exam-critical)

For each Task, the coordinator prompt should look like:

```
Screen this candidate.

## Job posting
<paste or path: fixtures/job_posting.md>

## Resume
<paste or path: fixtures/candidate_resume.md>

## Application
<paste or path: fixtures/application_answers.md>

Return JSON per your spoke contract.
```

For `score-aggregator`:

```
Aggregate these evaluator results:

keyword_scanner: { ... }
deep_evaluator: { ... }
red_flag_detector: { ... }
```

**Do not** forward the full coordinator conversation to spokes.

---

## Phase 5 — How to run in Claude Code

1. `cd coordinator_agent_basic/job_application_screener`
2. Add fixture files (or real data).
3. Start Claude Code in that directory.
4. Example user prompt:

   > Screen the candidate in `fixtures/` against `fixtures/job_posting.md`. Run keyword, deep, and red-flag evaluation, then aggregate a final decision.

5. Verify in the UI: three Tasks in parallel (or quick succession), then one `score-aggregator` Task, then coordinator summary.

Use `/agents` to list loaded subagents and confirm all four appear.

---

## Phase 6 — Optional programmatic runner (Agent SDK)

If you want the same architecture outside the CLI (like `main.py`):

| Piece | Implementation |
|-------|----------------|
| Coordinator | `claude_agent_sdk.query()` with prompt mirroring `CLAUDE.md` |
| Spokes | Separate `query()` calls per spoke **or** Task tool if `allowed_tools` includes Task |
| Loop | Same as `decision_making/model-driven.py`: `stop_reason` / tool loop |
| Output | Reuse `lib/agent_output_parser` for logging |

Map each spoke to either a **Task subagent name** (Claude Code style) or a **dedicated tool** that runs an isolated `messages.create` (current `coordinator_agent_basic/main.py` pattern).

---

## Routing matrix (coordinator decisions)

| User request | Spokes to call |
|--------------|----------------|
| Full screen | All three evaluators → `score-aggregator` |
| “Quick must-haves only” | `keyword-scanner` only; coordinator summarizes (no aggregator unless user asks) |
| “Red flags only” | `red-flag-detector` only |
| “Final decision” (evaluator JSON already provided) | `score-aggregator` only |

Default path for certification-style demos: **full pipeline**.

---

## Checklist before calling it done

- [x] Four subagent files under `.claude/agents/` with unique `name` values
- [x] Coordinator `CLAUDE.md` enforces Phase A → Phase B order
- [x] Each spoke returns structured JSON (easy for aggregator + tests)
- [x] Fixture trio: job posting, resume, application
- [x] Confirmed: spokes never receive each other’s outputs directly
- [x] Confirmed: `score-aggregator` receives only evaluator JSON
- [ ] Sample run produces `hire` | `pass` | `maybe` with reasons (run `python main.py`)

---

## Mapping from original sketch

| Original | Claude Code |
|----------|-------------|
| Hub coordinator | Main session + `CLAUDE.md` |
| Spokes | `.claude/agents/<name>.md` |
| “Call spokes with right input” | Task tool + explicit per-spoke prompt |
| “Routing” | Coordinator instructions + subagent `description` |
| “Combine outputs” | Phase B Task to `score-aggregator` + final user message |
