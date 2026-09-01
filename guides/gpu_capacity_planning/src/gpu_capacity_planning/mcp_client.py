import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import opik
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import config


def server_params(synthetic: bool) -> StdioServerParameters:
    """Spawn the bundled synthetic server, or the real Comet EM MCP server via uvx."""
    if synthetic:
        return StdioServerParameters(
            command=sys.executable,
            args=["-m", "gpu_capacity_planning.synthetic_server"],
        )
    env = {**os.environ, "COMET_API_KEY": config.COMET_API_KEY or ""}
    if config.COMET_WORKSPACE:
        env["COMET_WORKSPACE"] = config.COMET_WORKSPACE
    if config.COMET_URL_OVERRIDE:
        env["COMET_URL_OVERRIDE"] = config.COMET_URL_OVERRIDE
    return StdioServerParameters(command="uvx", args=["comet-mcp"], env=env)


@asynccontextmanager
async def comet_session(synthetic: bool) -> AsyncIterator[ClientSession]:
    async with stdio_client(server_params(synthetic)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@opik.track(type="tool", project_name=config.OPIK_PROJECT_NAME)
async def call_tool(session: ClientSession, tool: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call one MCP tool and JSON-decode its text content. Every call becomes an Opik tool span."""
    result = await session.call_tool(tool, arguments or {})
    if result.is_error:
        raise RuntimeError(f"MCP tool '{tool}' failed: {result.content}")
    if result.structured_content is not None:
        # WHY: servers with output schemas return the payload here; text content is a fallback.
        return result.structured_content
    payload = "\n".join(c.text for c in result.content if getattr(c, "type", None) == "text")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload


async def openai_tool_defs(session: ClientSession) -> list[dict[str, Any]]:
    """Convert the server's MCP tool schemas to OpenAI-format tool definitions for litellm."""
    tools = await session.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema,
            },
        }
        for t in tools.tools
    ]
