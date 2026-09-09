import json

import litellm
import opik
from mcp import ClientSession

from . import config, prompts
from .mcp_client import call_tool, openai_tool_defs
from .recommender import _opik_metadata, _wire_llm_span_logging


@opik.track(name="capacity_agent", project_name=config.OPIK_PROJECT_NAME)
async def ask(session: ClientSession, question: str, workspace: str, max_turns: int = 8) -> str:
    """Bounded tool-use loop: the LLM drives the comet-mcp tools to answer a free-form question."""
    _wire_llm_span_logging()
    tools = await openai_tool_defs(session)
    # WHY: without this the model guesses the workspace and audits the API key's default one.
    scope = (
        f"\nAudit the Comet workspace '{workspace}': pass it as the workspace argument "
        "to every tool that accepts one."
    )
    messages: list[dict] = [
        {"role": "system", "content": prompts.AGENT_SYSTEM_PROMPT + scope},
        {"role": "user", "content": question},
    ]

    for _ in range(max_turns):
        response = await litellm.acompletion(
            model=config.GEN_MODEL,
            messages=messages,
            tools=tools,
            metadata=_opik_metadata(),
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            return message.content or ""

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [tc.model_dump() for tc in tool_calls],
            }
        )
        for tc in tool_calls:
            arguments = json.loads(tc.function.arguments or "{}")
            try:
                result = await call_tool(session, tc.function.name, arguments)
            except RuntimeError as exc:
                result = {"error": str(exc)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)[:20000],
                }
            )

    return "Reached the tool-call turn limit before finishing; narrow the question or raise --max-turns."
