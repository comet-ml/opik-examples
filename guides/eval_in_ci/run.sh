#!/usr/bin/env bash
set -e

# WHY: with credentials (live-run CI job) exercise the Opik path; without them (dry-run) fall back
# to the offline demo. Extra args go to `run_eval.py run` (the selftest workflow passes
# --mark-baseline or --fail-on-regression); pr-test passes none, so a hold does not fail it.
export OPIK_PROJECT_NAME="eval-in-ci-example"

uv sync --group dev
if [ -n "$OPIK_API_KEY" ] && [ -n "$OPIK_WORKSPACE" ]; then
  uv run python example_task.py
  uv run python run_eval.py run --dataset eval-in-ci-example --task example_task:scenario_agent "$@"
else
  uv run python run_eval.py demo
fi
