# Google ADK Agentic RAG with Comet Opik

Trace a Google ADK router agent with Comet Opik.

## What this does

This example runs a Google ADK router agent that decides whether each query should use local RAG over the IMF Financial Access Survey PDF or live web search. It indexes the PDF into a local Qdrant database, exposes `retrieve_docs` and `web_search` tools, and traces the routing decision and tool calls with Opik.

## Prerequisites

This is a `uv` project — dependencies live in `pyproject.toml`.

```bash
uv sync
```

Copy `.env.example` to `.env` (or `export` the variables). With `GOOGLE_API_KEY` / Opik credentials unset, the example runs in **DRY_RUN** and prints what it would do instead of calling Gemini/Opik.

```bash
GOOGLE_API_KEY="<your-google-api-key>"
OPIK_API_KEY="<your-opik-api-key>"
OPIK_WORKSPACE="<your-opik-workspace>"
OPIK_PROJECT_NAME="google-adk-rag"
```

## Running it

```bash
uv run python index.py   # build the local Qdrant index from the IMF PDF
uv run python main.py    # run the traced ADK router

# or both, the way CI does:
bash run.sh
```

## How it works

1. **Index the PDF** — `index.py` downloads the IMF report, chunks it, embeds it, and writes vectors into the local `db` directory.
2. **Expose tools** — `tools.py` defines `retrieve_docs` for Qdrant search and `web_search` for DuckDuckGo search.
3. **Run the router** — `main.py` creates the notebook-style `router_agent`, traces it with `OpikTracer`, and runs one query through ADK.
