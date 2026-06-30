#!/usr/bin/env bash
set -e

# Entry point CI runs for this example. `eval` exercises the full Opik loop
# (dataset + test suite + evaluation). With no Opik credentials it falls back to
# DRY_RUN and exits 0 (the secrets-free check); with credentials set it runs live
# and logs traces to Opik. OPIK_PROJECT_NAME is defined in config.py.
uv sync
uv run example-use-case eval
