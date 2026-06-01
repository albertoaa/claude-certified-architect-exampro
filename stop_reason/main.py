import os
import json
import asyncio
import random
from anthropic import AsyncAnthropic, DefaultAioHttpClient
from dotenv import load_dotenv

load_dotenv()

def magic_eyeball(question: str) -> str:
    answers = ["Yes", "No", "Maybe", "Ask again later", "Definitely not", "It is certain"]
    return random.choice(answers)

async def claude_create(client, model, tools, messages):
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        tools=tools,
        messages=messages,
    )
    print(json.dumps(response.to_dict(), indent=2))
    return response

async def main() -> None:
    tools = [
        {
            "name": "magic_eyeball",
            "description": "When the user asks a yes or no fortune telling question, you can use this tool to answer the question.",
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

    model = "claude-haiku-4-5-20251001"
    messages = [{"role": "user", "content": "Hey Claude, will I be a billionaire living in Mars in 2026?"}]

    async with AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=DefaultAioHttpClient(),
    ) as client:
        response = await claude_create(client, model, tools, messages)
        print('original:')
        print(json.dumps(response.to_dict(), indent=2))
        while response.stop_reason == "tool_use":
            tool_use = next(block for block in response.content if block.type == "tool_use")
            tool_result = magic_eyeball(**tool_use.input)

            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": tool_result}]
            })

            response = await claude_create(client, model, tools, messages)
            print('after tool use:')
            print(json.dumps(response.to_dict(), indent=2))



if __name__ == "__main__":
    asyncio.run(main())
