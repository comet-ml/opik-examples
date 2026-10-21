#!/usr/bin/env bash
set -e

# WHY: CI runs this with no secrets (dry-run) and again with secrets (live-run); the demo
# mode needs neither, so both jobs exercise the same path. Live runs use `run_eval.py run`.
export OPIK_PROJECT_NAME="eval-in-ci-example"

uv sync --group dev
uv run python run_eval.py demo
