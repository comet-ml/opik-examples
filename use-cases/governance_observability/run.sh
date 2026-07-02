#!/usr/bin/env bash
set -e

export OPIK_PROJECT_NAME="governance-observability"

uv sync

echo "--- Step 1: agent tracing ---"
uv run python agent_tracing.py

echo "--- Step 2: use case team ---"
uv run python use_case_team.py

echo "--- Step 3: data governance team ---"
uv run python data_governance_team.py
