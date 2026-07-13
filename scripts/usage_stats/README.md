# Opik Usage Stats

A small, self-contained example that collects usage metrics for a single
**Opik** workspace via the Opik SDK and renders a themed, offline HTML report
(plus CSV exports and a console summary).

It demonstrates two complementary Opik SDK collection methods:

- `rest_client.projects.get_project_metrics` — daily time series
  (traces, spans, threads, token usage, cost).
- `rest_client.projects.get_project_stats` — the current per-project snapshot
  (trace/thread counts, per-model token usage, estimated cost, guardrail
  failures).

## Growth & adoption reporting → use cometx

This example focuses on **current + recent usage** for one workspace. For
**cross-platform use-case growth & adoption** reporting — how many use cases
exist and how fast they are being created, across **Opik + Experiment
Management + Model Production Monitoring** — use the `cometx` CLI:

```bash
pip install cometx --upgrade
cometx admin growth-report            # all workspaces your API key can see
```

See the [`cometx admin growth-report` docs](https://github.com/comet-ml/cometx/blob/main/README.md#growth-report).

## Setup

```bash
cd scripts/usage_stats
uv sync
```

## Configuration

| Variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | Yes | Your Opik API key |
| `OPIK_WORKSPACE` | No | Workspace name (defaults to your default workspace) |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted Opik deployments |

## Usage

```bash
cd scripts/usage_stats
export OPIK_API_KEY=your_api_key
export OPIK_WORKSPACE=your_workspace          # optional
export OPIK_URL_OVERRIDE=https://your-host    # self-hosted only
uv run python run_usage_stats.py
```

The analysis window for the time-series charts is the **last 30 days**. To
change it, edit the `WINDOW_DAYS` constant at the top of `run_usage_stats.py`.

## Output

Written to the current directory:

- `report.html` — self-contained, themed (light/dark) report: a per-project
  snapshot table, interactive time-series charts (daily bars + cumulative area
  for traces/spans/threads, with labelled x/y axes and a crosshair + hover
  tooltip), and token/cost tables. Charts are inline SVG with a small inline-JS
  interaction layer — no external assets, opens offline.
- `stats_daily.csv` — one row per project/metric/series/day.
- `stats_monthly.csv` — the same data rolled up to a monthly grain.
- `stats_summary.csv` — the current per-project snapshot.

No credentials are ever written to any output file.

## Development

```bash
cd scripts/usage_stats
uv run --with pytest pytest -v
uv run ruff check .
```

## Manual live verification

The test suite is fully offline. Before shipping a change that touches
collection or rendering, verify against a real workspace:

```bash
cd scripts/usage_stats
export OPIK_API_KEY=...      # a real key
export OPIK_WORKSPACE=...    # optional
uv run python run_usage_stats.py
```

Confirm: the command exits `0`; `report.html` opens in a browser and shows the
snapshot table, temporal charts, and token/cost tables, with a working
light/dark appearance; the CSVs are populated; and no API key appears in any
output (`grep -r "$OPIK_API_KEY" .` returns nothing). Delete any generated
`report.html` / `*.csv` before committing.
