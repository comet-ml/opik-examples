# [Example title]

<!-- One sentence: what problem does this solve and how? -->

## What this does

<!-- 1–3 sentences. What the example demonstrates and why it's useful. -->

## Prerequisites

```bash
pip install opik opentelemetry-sdk  # replace with actual dependencies
```

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | Yes | Your Opik API key |
| `OPIK_WORKSPACE` | Yes | Your Opik workspace name |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted Opik (default: Opik Cloud) |

## Running it

```bash
# Dry-run (no credentials needed — prints output locally)
python example.py

# Send to Opik
export OPIK_API_KEY="<your-api-key>"
export OPIK_WORKSPACE="<your-workspace>"
python example.py
```

## How it works

<!-- Brief walkthrough of the key steps. Reference line numbers or function names where helpful. -->

1. **Step one** — what happens first
2. **Step two** — what the key part does and why
3. **Step three** — what the output looks like
