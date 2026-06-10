import os
import re
import sys
import json
import time
import uuid
import asyncio
from pathlib import Path
from anthropic import AsyncAnthropic, DefaultAioHttpClient, APIError
from dotenv import load_dotenv

# Wire in the shared logger from lib/
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from agent_output_parser._logger import log as _log_to_file

load_dotenv()


def _log(msg: str) -> None:
    """Print to stdout and persist to the run's log file."""
    print(msg)
    _log_to_file(msg)


SYSTEM_PROMPT = """You are a coordinator assistant.
Before delegating, plan the full sequence of subtasks and identify which can run in parallel.
Use research_specialist for factual research. You may call it multiple times for independent subtopics.
Use writer_specialist for drafting or polishing text.
When a specialist's output is needed by another, include it verbatim in the next specialist's task field.
Synthesize specialist results into a final answer for the user.
"""

ALL_TOOLS = [
    {
        "name": "research_specialist",
        "description": "Runs a research subagent for factual questions and information gathering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The research subtask and any context the specialist needs",
                }
            },
            "required": ["task"],
        },
    },
    {
        "name": "writer_specialist",
        "description": "Runs a writing subagent to draft or edit prose.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The writing subtask and any context the specialist needs",
                }
            },
            "required": ["task"],
        },
    },
]

TOOLS_BY_NAME = {tool["name"]: tool for tool in ALL_TOOLS}

# Each pipeline lists only the specialists that request type needs.
# The coordinator is only offered tools from the selected pipeline,
# so it cannot accidentally invoke irrelevant specialists.
PIPELINES = {
    "RESEARCH_ONLY":      ["research_specialist"],
    "WRITING_ONLY":       ["writer_specialist"],
    "RESEARCH_AND_WRITE": ["research_specialist", "writer_specialist"],
    "DIRECT":             [],
}

SPECIALIST_PROMPTS = {
    "research_specialist": "You are a research specialist. Answer with concise factual points only.",
    "writer_specialist": "You are a writing specialist. Produce clear, polished prose.",
}

# ── Refinement-loop constants ────────────────────────────────────────────────

MAX_REFINEMENT_ITERATIONS = 4
COVERAGE_THRESHOLD = 8  # score out of 10; at or above this → sufficient

REFINEMENT_COORDINATOR_PROMPT = """You are a research coordinator. Your job is not just to delegate once —
it is to ensure the final output is complete.

Workflow:
1. Call delegate_research one or more times (in parallel if topics are independent) to gather information.
2. Collect all results, then call delegate_synthesis with ALL research findings and the original task.
3. Call evaluate_coverage with: the synthesis text, a coverage score (0–10), and a list of gaps.
4. If the response says NEEDS_REFINEMENT, call delegate_research for each listed gap, re-synthesize, then evaluate again.
5. Call submit_final only when evaluate_coverage returns SUFFICIENT, or when you have no iterations left.

After each synthesis, honestly evaluate it against the original task:
- What dimensions are missing or thin?
- What claims lack supporting evidence?
- What follow-up questions does the draft raise but not answer?

Score guidance for evaluate_coverage:
  9–10 : All aspects covered with strong evidence
  7–8  : Good coverage, only minor gaps
  5–6  : Moderate coverage, notable gaps
  0–4  : Significant gaps, major aspects missing

You have a maximum of 4 refinement iterations. Use them wisely.
"""

REFINEMENT_TOOLS = [
    {
        "name": "delegate_research",
        "description": "Send a research query to the research agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The specific research question to investigate",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "delegate_synthesis",
        "description": "Send all collected research to the writer agent for synthesis into a coherent answer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "research_data": {
                    "type": "string",
                    "description": "All research findings collected so far, verbatim",
                },
                "original_task": {
                    "type": "string",
                    "description": "The original user task/question being answered",
                },
            },
            "required": ["research_data", "original_task"],
        },
    },
    {
        "name": "evaluate_coverage",
        "description": (
            "Score the current synthesis and identify gaps. "
            "This forces a structured commitment before the loop can continue — "
            "the score and gaps are recorded in history so subsequent iterations know what was already tried."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "synthesis": {
                    "type": "string",
                    "description": "The current synthesis to evaluate",
                },
                "score": {
                    "type": "integer",
                    "description": "Coverage score from 0 (nothing covered) to 10 (fully complete)",
                },
                "gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Missing dimensions, unsupported claims, or unanswered follow-up questions. "
                        "Empty list means no gaps."
                    ),
                },
            },
            "required": ["synthesis", "score", "gaps"],
        },
    },
    {
        "name": "submit_final",
        "description": "Submit the final response when coverage is sufficient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "The complete, final answer to submit to the user",
                }
            },
            "required": ["answer"],
        },
    },
]


async def generate_partitions(
    client: AsyncAnthropic,
    model: str,
    request: str,
) -> dict:
    """Generate non-overlapping research partitions before the coordinator runs."""
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=(
            "You are a task decomposition specialist. Given a research request, split it into "
            "non-overlapping partitions — each covering a distinct aspect with no topic overlap.\n"
            "For each partition specify what it COVERS and what it EXCLUDES (the other partitions' topics).\n"
            "Return ONLY valid JSON with this exact shape:\n"
            '{"partitions": [{"agent": "<snake_case_name>", "scope": {"topic": "<short topic>", '
            '"covers": ["<specific point>", ...], "excludes": ["<excluded topic>", ...]}}]}'
        ),
        messages=[{"role": "user", "content": request}],
    )
    text = response.content[0].text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


async def classify_request(client: AsyncAnthropic, model: str, request: str) -> str:
    """One cheap call that picks the right pipeline before the coordinator runs."""
    response = await client.messages.create(
        model=model,
        max_tokens=10,
        system=(
            "Classify the user's request. Reply with exactly one label:\n"
            "RESEARCH_ONLY    — needs facts/lookup, no writing.\n"
            "WRITING_ONLY     — needs prose drafting/editing, no research.\n"
            "RESEARCH_AND_WRITE — needs both research and writing.\n"
            "DIRECT           — simple question, no specialists needed."
        ),
        messages=[{"role": "user", "content": request}],
    )
    label = response.content[0].text.strip().upper()
    return label if label in PIPELINES else "RESEARCH_AND_WRITE"


async def run_specialist(
    client: AsyncAnthropic,
    model: str,
    name: str,
    task: str,
) -> str:
    if name not in SPECIALIST_PROMPTS:
        _log(f"  [ERROR] Unknown specialist: '{name}'")
        return f"[ERROR] Unknown specialist: '{name}'"

    t0 = time.perf_counter()
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            system=SPECIALIST_PROMPTS[name],
            messages=[{"role": "user", "content": task}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        result = "\n".join(text_blocks) if text_blocks else "(no response)"
    except APIError as exc:
        result = f"[ERROR] Specialist '{name}' failed: {exc}"

    elapsed = time.perf_counter() - t0
    _log(f"  [{name}] completed in {elapsed:.2f}s")
    return result


async def run_coordinator(
    client: AsyncAnthropic,
    model: str,
    messages: list,
    selected_tools: list,
    partitions: dict | None = None,
) -> None:
    """Coordinator loop restricted to the pre-selected tool set."""
    system = SYSTEM_PROMPT
    if partitions:
        system += (
            "\n\nResearch partitions (strictly follow these — no overlap between agents):\n"
            + json.dumps(partitions, indent=2)
            + "\nCall research_specialist once per partition, using its 'covers' as the exact "
            "research scope and respecting its 'excludes' to avoid duplication."
        )

    while True:
        create_kwargs = dict(
            model=model,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        if selected_tools:
            create_kwargs["tools"] = selected_tools

        response = await client.messages.create(**create_kwargs)

        _log(
            f"  [coordinator] stop={response.stop_reason}"
            f"  tokens={response.usage.input_tokens}↑/{response.usage.output_tokens}↓"
        )

        if response.stop_reason != "tool_use":
            for block in response.content:
                if hasattr(block, "text"):
                    _log(block.text)
            break

        tool_uses = [block for block in response.content if block.type == "tool_use"]

        # Dispatch all specialist calls concurrently — independent calls need not be serialized.
        tool_results = list(
            await asyncio.gather(*[
                run_specialist(client, model, tu.name, tu.input["task"])
                for tu in tool_uses
            ])
        )

        for tu, result in zip(tool_uses, tool_results):
            _log(f"\n>>> Specialist called: {tu.name}({tu.input})")
            _log(f">>> Specialist result: {result}\n")

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                }
                for tu, result in zip(tool_uses, tool_results)
            ],
        })


_W = 64  # terminal width for dividers


def _bar(score: int, width: int = 20) -> str:
    filled = round(score / 10 * width)
    return "█" * filled + "░" * (width - filled)


async def run_refinement_coordinator(
    client: AsyncAnthropic,
    model: str,
    user_request: str,
) -> None:
    """Coordinator with a self-evaluating refinement loop.

    evaluate_coverage forces the coordinator to commit to a score and gap list
    in structured output before the loop can continue. The tool result then
    drives the loop decision (SUFFICIENT vs NEEDS_REFINEMENT), and the score +
    gaps are recorded in conversation history so later iterations know what was
    already tried.
    """
    run_id = uuid.uuid4().hex[:8]
    messages = [{"role": "user", "content": user_request}]
    refinement_iteration = 0
    scores: list[int] = []
    total_tokens = 0

    _log(f"\n{'━' * _W}")
    _log(
        f"  REFINEMENT LOOP  run={run_id}"
        f"  (max {MAX_REFINEMENT_ITERATIONS} iterations · threshold {COVERAGE_THRESHOLD}/10)"
    )
    _log(f"{'━' * _W}\n")

    while True:
        response = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=REFINEMENT_COORDINATOR_PROMPT,
            messages=messages,
            tools=REFINEMENT_TOOLS,
        )

        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        _log(
            f"  [coordinator] stop={response.stop_reason}"
            f"  tokens={response.usage.input_tokens}↑/{response.usage.output_tokens}↓"
            f"  total={total_tokens:,}"
        )

        if response.stop_reason != "tool_use":
            for block in response.content:
                if hasattr(block, "text"):
                    _log(f"\n{block.text}\n")
            break

        tool_uses = [block for block in response.content if block.type == "tool_use"]

        # Pre-dispatch all remote specialist calls concurrently.
        # evaluate_coverage and submit_final are local (no API call) — they return None here.
        async def _dispatch(name: str, inp: dict) -> str | None:
            if name == "delegate_research":
                return await run_specialist(client, model, "research_specialist", inp["query"])
            if name == "delegate_synthesis":
                combined = (
                    f"Original task: {inp['original_task']}\n\nResearch findings:\n{inp['research_data']}"
                )
                return await run_specialist(client, model, "writer_specialist", combined)
            return None

        remote_results: list[str | None] = list(
            await asyncio.gather(*[_dispatch(tu.name, tu.input) for tu in tool_uses])
        )

        tool_results = []
        done = False

        for i, tool_use in enumerate(tool_uses):
            name = tool_use.name
            inp = tool_use.input

            if name == "delegate_research":
                result = remote_results[i]
                query_preview = inp["query"][:70] + ("..." if len(inp["query"]) > 70 else "")
                result_preview = result[:100] + ("..." if len(result) > 100 else "")
                _log(f"  [RESEARCH]   {query_preview}")
                _log(f"               {result_preview}\n")

            elif name == "delegate_synthesis":
                result = remote_results[i]
                result_preview = result[:100] + ("..." if len(result) > 100 else "")
                _log(f"  [SYNTHESIS]  {result_preview}\n")

            elif name == "evaluate_coverage":
                refinement_iteration += 1
                score: int = inp["score"]
                gaps: list = inp["gaps"]
                scores.append(score)

                sufficient = (
                    score >= COVERAGE_THRESHOLD
                    or not gaps
                    or refinement_iteration >= MAX_REFINEMENT_ITERATIONS
                )
                remaining = MAX_REFINEMENT_ITERATIONS - refinement_iteration
                decision = "SUFFICIENT ✓" if sufficient else f"NEEDS REFINEMENT  ({remaining} left)"

                _log(
                    f"  [EVALUATE]   iteration {refinement_iteration}/{MAX_REFINEMENT_ITERATIONS}"
                    f"  ·  score {score:2d}/10  [{_bar(score)}]  {decision}"
                )

                if gaps:
                    _log("               gaps:")
                    for gap in gaps:
                        _log(f"                 • {gap}")
                else:
                    _log("               no gaps identified")
                _log("")

                if sufficient:
                    result = json.dumps({
                        "decision": "SUFFICIENT",
                        "message": "Coverage is sufficient. Call submit_final with your synthesized answer.",
                    })
                else:
                    result = json.dumps({
                        "decision": "NEEDS_REFINEMENT",
                        "remaining_iterations": remaining,
                        "gaps": gaps,
                        "message": (
                            f"Score {score}/10 is below threshold ({COVERAGE_THRESHOLD}). "
                            f"{remaining} iteration(s) remaining. "
                            "Call delegate_research for each gap, then delegate_synthesis, "
                            "then evaluate_coverage again."
                        ),
                    })

            elif name == "submit_final":
                score_trail = " → ".join(f"{s}/10" for s in scores)
                _log(f"{'━' * _W}")
                _log(f"  FINAL ANSWER  (scores: {score_trail}  ·  total tokens: {total_tokens:,})")
                _log(f"{'━' * _W}")
                _log(inp["answer"])
                _log(f"{'━' * _W}\n")
                result = "Answer submitted successfully."
                done = True

            else:
                _log(f"  [WARN] Unrecognized tool: {name}")
                result = f"Unknown tool: {name}"

            tool_results.append(result)

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": res,
                }
                for tu, res in zip(tool_uses, tool_results)
            ],
        })

        if done:
            break


async def main() -> None:
    model = "claude-haiku-4-5-20251001"

    # Try different request types to see dynamic selection in action:
    # user_request = "What is the capital of France?"                               # → DIRECT
    # user_request = "What are the three main causes of the French Revolution?"     # → RESEARCH_ONLY
    # user_request = "Rewrite this to sound more professional: 'i did the thing'"  # → WRITING_ONLY
    user_request = (
        "Research three benefits of morning exercise, "
        "then write a short motivational paragraph using those points."
    )  # → RESEARCH_AND_WRITE  (uses refinement loop)

    async with AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=DefaultAioHttpClient(),
    ) as client:
        pipeline = await classify_request(client, model, user_request)
        _log(f">>> Pipeline selected: {pipeline}\n")

        if pipeline == "RESEARCH_AND_WRITE":
            # Use the refinement loop for tasks that require both research and writing.
            # The coordinator self-evaluates after each synthesis and re-delegates
            # targeted queries until coverage is sufficient or iterations are exhausted.
            await run_refinement_coordinator(client, model, user_request)
        else:
            selected_tools = [TOOLS_BY_NAME[name] for name in PIPELINES[pipeline]]
            _log(f">>> Active tools: {[t['name'] for t in selected_tools] or '(none)'}\n")

            partitions = None
            if pipeline == "RESEARCH_ONLY":
                partitions = await generate_partitions(client, model, user_request)
                _log(">>> Research partitions:")
                _log(json.dumps(partitions, indent=2))
                _log("")

            messages = [{"role": "user", "content": user_request}]
            await run_coordinator(client, model, messages, selected_tools, partitions)


if __name__ == "__main__":
    asyncio.run(main())
