# [Script title]

<!-- One sentence: what problem does this script solve and how? -->

A runnable skeleton for a standalone Opik utility script: a single `.py` file with an argparse
CLI, env-var credentials, and a DRY_RUN fallback. Copy it with the `scaffold-example` skill
(`--template script-template --bucket scripts`), then fill in the parts marked `TODO`.

## What this does

<!-- 1–3 sentences. Replace with what your script does and why it's useful. -->

Runs a single Opik task from the command line. It loads credentials from the environment and,
when they are missing, prints what it *would* do instead of touching anything (DRY_RUN).

## Prerequisites

```bash
pip install opik
```

Or, with `uv` (recommended — this folder is a `uv` project): `uv sync`.

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | for a real run | Your Opik API key. Unset → the script runs in DRY_RUN |
| `OPIK_WORKSPACE` | for a real run | Your Opik workspace name |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted Opik (default: Opik Cloud) |

## Running it

```bash
# Dry-run first — no credentials needed.
uv run example-script --dry-run        # prints what it would do

# Full run — set credentials, then the same command talks to Opik.
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"

uv run example-script                   # does the work
uv run example-script --limit 50        # sample option — replace with real flags
```

## How it works

<!-- Replace specifics as you flesh out the script. -->

1. **Config** — credentials come from `OPIK_API_KEY`, `OPIK_WORKSPACE`, and the optional
   `OPIK_URL_OVERRIDE`; `DRY_RUN` is on whenever the key/workspace pair is absent.
2. **CLI** — `build_parser()` defines the flags; `--dry-run` forces DRY_RUN even with credentials.
3. **Work** — `run()` holds the real logic. In DRY_RUN it prints its plan; otherwise it uses a
   live `opik.Opik()` client. Replace its body with the actual task.
