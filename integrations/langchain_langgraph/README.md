# LangChain + LangGraph + Opik

Trace LangChain runnables inside a LangGraph workflow with Opik.

## What this does

This example builds a small support-router workflow with [LangGraph](https://langchain-ai.github.io/langgraph/)
and [LangChain](https://python.langchain.com/) runnables. The graph classifies a support question,
routes it to a branch, and generates a deterministic response. When Opik credentials are set, the
workflow is wrapped with `track_langgraph()` and traced with `OpikTracer`.

## Prerequisites

This is a `uv` project - dependencies live in `pyproject.toml`.

```bash
uv sync
```

Or, with `pip`:

```bash
pip install opik langchain-core langgraph
```

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | for a live run | Opik API key from [comet.com/opik](https://www.comet.com/opik). Unset -> DRY_RUN. |
| `OPIK_WORKSPACE` | for a live run | Your Opik workspace. Unset -> DRY_RUN. |
| `OPIK_PROJECT_NAME` | no | Project traces are logged to (default `langchain-langgraph`). |
| `OPIK_URL_OVERRIDE` | no | Base URL for self-hosted Opik (default: Opik Cloud). |

## Running it

```bash
# Dry-run first - no credentials needed.
uv run langchain-langgraph-opik --dry-run

# Full run - set credentials, then the same command logs the graph to Opik.
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"

uv run langchain-langgraph-opik

# or run it the way CI does:
bash run.sh
```

## How it works

1. **LangChain runnables** - `RunnableLambda` wraps the classification and response functions so
   each unit is visible as a LangChain step.
2. **LangGraph routing** - `StateGraph` routes the question to greeting, billing, technical, or
   general response nodes based on the classification.
3. **Opik tracing** - `OpikTracer` records the graph execution and `track_langgraph()` attaches
   graph structure and node spans to the trace.
4. **Dry-run fallback** - missing Opik credentials switch the script into DRY_RUN, which prints the
   same classification and response locally without sending data.
