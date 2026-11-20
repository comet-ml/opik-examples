#!/usr/bin/env bash
set -e

# Entry point CI runs for this example. With no Opik credentials it checks every evals.yaml and exits 0
# (the secrets-free check); with credentials it runs every skill's test suite and exits 1 if a test fails.
# OPIK_PROJECT_NAME is defined in run_skill_evals.py.
uv sync
uv run skill-evals
