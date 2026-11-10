#!/usr/bin/env bash
set -e

# WHY: with credentials (live-run CI job) exercise the Opik path; without them (dry-run) fall back
# to the offline demo. Extra args go to `run_eval.py run` (the selftest passes --mark-baseline on
# main and no gate flag on PRs; pr-test passes none, so a hold does not fail it).
# The command matches github/opik-eval.yml; a unit test keeps the flag sets aligned.
export OPIK_PROJECT_NAME="${OPIK_PROJECT_NAME:-eval-in-ci-smoke}"

# WHY: the selftest passes "$MODE_FLAG" first, which is empty on PRs; argparse would reject "".
if [ "$#" -gt 0 ] && [ -z "$1" ]; then
  shift
fi

uv sync --group dev
if [ -n "$OPIK_API_KEY" ] && [ -n "$OPIK_WORKSPACE" ]; then
  uv run python run_eval.py run --dataset scenario-planner --task planner:make_eval_task \
    --metric scenarios:build_metric --prompt-file prompts/system.txt \
    --setup setup_opik:run_setup --suite-task planner:make_suite_task \
    --suite-name scenario-planner-guardrails --traffic planner:simulate_traffic_hook \
    "$@"
else
  uv run python run_eval.py demo
fi
