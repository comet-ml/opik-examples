# Google ADK Agentic RAG with Comet Opik

Trace a Google ADK router agent with Comet Opik.

## What this does

This example runs a Google ADK router agent that decides whether each query should use local RAG over the IMF Financial Access Survey PDF or live web search. It indexes the PDF into a local Qdrant database, exposes `retrieve_docs` and `web_search` tools, and traces the routing decision and tool calls with Opik.

## Prerequisites

```bash
pip install google-adk opik pypdfium2 fastembed qdrant-client ddgs tqdm
```

The same dependencies are also listed in `requirements.txt`.

Create a `.env` file with:

```bash
GOOGLE_API_KEY="<your-google-api-key>"
OPIK_API_KEY="<your-opik-api-key>"
OPIK_WORKSPACE="<your-opik-workspace>"
OPIK_PROJECT_NAME="<your-project-name>"
```

## Running it

Index the IMF PDF or sample PDF into the local Qdrant database:

```bash
python index.py
```

Run the Google ADK router agent and send traces to Opik:

```bash
python main.py
```

![Opik dashboard trace view](assets/dashboard.png)

## How it works

1. **Index the PDF** — `index.py` downloads the IMF report, chunks it, embeds it, and writes vectors into the local `db` directory.
2. **Expose tools** — `tools.py` defines `retrieve_docs` for Qdrant search and `web_search` for DuckDuckGo search.
3. **Run the router** — `main.py` creates the notebook-style `router_agent`, traces it with `OpikTracer`, and runs one query through ADK.
