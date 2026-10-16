#!/usr/bin/env bash
set -e

# CI entrypoint. Without Opik credentials the script uses sample data and still writes a PNG.
uv sync
export OPIK_PROJECT_NAME="${OPIK_PROJECT_NAME:-visualize-thread-feedback-scores}"
uv run visualize-thread-feedback-scores --output thread_feedback_scores.png
