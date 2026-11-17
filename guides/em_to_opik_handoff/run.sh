#!/usr/bin/env bash
set -e

# WHY: the full pipeline needs a 10 GB dataset, a GPU hour and a Comet key, none of which CI
# has. CI checks the pure logic and the credentials-free dry run; it never logs a trace, so
# the showcase project in the opik-examples workspace stays as the README describes it.
uv sync --group dev
uv run pytest -q
uv run python scripts/00_dry_run.py
