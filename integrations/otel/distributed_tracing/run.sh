#!/usr/bin/env bash
set -e

export OPIK_PROJECT_NAME="otel-distributed-tracing"

uv sync

# Both scripts support DRY_RUN mode when credentials are absent,
# and send real traces to Opik when OPIK_API_KEY + OPIK_WORKSPACE are set.
uv run python option_a_explicit_ids.py
uv run python option_b_w3c_propagation.py
