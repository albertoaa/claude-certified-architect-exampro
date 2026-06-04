import os
import json
import asyncio
import re
from pathlib import Path

from anthropic import AsyncAnthropic, DefaultAioHttpClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()

ROOT = Path(__file__).parent
AGENTS_DIR = ROOT / ".claude" / "agents"
FIXTURES_DIR = ROOT / "fixtures"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Claude Code subagent names use hyphens; Messages API tool names use underscores.
SPOKE_TOOL_NAMES = {
    "keyword-scanner": "keyword_scanner",
    "deep-evaluator": "deep_evaluator",
    "red-flag-detector": "red_flag_detector",
    "score-aggregator": "score_aggregator",
}
TOOL_TO_SPOKE = {v: k for k, v in SPOKE_TOOL_NAMES.items()}

TOOL_DESCRIPTIONS = {
    "keyword_scanner": (
        "Phase A spoke: fast must-have skills and qualifications check. "
        "Pass job posting, resume, and application text in the task field."
    ),
    "deep_evaluator": (
        "Phase A spoke: assess experience depth, context, and seniority fit. "
        "Pass job posting, resume, and application text in the task field."
    ),
    "red_flag_detector": (
        "Phase A spoke: find disqualifiers and inconsistencies. "
        "Pass job posting, resume, and application text in the task field."
    ),
    "score_aggregator": (
        "Phase B spoke: produce hire/pass/maybe from evaluator JSON only. "
        "Call only after keyword_scanner, deep_evaluator, and red_flag_detector have returned. "
        "Pass their JSON outputs in the task field — not raw resumes."
    ),
}


def load_coordinator_prompt() -> str:
    return (ROOT / "CLAUDE.md").read_text()


def load_spokes() -> dict[str, dict[str, str]]:
    spokes: dict[str, dict[str, str]] = {}
    for path in sorted(AGENTS_DIR.glob("*.md")):
        parts = path.read_text().split("---", 2)
        if len(parts) < 3:
            continue
        frontmatter, body = parts[1], parts[2].strip()
        name_match = re.search(r"^name:\s*(\S+)", frontmatter, re.MULTILINE)
        model_match = re.search(r"^model:\s*(\S+)", frontmatter, re.MULTILINE)
        if not name_match:
            continue
        spoke_name = name_match.group(1)
        tool_name = SPOKE_TOOL_NAMES[spoke_name]
        model = DEFAULT_MODEL
        if model_match and model_match.group(1) == "haiku":
            model = DEFAULT_MODEL
        spokes[tool_name] = {"system": body, "model": model}
    return spokes


def load_fixtures() -> str:
    job = (FIXTURES_DIR / "job_posting.md").read_text()
    resume = (FIXTURES_DIR / "candidate_resume.md").read_text()
    application = (FIXTURES_DIR / "application_answers.md").read_text()
    return (
        "Screen this candidate using the full pipeline (Phase A evaluators, then Phase B aggregator).\n\n"
        f"## Job posting\n{job}\n\n"
        f"## Resume\n{resume}\n\n"
        f"## Application\n{application}"
    )


def build_tools() -> list[dict]:
    return [
        {
            "name": tool_name,
            "description": TOOL_DESCRIPTIONS[tool_name],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Context for this spoke only (materials or evaluator JSON)",
                    }
                },
                "required": ["task"],
            },
        }
        for tool_name in SPOKE_TOOL_NAMES.values()
    ]


async def run_spoke(
    client: AsyncAnthropic,
    spokes: dict[str, dict[str, str]],
    tool_name: str,
    task: str,
) -> str:
    config = spokes[tool_name]
    response = await client.messages.create(
        model=config["model"],
        max_tokens=1024,
        system=config["system"],
        messages=[{"role": "user", "content": task}],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks) if text_blocks else "(no response)"


async def main() -> None:
    coordinator_prompt = load_coordinator_prompt()
    spokes = load_spokes()
    tools = build_tools()
    messages = [{"role": "user", "content": load_fixtures()}]

    missing = [name for name in SPOKE_TOOL_NAMES.values() if name not in spokes]
    if missing:
        raise RuntimeError(f"Missing spoke definitions: {missing}")

    async with AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=DefaultAioHttpClient(),
    ) as client:
        max_iterations = 12
        for iteration in range(max_iterations):
            response = await client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=2048,
                system=coordinator_prompt,
                tools=tools,
                messages=messages,
            )
            print(json.dumps(response.to_dict(), indent=2))

            if response.stop_reason != "tool_use":
                break

            if iteration == max_iterations - 1:
                print("Max iterations reached — stopping loop.")
                break

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            tool_results = []
            for tool_use in tool_uses:
                result = await run_spoke(
                    client, spokes, tool_use.name, tool_use.input["task"]
                )
                tool_results.append(result)
                spoke = TOOL_TO_SPOKE.get(tool_use.name, tool_use.name)
                print(f"\n>>> Spoke called: {spoke} ({tool_use.name})")
                print(f">>> Input: {tool_use.input}")
                print(f">>> Result: {result}\n")

            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    }
                    for tool_use, result in zip(tool_uses, tool_results)
                ],
            })


if __name__ == "__main__":
    asyncio.run(main())
