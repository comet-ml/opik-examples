# MCP-driven GPU capacity planning

Pull system metrics from Comet EM training runs through the **Comet MCP server**, flag
under-utilized hardware with simple heuristics, have an **LLM write rightsizing
recommendations**, and trace the whole pipeline in **Opik** so the recommendation runs can be
reviewed (e.g. by Opik Diagnostics).

```text
Comet EM training runs
        │  uvx comet-mcp  (or the bundled synthetic server when no COMET_API_KEY)
        ▼
collector: list_projects → list_experiments → details / parameters / metric series
        │        declared num_gpus, gpu_type   vs   measured sys.gpu.N.gpu_utilization
        ▼
analysis: rule-based flags (idle, under-utilized, declared≠detected, CPU-bound)
        │
        ▼
recommender: one litellm call → Markdown rightsizing report
        │
        ▼
Opik trace: capacity_audit ─ tool spans per MCP call ─ analyze span ─ LLM span (tokens/cost)
```

## What this does

Teams routinely over-provision training hardware because *declared* capacity (`num_gpus`,
`gpu_type` hyperparameters) and *actual* utilization (`sys.gpu.*` system metrics) live in
different places and nobody joins them — 64 declared GPUs running at 12% mean utilization is
a real, common finding. This guide closes that loop with the Comet ecosystem: the Comet MCP
server exposes EM experiment data as tools, deterministic code sweeps the runs and computes
utilization-vs-declared findings, an LLM turns the findings into concrete rightsizing
recommendations, and Opik records every MCP call, the analysis, and the LLM call (with token
costs) as one trace per audit.

Two commands share the same five MCP tools (`list_projects`, `list_experiments`,
`get_experiment_details`, `get_experiment_parameters`, `get_experiment_metric_data`):

- **`audit`** — deterministic sweep → findings table → LLM report. Reproducible, bounded cost.
- **`ask`** — the LLM drives the tools itself in a bounded loop, for free-form questions like
  *"Which projects waste the most GPU hours?"*

## Prerequisites

```bash
uv sync
```

(Or `pip install opik litellm typer mcp`.) Live mode also needs `uvx` on your `PATH` — it
ships with [uv](https://docs.astral.sh/uv/).

| Variable | Needed for | Notes |
|---|---|---|
| `OPIK_API_KEY` / `OPIK_WORKSPACE` | Opik traces + LLM report | Both unset → **DRY_RUN**: no LLM call, no traces; heuristics still run |
| `ANTHROPIC_API_KEY` | The LLM call via litellm | Or any provider key matching the model you set |
| `OPIK_EXAMPLES_MODEL` | Optional model override | Default `anthropic/claude-sonnet-5` |
| `COMET_API_KEY` / `COMET_WORKSPACE` | Real EM data | Unset → the bundled **synthetic** MCP server serves `data/sample_runs.json` |
| `COMET_URL_OVERRIDE` / `OPIK_URL_OVERRIDE` | Self-hosted deployments | Optional |
| `OPIK_PROJECT_NAME` | Trace destination | Default `gpu-capacity-planning` |
| `CAPACITY_LOW_UTIL_PCT` / `CAPACITY_IDLE_UTIL_PCT` / `CAPACITY_MAX_RUNS` | Threshold tuning | Defaults 30 / 10 / 50 |

The two credential pairs gate independently, giving three useful modes:

1. **No credentials** — synthetic data + dry run. What CI runs; works offline.
2. **Opik + LLM keys only** — synthetic EM data, real LLM report, real Opik traces. Try the
   full story without a populated EM workspace.
3. **All credentials** — audit your real training runs.

## Running it

```bash
# 1. Dry run (no credentials needed) — synthetic runs, rule-based findings, exit 0
uv run gpu-capacity-planning audit

# 2. Real LLM report + Opik traces over the synthetic runs
export OPIK_API_KEY=... OPIK_WORKSPACE=... ANTHROPIC_API_KEY=...
uv run gpu-capacity-planning audit

# 3. Live against your Comet EM workspace
export COMET_API_KEY=... COMET_WORKSPACE=...
uv run gpu-capacity-planning list-runs                     # collection only, no LLM
uv run gpu-capacity-planning audit -p my-project --output report.md
uv run gpu-capacity-planning ask "Which projects waste the most GPU hours?"
```

`--synthetic` forces the bundled server even when Comet credentials are set.

## How it works

- **`mcp_client.py`** — picks the server (`uvx comet-mcp` live, or
  `python -m gpu_capacity_planning.synthetic_server` bundled) and opens a stdio
  `ClientSession`. `call_tool()` is the single choke point every MCP call goes through, so
  each call becomes an Opik tool span. `openai_tool_defs()` converts the server's MCP schemas
  into OpenAI-format tool definitions for litellm.
- **`collector.py`** — deterministic sweep. For each run: details (name, URL, timestamps,
  available metric names), parameters (declared `num_gpus` / `gpu_type`), then one batched
  `get_experiment_metric_data` call for the `sys.gpu.N.*` and CPU series. Produces one
  `RunMetrics` per run with utilization means/peaks.
- **`analysis.py`** — pure rules, no LLM: mean GPU utilization under the idle threshold →
  **high**; under the target threshold → **medium**; declared ≠ detected GPU count → flag;
  high CPU + idle GPU → likely dataloader-bound; missing metrics → instrumentation advice.
  Also estimates wasted GPU-hours (`duration × GPUs × (1 − util)` over flagged runs).
- **`recommender.py`** — one `litellm` call turns the findings JSON into the Markdown
  recommendations section. Opik's litellm callback nests the LLM span (model, tokens, cost)
  under the audit trace.
- **`agent.py`** — the `ask` loop: litellm tool-calling against the same MCP session, bounded
  by `--max-turns`.
- **`synthetic_server.py`** — a FastMCP server that mimics comet-mcp's five tools from
  `data/sample_runs.json` (six fictional runs: the 64-GPU/12% offender, a healthy LoRA run, a
  CPU-bound run, a declared/detected mismatch, an uninstrumented run, and a well-utilized
  baseline). Because it speaks the same tool contract, the dry run exercises the exact code
  path used against production.

## Viewing the results in Opik

Each `audit` produces one trace named **`capacity_audit`** in the `gpu-capacity-planning`
project: `fetch_run` spans per experiment (with the per-run metrics), `call_tool` tool spans
per MCP call, an `analyze` span, and a `write_recommendations` span with the nested LLM call.
Trace tags (`capacity-planning`, `comet-em`, `mcp`, `live`/`synthetic`) and metadata
(workspace, runs analyzed/flagged, GPU-hours, thresholds, model) are the stable contract to
filter or aggregate on — including for automated review of the audit runs themselves via
Opik's trace analysis features. `ask` produces a **`capacity_agent`** trace with one LLM span
per turn plus the tool spans it triggered.

## Using the Comet MCP server with your own agent

The repo ships a [.mcp.json](./.mcp.json) with the same server definition this example spawns
programmatically. Point Claude Code, Cursor, or any MCP-capable agent at it and explore the
same workspace interactively — the `ask` command is exactly that loop, minus the IDE.
