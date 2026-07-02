#!/usr/bin/env bash
set -e

# Entry point CI runs for this example. With no Opik/provider credentials it falls
# back to DRY_RUN and exits 0; with credentials set it logs a trace to Opik.
uv sync
export OPIK_PROJECT_NAME="pydantic-ai"
uv run pydantic-ai-opik
