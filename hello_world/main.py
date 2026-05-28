import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from claude_agent_sdk import query, ClaudeAgentOptions
from agent_output_parser import print_message

async def main():
    print('running fix agent')
    async for message in query(
        prompt="Find and fix the bug in hello_world.rb",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash"]),
    ):
        print_message(message)

if __name__ == '__main__':
    asyncio.run(main())
