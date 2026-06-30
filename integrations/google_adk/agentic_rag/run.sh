#!/usr/bin/env bash
set -e

export OPIK_PROJECT_NAME="google-adk-rag"

uv sync

# index.py builds the local Qdrant DB; main.py runs the traced router. With no
# GOOGLE_API_KEY / Opik credentials both fall back to DRY_RUN and exit 0 (the
# secrets-free CI check). With credentials set, this indexes the PDF and logs a trace.
uv run python index.py
uv run python main.py
