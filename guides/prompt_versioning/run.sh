#!/usr/bin/env bash
set -e

# Entry point CI runs for this example. With no Opik/OpenAI credentials each script falls
# back to DRY_RUN and exits 0 (the secrets-free check); with credentials set it runs live —
# versioning prompts in Opik, evaluating versions for hallucination, then running inference
# against the latest committed version via the OpenAI SDK.
uv sync
uv run python version.py
uv run python inference.py
uv run python evaluate.py
