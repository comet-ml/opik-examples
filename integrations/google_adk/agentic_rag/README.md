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

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | for a live run | Gemini API key (Google AI Studio). Unset → DRY_RUN. |
| `OPIK_API_KEY` | for a live run | Opik API key from [comet.com/opik](https://www.comet.com/opik). Unset → DRY_RUN. |
| `OPIK_WORKSPACE` | for a live run | Your Opik workspace. Unset → DRY_RUN. |
| `OPIK_PROJECT_NAME` | no | Project traces are logged to (default `google-adk-rag`). |
| `GADK_MODEL` | no | Gemini model the router runs on (default `gemini-2.5-flash`). |

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
3. **Run the router** — `main.py` creates the `router_agent`, traces it with `OpikTracer` (logging to `OPIK_PROJECT_NAME`, default `google-adk-rag`), and runs one query through ADK.
