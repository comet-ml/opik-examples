# Opik Usage Stats

Fetch time-series metrics from an Opik workspace and render daily bar charts alongside a cumulative view — broken down by project.

## Metrics collected

| Metric | Chart | CSV |
|---|---|---|
| `TRACE_COUNT` | Daily bar + cumulative | `opik_stats_daily.csv`, `opik_stats_monthly.csv` |
| `THREAD_COUNT` | Daily bar + cumulative | same |
| `SPAN_COUNT` | Daily bar + cumulative | same |
| `TOKEN_USAGE` | CSV only | same |
| `COST` | CSV only | same |

## Setup

```bash
uv sync
```

## Configuration

Set the following environment variables before running:

| Variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | Yes | Your Opik API key |
| `OPIK_WORKSPACE` | No | Workspace name (uses account default if unset) |
| `OPIK_URL_OVERRIDE` | No | Base URL for self-hosted deployments |

## Usage

```bash
export OPIK_API_KEY=your_api_key
export OPIK_WORKSPACE=your_workspace   # optional

uv run python run_usage_stats.py
```

## Output

- **Charts** — saved to `opik_usage_stats.png` and displayed interactively
- **CSVs** — `opik_stats_daily.csv` and `opik_stats_monthly.csv` for further analysis

The CSVs include `workspace`, `project`, `metric`, `series`, `date`, and `value` columns, making them easy to group and filter in any tool.