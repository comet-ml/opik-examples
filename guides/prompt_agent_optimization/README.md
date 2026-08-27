# Prompt & Agent Optimization with Opik — an A-to-Z guide

A single, **self-contained** notebook that teaches prompt and agent optimization
end-to-end, over one escalating RAG-over-docs example (a documentation assistant
for a fictional product, **Ledgerline**). It doubles as:

- a **live workshop** — run **Part 1** (~20 min) to optimize a prompt against an
  exact-match metric and see it in Opik; and
- a **take-home guide** — Parts 2–5 cover LLM-judge metrics (and how to *trust*
  them), multi-objective optimization with **real token cost**, comparing
  optimizers (MetaPrompt vs GEPA vs Few-Shot), agents, and how to choose.

Every optimization logs to Opik under **Evaluation → Optimization runs**, so each
step is a comparable run.

## What it covers

- **Part 0** — how to think about prompt optimization (prompt + dataset + metric).
- **Part 1** ⭐ — your first optimization: exact-match metric + `MetaPromptOptimizer`,
  with a before/after answer and a note on *steering* the optimizer.
- **Part 2 — Defining the objective** — LLM-judge metrics, *how to trust a judge*,
  and multi-objective optimization combining quality with **real token cost**
  (Opik's built-in `SpanCost`).
- **Part 3 — Choosing an optimizer** — **MetaPrompt vs GEPA vs Few-Shot** run
  head-to-head on the same task (what each one does differently), plus the
  selection table and chaining.
- **Part 4 — Going further** — a tool-calling `search_docs` agent, `ParameterOptimizer`
  (described), and pointers to more (tool optimization, HRPO, Evolutionary, and
  `OptimizableAgent` for optimizing your own app code).
- **Part 5** — promote the winner to the Prompt Library; pointers to Optimization
  Studio and the docs.

## Running it

The notebook is self-contained — it installs its dependencies and configures its
credentials in the first few cells, and defines its corpus + RAG app inline. Run
the cells top to bottom; for the workshop, stop at the end of Part 1.

- **Google Colab** — upload/open the notebook and run it; the first cell
  `%pip install`s everything.
- **Locally** — `uv sync` then `uv run jupyter lab` (or open the notebook in your
  editor's Jupyter). `uv` and the `pyproject.toml` are here for convenience; the
  notebook's own `%pip install` cell means it also runs in a bare environment.

## Credentials

The **Credentials** cell walks you through setup — no external environment dance
required:

- **Opik** — it calls `opik.configure()`, which prompts for your API key and
  workspace (get them free at [comet.com/opik](https://www.comet.com/opik)).
- **A model provider key** — the guide calls models through litellm. It defaults
  to a small Anthropic Claude model and prompts for your `ANTHROPIC_API_KEY`. To
  use another provider, set `OPIK_EXAMPLES_MODEL` (e.g. `openai/gpt-4o-mini`) and
  you'll be prompted for that provider's key instead.

If the relevant variables are already set in your environment (`OPIK_API_KEY`,
`OPIK_WORKSPACE`, `OPIK_EXAMPLES_MODEL`, the provider key, and optional
`OPIK_PROJECT_NAME`), the cell skips the prompts — which is how it runs
non-interactively in CI. There is **no dry-run**: optimization runs real
evaluations against your Opik workspace.

## How the code is organized

Everything lives **in the notebook** — the corpus, the tiny RAG app (a ChromaDB
retriever + an `answer()` function), the metrics, and every optimizer call. That's
deliberate: you can read it top to bottom, run it anywhere, and share it as a
single file with no external dependencies. Lifting the inline retriever/answer
helpers into a module to back a repeatable CLI is a natural next step.
