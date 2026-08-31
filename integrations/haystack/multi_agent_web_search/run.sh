#!/usr/bin/env bash
set -e

export OPIK_PROJECT_NAME="haystack-multi-agent-scout"

uv sync

# With no OpenAI / SerperDev / Opik credentials this falls back to DRY_RUN and
uv run python agent.py
