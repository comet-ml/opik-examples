# Visualise multi-turn feedback scores

Pull every trace in an Opik conversation thread, read each turn's feedback scores, and plot how those scores evolve so you can see where a multi-turn chat improved or went off course.

## What this does

Given a `project-name` and `thread-id`, the script:

1. Searches Opik for all traces belonging to that thread.
2. Orders them by `start_time` (turn 1, turn 2, …).
3. Reads each trace's `feedback_scores`.
4. Writes a PNG line chart (one series per score name) and optionally a CSV.

When credentials are missing it runs in **DRY_RUN** with sample data and still produces a chart — so CI and local smoke tests work without an Opik account.

## Prerequisites

```bash
uv sync
```

Optional fallback: `pip install opik matplotlib`.

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | for a live run | Your Opik API key. Unset → DRY_RUN |
| `OPIK_WORKSPACE` | for a live run | Your Opik workspace name |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted Opik |
| `OPIK_PROJECT_NAME` | No | Default project if `--project-name` is omitted |

## Running it

```bash
# Dry-run first — no credentials needed; writes a sample PNG.
uv run visualize-thread-feedback-scores --dry-run
uv run visualize-thread-feedback-scores --dry-run --output demo.png --csv demo.csv

# Live run — set credentials, then pass project + thread.
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"

uv run visualize-thread-feedback-scores \
  --project-name "<project>" \
  --thread-id "<thread-id>" \
  --output thread_scores.png \
  --csv thread_scores.csv
```

Or via the CI entrypoint:

```bash
bash run.sh
```

## How it works

1. Read `OPIK_API_KEY` / `OPIK_WORKSPACE`. If missing (or `--dry-run`), use sample data.
2. Live mode: `search_traces` with `thread_id = "..."`, sort by `start_time`.
3. Read each trace's `feedback_scores` and draw a PNG line chart; optional CSV one row per turn.

## Development

```bash
uv sync --group dev
uv run ruff check .
uv run --with pytest pytest -q
```
