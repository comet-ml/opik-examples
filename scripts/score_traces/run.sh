#!/usr/bin/env bash
set -e

# CI entry point. With no Opik credentials the runner exits 0 without network
# access (the secrets-free check). With credentials + a seeded project it runs live.
#
# Set the target project/workspace here, or (better) as pipeline env vars.
# NEVER hard-code OPIK_API_KEY / gateway keys — inject them from your CI secret store,
# ideally a dedicated Opik service account.
# export OPIK_WORKSPACE="your-workspace"
# export OPIK_PROJECT_NAME="score-traces-example"

uv sync
uv run python score_traces.py
