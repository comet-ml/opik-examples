#!/usr/bin/env bash
set -e

export OPIK_PROJECT_NAME="f1-radio-rag"

uv sync

uv run f1rag ingest
uv run f1rag ask "Why did Verstappen pit early?"
