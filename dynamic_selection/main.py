import os
import json
import asyncio
from anthropic import AsyncAnthropic, DefaultAioHttpClient
from dotenv import load_dotenv

load_dotenv()

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
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=SPECIALIST_PROMPTS[name],
        messages=[{"role": "user", "content": task}],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks) if text_blocks else "(no response)"


async def run_coordinator(
    client: AsyncAnthropic,
    model: str,
    messages: list,
    selected_tools: list,
) -> None:
    """Coordinator loop restricted to the pre-selected tool set."""
    while True:
        create_kwargs = dict(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        if selected_tools:
            create_kwargs["tools"] = selected_tools

        response = await client.messages.create(**create_kwargs)
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


async def main() -> None:
    model = "claude-haiku-4-5-20251001"

    # Try different request types to see dynamic selection in action:
    # user_request = "What is the capital of France?"                               # → DIRECT
    # user_request = "What are the three main causes of the French Revolution?"     # → RESEARCH_ONLY
    # user_request = "Rewrite this to sound more professional: 'i did the thing'"  # → WRITING_ONLY
    user_request = (
        "Research three benefits of morning exercise, "
        "then write a short motivational paragraph using those points."
    )  # → RESEARCH_AND_WRITE

    async with AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=DefaultAioHttpClient(),
    ) as client:
        # Classify the request upfront to select the minimal tool set
        pipeline = await classify_request(client, model, user_request)
        selected_tools = [TOOLS_BY_NAME[name] for name in PIPELINES[pipeline]]

        print(f">>> Pipeline selected: {pipeline}")
        print(f">>> Active tools: {[t['name'] for t in selected_tools] or '(none)'}\n")

        messages = [{"role": "user", "content": user_request}]
        await run_coordinator(client, model, messages, selected_tools)


if __name__ == "__main__":
    asyncio.run(main())
