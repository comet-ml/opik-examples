#!/usr/bin/env bash
set -e

export OPIK_PROJECT_NAME="otel-offline-eval"

pip install -r requirements.txt

# Run the LLM app standalone — OTel spans may fail to export if the endpoint
# is unreachable, but Python/import errors will surface here.
python llm_app.py
