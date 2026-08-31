# Haystack Multi-Agent Web Search with Comet Opik

Trace a Haystack multi-agent pipeline with Comet Opik.

## What this does

This example runs a two-agent Haystack chain: a coordinator agent that delegates research
questions to a scout agent, which searches the web via SerperDev to answer them. `OpikConnector`
traces the coordinator, the scout, and every tool call into a single Opik trace.

## Prerequisites

This is a `uv` project — dependencies live in `pyproject.toml`.

```bash
uv sync
```

Copy `.env.example` to `.env` (or `export` the variables). With `OPENAI_API_KEY` /
`SERPERDEV_API_KEY` / Opik credentials unset, the example runs in **DRY_RUN** and prints what it
would do instead of calling OpenAI/SerperDev/Opik.

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | for a live run | OpenAI API key used by both agents' chat generators. Unset → DRY_RUN. |
| `SERPERDEV_API_KEY` | for a live run | SerperDev API key for the web-search tool. Unset → DRY_RUN. |
| `OPIK_API_KEY` | for a live run | Opik API key from [comet.com/opik](https://www.comet.com/opik). Unset → DRY_RUN. |
| `OPIK_WORKSPACE` | for a live run | Your Opik workspace. Unset → DRY_RUN. |
| `OPIK_PROJECT_NAME` | no | Project traces are logged to (default `haystack-multi-agent-scout`). |
| `HAYSTACK_OPENAI_MODEL` | no | OpenAI model both agents run on (default `gpt-5-mini`). |

## Running it

```bash
uv run python agent.py

# or, the way CI does:
bash run.sh
```

## How it works

1. **Define the tool** — `tool.py` wraps `SerperDevWebSearch` as a `ComponentTool` named `web_search`.
2. **Enable tracing** — `agent.py` sets `HAYSTACK_CONTENT_TRACING_ENABLED=true` and constructs
   `OpikConnector`, which activates Opik tracing for every Haystack component run in the process.
3. **Build the agents** — `agent.py` creates a `scout` agent that calls `web_search`, wraps it as a
   `scout` tool, and gives that tool to a `coordinator` agent.
4. **Run and trace** — `run_agent` sends a query to the coordinator, which delegates to the scout as
   needed; the full call chain is logged to Opik under `OPIK_PROJECT_NAME`.
