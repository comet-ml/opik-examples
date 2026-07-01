#!/usr/bin/env bash
set -e

# CI entry point. With no Opik credentials this falls back to DRY_RUN and exits 0
# (the secrets-free check), printing the SDK + curl for each rule type. With
# OPIK_API_KEY + OPIK_WORKSPACE set it creates the rules live.
uv sync
export OPIK_PROJECT_NAME="${OPIK_PROJECT_NAME:-online-eval-rules-example}"

for cmd in create-llm-judge create-python create-thread create-span; do
  echo "=== ${cmd} ==="
  uv run create-online-eval-rules "${cmd}" --name "example-${cmd}"
done
