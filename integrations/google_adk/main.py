"""
Before running this script, export your Opik credentials:

    export OPIK_API_KEY="<your-opik-api-key>"
    export OPIK_WORKSPACE="<your-opik-workspace>"
    export OPIK_PROJECT_NAME="<your-opik-project-name>"

You can create an Opik API key from https://www.comet.com/opik.
"""

import asyncio

from opik.integrations.adk import OpikTracer, track_adk_agent_recursive
from google.adk.agents import LlmAgent

from constant import DESCRIPTION, INSTRUCTION
from tools import retrieve_docs, web_search

MODEL_NAME = "gemini-2.5-flash-lite"
APP_NAME = "multi-agent"
USER_ID = "tranfer_01"
SESSION_ID = "session_01"

def build_agent():    
    agent = LlmAgent(
        name="agent",
        model=MODEL_NAME,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        tools=[retrieve_docs, web_search],
    )

    opik_tracer = OpikTracer(name="router-agent")
    track_adk_agent_recursive(agent, opik_tracer)
    return agent

async def create_session(session_service) -> None:
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

def run_agent(query: str) -> str:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    agent = build_agent()
    session_service = InMemorySessionService()
    asyncio.run(create_session(session_service))
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    content = types.Content(role="user", parts=[types.Part(text=query)])
    events = runner.run(user_id=USER_ID, session_id=SESSION_ID, new_message=content)

    for event in events:
        if event.is_final_response() and event.content:
            return event.content.parts[0].text.strip()
    return ""

def main() -> None:
    query = "projected reach of the digital remittance market by 2034"
    response = run_agent(query)
    print(response)

if __name__ == "__main__":
    main()
