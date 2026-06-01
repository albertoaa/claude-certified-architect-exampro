import os
import asyncio
import random
from anthropic import AsyncAnthropic, DefaultAioHttpClient
from dotenv import load_dotenv

load_dotenv()


def magic_eyeball(question: str) -> str:
    answers = ["Yes", "No", "Maybe", "Ask again later", "Definitely not", "It is certain"]
    return random.choice(answers)


def handle_fortune(question: str) -> str:
    return f"The Magic Eyeball says: {magic_eyeball(question)}"


def handle_general(answer: str) -> str:
    return f"Claude's answer: {answer}"


def handle_unclear() -> str:
    return "Please ask a clearer yes/no fortune-telling question."


async def classify_question(client, model: str, question: str) -> str:
    response = await client.messages.create(
        model=model,
        max_tokens=10,
        system=(
            "Classify the user's question. Reply with exactly one word: "
            "FORTUNE if it is a yes/no fortune-telling question, "
            "GENERAL if it is a factual question, "
            "or UNCLEAR otherwise."
        ),
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text.strip().upper()


async def main() -> None:
    # fortune telling question
    # question = "Will I be a billionaire living on Mars in 2026?"
    # general question
    question = "What is the capital of France?"
    # unclear question
    question = "What is the capital of Mars?"
    model = "claude-haiku-4-5-20251001"

    async with AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        http_client=DefaultAioHttpClient(),
    ) as client:
        classification = await classify_question(client, model, question)
        print(f"Classification: {classification}")

        # Pre-configured decision tree — logic lives here, not in the LLM
        if classification == "FORTUNE":
            result = handle_fortune(question)
        elif classification == "GENERAL":
            response = await client.messages.create(
                model=model,
                max_tokens=256,
                messages=[{"role": "user", "content": question}],
            )
            result = handle_general(response.content[0].text)
        else:
            result = handle_unclear()

        print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
