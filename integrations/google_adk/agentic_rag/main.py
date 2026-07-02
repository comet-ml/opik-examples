"""
Google ADK Agentic RAG router, traced with Opik.

Run end-to-end:
    export GOOGLE_API_KEY="<your-google-api-key>"
    export OPIK_API_KEY="<your-opik-api-key>"
    export OPIK_WORKSPACE="<your-opik-workspace>"
    python index.py && python main.py

With GOOGLE_API_KEY / Opik credentials unset, this prints a DRY_RUN line and exits 0.
You can create an Opik API key from https://www.comet.com/opik.
"""

import asyncio
import os

MODEL_NAME = os.environ.get("GADK_MODEL", "gemini-2.5-flash")
APP_NAME = "agentic-rag"
USER_ID = "user"
SESSION_ID = "session_01"
QUERY = "projected reach of the digital remittance market by 2034"

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "google-adk-rag")

# No Google/Opik credentials -> print what would run instead of calling Gemini + Opik.
DRY_RUN = not (GOOGLE_API_KEY and OPIK_API_KEY and OPIK_WORKSPACE)


def build_agent():
    from google.adk.agents import LlmAgent
    from opik.integrations.adk import OpikTracer, track_adk_agent_recursive

    from constant import DESCRIPTION, INSTRUCTION
    from tools import retrieve_docs, web_search

    agent = LlmAgent(
        name="router_agent",
        model=MODEL_NAME,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        tools=[retrieve_docs, web_search],
    )
    opik_tracer = OpikTracer(name="router-agent", project_name=OPIK_PROJECT_NAME)
    track_adk_agent_recursive(agent, opik_tracer)
    return agent


async def _create_session(session_service) -> None:
    await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)


def run_agent(query: str) -> str:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    agent = build_agent()
    session_service = InMemorySessionService()
    asyncio.run(_create_session(session_service))
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    content = types.Content(role="user", parts=[types.Part(text=query)])
    events = runner.run(user_id=USER_ID, session_id=SESSION_ID, new_message=content)
    for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            return (event.content.parts[0].text or "").strip()
    return ""


def main() -> None:
    if DRY_RUN:
        print(
            "[DRY RUN] GOOGLE_API_KEY / Opik credentials not set — would route this query "
            f"through the ADK router (retrieve_docs / web_search) and trace it to Opik:\n  {QUERY}"
        )
        return
    print(run_agent(QUERY))


if __name__ == "__main__":
    main()
