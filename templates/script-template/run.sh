#!/usr/bin/env bash
set -e

# Entry point CI runs for this example. With no Opik credentials it falls back to
# DRY_RUN and exits 0 (the secrets-free check); with credentials set it runs live
# and logs traces to Opik.
uv sync
export OPIK_PROJECT_NAME="example-script"
uv run example-script
