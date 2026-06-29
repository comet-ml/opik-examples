# F1 Radio RAG — the full Opik loop

A small, runnable demo that walks the **entire Opik evaluation-and-improvement loop** for a
RAG use case: summarising Formula 1 team-radio messages across a race weekend. A Typer CLI takes
you from a raw RAG app to a measured, optimised, version-controlled prompt.

## What this does

Indexes a set of (synthetic) F1 team-radio messages in a local ChromaDB vector store, then answers
questions about the weekend by retrieving the relevant messages and summarising them with Claude.
On top of that RAG app it demonstrates the four Opik lifecycle steps, each as a CLI command:

- **`ingest`** — load the radio messages into ChromaDB (fully offline).
- **`ask`** — retrieve relevant messages and summarise them with Claude (traced in Opik).
- **`eval`** — create an Opik **dataset** and a **test suite** (plain-English assertions), then run
  both: `run_tests` for the assertions and `evaluate` with the `ContextRecall` and `Hallucination`
  metrics.
- **`optimize`** — run **Optimization Studio** (`opik-optimizer`) to improve the summariser prompt
  against the dataset, scored by an `AnswerRelevance` judge.
- **`promote`** — save the optimised prompt to the Opik **Prompt Library** (re-running versions it).
- **`run-all`** — chain ingest → eval → optimize → promote.

> **Note on the data.** OpenF1's `team_radio` endpoint returns audio recordings, not transcripts, so
> the radio messages here are **synthetic** (see `data/radio_messages.json`). The eval/optimize loop
> is identical for real transcripts once you have them.
>
> **Note on the optimizer.** It tunes the *prompt and model parameters* — how Claude turns retrieved
> messages into a summary — not the retriever. Retrieval quality is iterated separately and watched
> via the `ContextRecall` metric in `eval`.

## Prerequisites

```bash
pip install opik opik-optimizer chromadb litellm typer
```

Or, with `uv` (recommended — this folder is a `uv` project): `uv sync`.

| Environment variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | for `ask`/`eval`/`optimize`/`promote` | Anthropic key; used via litellm for generation, the LLM-judge metrics, and the optimizer |
| `OPIK_API_KEY` | for `eval`/`optimize`/`promote` | Your Opik API key. Unset → those commands run in DRY_RUN |
| `OPIK_WORKSPACE` | for `eval`/`optimize`/`promote` | Your Opik workspace name |
| `OPIK_PROJECT_NAME` | No | Opik project for traces/experiments (default `f1-radio-rag`) |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted Opik (default: Opik Cloud) |

## Running it

```bash
# Dry-run first — no credentials needed.
uv run f1rag ingest                                    # offline; populates ChromaDB
uv run f1rag ask "What tyre problems did drivers report?"   # prints retrieved messages + [DRY RUN]
uv run f1rag eval                                      # prints the dataset items + assertions it would create
uv run f1rag optimize                                  # prints what it would optimise
uv run f1rag promote                                   # prints what it would save

# Full run — set credentials, then the same commands talk to Claude + Opik.
export ANTHROPIC_API_KEY="<your-key>"
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"

uv run f1rag ask "Did McLaren use an undercut, and did it work?"   # real summary; trace in Opik
uv run f1rag eval        # dataset + test suite created; pass rate + experiment URL printed
uv run f1rag optimize    # initial -> optimised score printed; run visible in Optimization Studio
uv run f1rag promote     # optimised prompt saved to the Prompt Library (versioned)
uv run f1rag run-all     # the whole loop in one shot
```

## How it works

1. **Ingest** (`rag.py`) — `chromadb.PersistentClient` stores one document per radio message with
   session/driver/lap metadata, using ChromaDB's default local embeddings (no embedding-API cost).
2. **Ask** (`rag.py`) — `answer()` retrieves the top-k messages, then calls
   `litellm.completion(model="anthropic/claude-sonnet-4-6", ...)` with the summariser prompt from
   `prompts.py`. It's decorated with `@opik.track`, so each call appears as a trace in Opik.
3. **Eval** (`evaluation.py`) — builds an Opik dataset and a test suite, then scores the live RAG
   task. The test suite checks plain-English **assertions**; `evaluate` runs the `ContextRecall`
   (retrieval quality) and `Hallucination` (faithfulness) metrics. The eval cases live in
   `data/eval_cases.json`.
4. **Optimize** (`optimization.py`) — `MetaPromptOptimizer.optimize_prompt(...)` improves the
   `ChatPrompt` against the dataset, scored by a callable that wraps Opik's `AnswerRelevance` judge.
5. **Promote** (`prompts.py`) — `client.create_chat_prompt(...)` saves the optimised messages to the
   Prompt Library; re-running with the same name creates a new version.
