#!/usr/bin/env bash
set -e

# Entry point CI runs for this example. `audit` sweeps training runs through the Comet MCP
# server (the bundled synthetic one when no COMET_API_KEY is set), flags under-utilized
# hardware, and — with Opik + LLM credentials — writes an LLM rightsizing report and logs
# the whole pipeline as an Opik trace. With no credentials it falls back to DRY_RUN and
# exits 0 (the secrets-free check). OPIK_PROJECT_NAME is defined in config.py.
uv sync
uv run gpu-capacity-planning audit
