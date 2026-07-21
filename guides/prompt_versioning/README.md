# Prompt Versioning

Version prompts in the Opik Prompt Library, compare versions for hallucination before you
ship one, then run inference against whichever version is currently the latest commit
without hardcoding the prompt text into your application.

## What this does

Every call to `client.create_prompt(name=..., prompt=...)` with the same `name` creates a new,
immutable **commit** rather than overwriting the previous one — so you always have a history of
what a prompt used to say, and can fetch any specific version by its commit hash. This guide
walks through the full loop: commit two versions of a prompt, score them against each other with
an LLM-as-judge `Hallucination` metric, then fetch whichever version is newest and run it through
a real OpenAI call.

- **`prompts.py`** — the raw prompt strings, versioned in this guide (a "loose" baseline and a
  stricter, compliance-reviewed rewrite for two use cases: a fintech assistant and an earnings-call
  summarizer).
- **`version.py`** — the Opik logic: commit new prompt versions and fetch a version by commit or by
  "latest".
- **`evaluate.py`** — builds a small Opik dataset and scores both versions of the summarizer prompt
  with the `Hallucination` metric via `evaluate_prompt`, so you can compare them as experiments in
  the Opik UI.
- **`inference.py`** — fetches the latest committed version of the fintech-assistant prompt from
  Opik and runs it through the OpenAI SDK, traced with `@opik.track`.

## Prerequisites

```bash
uv sync    # or: uv pip install "opik>=2.0.74" "openai>=1.0"
```

| Variable | Required for | Description |
|---|---|---|
| `OPIK_API_KEY` | `version.py`, `evaluate.py`, `inference.py` | Your Opik API key. Unset → every script runs in DRY_RUN |
| `OPIK_WORKSPACE` | `version.py`, `evaluate.py`, `inference.py` | Your Opik workspace name |
| `OPIK_PROJECT_NAME` | `version.py`, `evaluate.py`, `inference.py` | Opik project for traces/experiments |
| `OPENAI_API_KEY` | `inference.py`, `evaluate.py` | OpenAI key used to run the fetched prompt |

## Running it

```bash
# Dry-run first — no credentials needed.
uv run python version.py     # prints the prompt versions it would create
uv run python evaluate.py    # prints the versions it would score
uv run python inference.py   # prints the query it would run

# Full run — set credentials, then the same scripts talk to Opik (+ OpenAI for inference.py).
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"
export OPENAI_API_KEY="<your-key>"

uv run python version.py     # commits 2 versions of 'fintech-assistant', prints their commits
uv run python evaluate.py    # commits 2 versions of 'summarizer-fintech', logs 2 experiments
uv run python inference.py   # fetches the latest 'fintech-assistant' commit, runs it via OpenAI
```

Or just run `./run.sh` to do all three in sequence

## How it works

1. **`prompts.py`** holds plain prompt strings — no Opik calls. Two pairs of versions: a loose
   baseline and a stricter rewrite, for a fintech assistant and for an earnings-call summarizer.
2. **`version.py`** wraps `client.create_prompt` (commit a new version) and `client.get_prompt`
   (fetch a version — by `commit`, or the newest one when `commit` is omitted). Running it commits
   both fintech-assistant versions and prints each resulting commit hash.
3. **`evaluate.py`** commits both summarizer versions, builds a one-item Opik dataset from a sample
   earnings-call transcript, and runs `evaluate_prompt` for each version with the `Hallucination`
   metric as the scorer. Each version becomes its own experiment in Opik, so you can compare
   hallucination scores side by side — the stricter version should score lower.
4. **`inference.py`** calls `version.get_latest` to resolve whichever fintech-assistant commit is
   newest, then sends it as the system prompt to the OpenAI SDK. The call is wrapped in
   `@opik.track`, so it shows up as a trace in Opik. Because it always asks for the latest commit,
   promoting a new prompt version in Opik changes what this script runs without any code changes.
