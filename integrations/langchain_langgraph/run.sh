#!/usr/bin/env bash
set -e

# Entry point CI runs for this example. With no Opik credentials it falls back to
# DRY_RUN and exits 0; with credentials set it logs the graph to Opik.
uv sync
export OPIK_PROJECT_NAME="langchain-langgraph"
uv run langchain-langgraph-opik
