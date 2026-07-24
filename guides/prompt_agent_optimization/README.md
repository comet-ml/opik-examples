# Prompt & Agent Optimization with Opik — an A-to-Z guide

A single notebook that teaches prompt and agent optimization end-to-end, over one
escalating RAG-over-docs example (a documentation assistant for a fictional
product, **Ledgerline**). It doubles as:

- a **live workshop** — run **Part 1** (~20 min) to optimize a prompt against an
  exact-match metric and see it in Opik; and
- a **take-home guide** — Parts 2–5 cover LLM-judge metrics (and how to *trust*
  them), multi-objective optimization, agent/tool optimization, and choosing an
  optimizer.

Every optimization logs to Opik under **Evaluation → Optimization runs**, so each
step is a comparable run.

## What it covers

- **Part 0** — how to think about prompt optimization (prompt + dataset + metric).
- **Part 1** ⭐ — your first optimization: exact-match metric + `MetaPromptOptimizer`.
- **Part 2** — LLM-judge metrics, *how to trust a judge*, and multi-objective
  optimization with `MultiMetricObjective`.
- **Part 3** — from prompt to agent: a retrieval gate, `FewShotBayesianOptimizer`,
  and `ParameterOptimizer`.
- **Part 4** — choosing an optimizer (selection table + how to choose + chaining).
- **Part 5** — promote the winner to the Prompt Library; pointers to Optimization
  Studio and the docs.

## Prerequisites

```bash
uv sync
```

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | yes | Your Opik API key. |
| `OPIK_WORKSPACE` | yes | Your Opik workspace name. |
| `ANTHROPIC_API_KEY` (or the key for your `OPIK_EXAMPLES_MODEL` provider) | yes | Model-provider key used via litellm for generation, judging, and optimizing. |
| `OPIK_PROJECT_NAME` | no | Opik project for traces/runs (default `prompt-agent-optimization`). |
| `OPIK_EXAMPLES_MODEL` | no | litellm model (default `anthropic/claude-sonnet-4-6`). Use a cheap model to run fast. |
| `OPIK_URL_OVERRIDE` | no | Base URL for self-hosted Opik. |

There is **no dry-run** — optimization requires running real evaluations. The
notebook's first cell fails fast if a required variable is missing.

## Running it

Open `prompt_agent_optimization.ipynb` in Jupyter and run cells top to bottom.
For the workshop, stop at the end of Part 1. You can launch JupyterLab directly
with `uv run jupyter lab` (it's included as a project dependency).

## How the code is organized

Optimization code (`ChatPrompt`, metrics, optimizer calls) lives **inline in the
notebook** — it's the lesson. Repeated plumbing (retriever, data loading) lives in
`optimization_guide/` so it stays out of the way and could back a future CLI.
