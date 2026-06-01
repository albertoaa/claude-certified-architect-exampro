import os
import json
import asyncio
import random
from anthropic import AsyncAnthropic, DefaultAioHttpClient
from dotenv import load_dotenv

load_dotenv()

# The system prompt is where routing logic used to live before tool use.
# With model-driven decisions, Claude reads the tool descriptions and decides
# on its own — the system prompt no longer needs to encode the decision tree.
SYSTEM_PROMPT = """You are a fortune teller assistant.
Use the magic_eyeball tool when the user asks a yes/no question about their future.
For all other questions, respond normally without using any tools.
"""

TOOLS = [
    {
        "name": "magic_eyeball",
        "description": "Consults the Magic Eyeball to answer a yes/no fortune-telling question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The yes or no question to answer"
                }
            },
            "required": ["question"]
        }
    }
]


def magic_eyeball(question: str) -> str:
    answers = ["Yes", "No", "Maybe", "Ask again later", "Definitely not", "It is certain"]
    return random.choice(answers)


async def main() -> None:
    model = "claude-haiku-4-5-20251001"
    messages = [{"role": "user", "content": "Hey Claude, will I be a billionaire living on Mars in 2026?"}]

    async with AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=DefaultAioHttpClient(),
    ) as client:
        # Claude decides whether and when to call tools — no hardcoded routing here
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

            # Model chose to call a tool — execute it and feed the result back
            tool_use = next(block for block in response.content if block.type == "tool_use")
            tool_result = magic_eyeball(**tool_use.input)
            print(f"\n>>> Tool called: {tool_use.name}({tool_use.input})")
            print(f">>> Tool result: {tool_result}\n")

            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": tool_result}]
            })


if __name__ == "__main__":
    asyncio.run(main())
