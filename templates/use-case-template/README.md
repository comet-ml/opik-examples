# [Example title]

<!-- One sentence: what problem does this demo solve and how? -->

A runnable skeleton for an Opik use-case demo: a traced app wired through the full Opik
evaluation-and-improvement loop (dataset + test suite → `evaluate`/`run_tests` → Optimization
Studio → Prompt Library), driven by a Typer CLI. Copy it with the `scaffold-example` skill,
then fill in the parts marked `TODO`.

## What this does

<!-- 1–3 sentences. Replace with what your demo demonstrates and why it's useful. -->

Runs an LLM task over a small set of cases (`data/cases.json`) and demonstrates the Opik
lifecycle as CLI commands:

- **`run`** — run the app on one input (traced in Opik).
- **`eval`** — create an Opik **dataset** and a **test suite** (plain-English assertions), then
  run both: `run_tests` for the assertions and `evaluate` with the `AnswerRelevance` and
  `Hallucination` metrics.
- **`optimize`** — run **Optimization Studio** (`opik-optimizer`) to improve the prompt against
  the dataset.
- **`promote`** — save the optimised prompt to the Opik **Prompt Library** (re-running versions it).
- **`run-all`** — chain eval → optimize → promote.

## Prerequisites

```bash
pip install opik opik-optimizer litellm typer
```

Or, with `uv` (recommended — this folder is a `uv` project): `uv sync`.

| Environment variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | for `run`/`eval`/`optimize`/`promote` | Anthropic key; used via litellm for generation, judge metrics, and the optimizer |
| `OPIK_API_KEY` | for `eval`/`optimize`/`promote` | Your Opik API key. Unset → those commands run in DRY_RUN |
| `OPIK_WORKSPACE` | for `eval`/`optimize`/`promote` | Your Opik workspace name |
| `OPIK_PROJECT_NAME` | No | Opik project for traces/experiments (default `example-use-case`) |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted Opik (default: Opik Cloud) |

## Running it

```bash
# Dry-run first — no credentials needed.
uv run example-use-case eval        # prints the dataset items + assertions it would create
uv run example-use-case optimize    # prints what it would optimise

# Full run — set credentials, then the same commands talk to Claude + Opik.
export ANTHROPIC_API_KEY="<your-key>"
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"

uv run example-use-case eval        # dataset + test suite created; pass rate + experiment URL printed
uv run example-use-case optimize    # initial -> optimised score printed
uv run example-use-case promote     # optimised prompt saved to the Prompt Library (versioned)
uv run example-use-case run-all     # the whole loop in one shot
```

## How it works

<!-- Replace specifics as you flesh out the demo. -->

1. **App** (`app.py`) — `run()` is decorated with `@opik.track`, so each call appears as a trace
   in Opik. Replace its body with your real logic (retrieval, tool use, chains).
2. **Eval** (`evaluation.py`) — builds an Opik dataset and a test suite, then scores the live
   task: `run_tests` checks the plain-English **assertions**; `evaluate` runs the
   `AnswerRelevance` and `Hallucination` metrics. Cases live in `data/cases.json`.
3. **Optimize** (`optimization.py`) — `MetaPromptOptimizer.optimize_prompt(...)` improves the
   `ChatPrompt` against the dataset, scored by a callable that wraps an Opik judge.
4. **Promote** (`prompts.py`) — `client.create_chat_prompt(...)` saves the optimised messages to
   the Prompt Library; re-running with the same name creates a new version.
