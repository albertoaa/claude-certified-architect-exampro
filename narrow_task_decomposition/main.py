import os
import json
import asyncio
from anthropic import AsyncAnthropic, DefaultAioHttpClient
from dotenv import load_dotenv

load_dotenv()

# The coordinator decomposes work and delegates to specialists via tools.
# Specialists run in isolated context — they do not see the coordinator's history.
SYSTEM_PROMPT = """You are a coordinator assistant.
Before delegating, plan the full sequence of subtasks and identify which can run in parallel.
Use research_specialist for factual research. You may call it multiple times for independent subtopics.
Use writer_specialist for drafting or polishing text.
When a specialist's output is needed by another, include it verbatim in the next specialist's task field.
Synthesize specialist results into a final answer for the user.
"""

TOOLS = [
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

SPECIALIST_PROMPTS = {
    "research_specialist": "You are a research specialist. Answer with concise factual points only.",
    "writer_specialist": "You are a writing specialist. Produce clear, polished prose.",
}


async def run_specialist(
    client: AsyncAnthropic,
    model: str,
    name: str,
    task: str,
) -> str:
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=SPECIALIST_PROMPTS[name],
        messages=[{"role": "user", "content": task}],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks) if text_blocks else "(no response)"


async def main() -> None:
    model = "claude-haiku-4-5-20251001"
    messages = [{
        "role": "user",
        "content": (
            "Research three benefits of morning exercise, "
            "then write a short motivational paragraph using those points."
        ),
    }]

    async with AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=DefaultAioHttpClient(),
    ) as client:
        while True:
            response = await client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            print(json.dumps(response.to_dict(), indent=2))

            if response.stop_reason != "tool_use":
                break

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            tool_results = []
            for tool_use in tool_uses:
                result = await run_specialist(
                    client, model, tool_use.name, tool_use.input["task"]
                )
                tool_results.append(result)
                print(f"\n>>> Specialist called: {tool_use.name}({tool_use.input})")
                print(f">>> Specialist result: {result}\n")

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
