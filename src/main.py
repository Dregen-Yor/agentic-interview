from agents import Agent, Runner
from Agents.agents import inter_view_agent
import asyncio
 

async def main():
    result=await Runner.run(inter_view_agent,input="Who are you?")
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
