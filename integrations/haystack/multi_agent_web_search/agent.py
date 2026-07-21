"""
Haystack multi-agent web-search example, traced with Opik.

A coordinator agent delegates research questions to a scout agent, which in turn
calls a SerperDev web-search tool. Opik traces the whole coordinator -> scout ->
tool chain via `OpikConnector`.
"""

import os
from typing import Annotated

os.environ["HAYSTACK_CONTENT_TRACING_ENABLED"] = "true"

from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.tools import tool
from opik.integrations.haystack import OpikConnector

import config
from tool import build_web_search_tool

QUERY = "What was the final score and who won the FIFA World Cup 2026 championship?"


def build_coordinator() -> Agent:
    OpikConnector(name="haystack-multi-agent-scout", project_name=config.OPIK_PROJECT_NAME)

    scout_agent = Agent(
        chat_generator=OpenAIChatGenerator(model=config.OPENAI_MODEL),
        tools=[build_web_search_tool()],
        system_prompt=(
            "You are a football scouting specialist covering the FIFA World Cup 2026. "
            "Search the web to find up-to-date information on teams, fixtures, venues, and knockout news"
        ),
    )

    @tool
    def scout(query: Annotated[str, "The World Cup 2026 research question to investigate"]) -> str:
        """Research a FIFA World Cup 2026 topic and return a summary of findings."""
        try:
            result = scout_agent.run(messages=[ChatMessage.from_user(query)])
            return result["last_message"].text
        except Exception as e:
            return f"Scouting research failed: {e}"

    return Agent(
        chat_generator=OpenAIChatGenerator(model=config.OPENAI_MODEL),
        tools=[scout],
        system_prompt=(
            "You are a World Cup 2026 coverage coordinator. Delegate research questions "
            "about teams, matches, venues, and players to the scout tool, then summarize "
            "the findings for a fan who wants the latest updates."
        ),
    )


def run_agent(query: str) -> str:
    coordinator = build_coordinator()
    result = coordinator.run(messages=[ChatMessage.from_user(query)])
    return result["last_message"].text


def main() -> None:
    if config.DRY_RUN:
        print(
            "[DRY RUN] OpenAI / SerperDev / Opik credentials not set — would delegate this "
            f"query through the coordinator -> scout agent chain and trace it to Opik:\n  {QUERY}"
        )
        return
    print(run_agent(QUERY))

if __name__ == "__main__":
    main()
