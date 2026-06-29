---
name: run-optimizations
description: Run an Opik prompt optimization (opik-optimizer) for an example in this repo, and optionally promote the result to the Prompt Library. Use when the user says "optimize the prompt", "run the optimizer", "improve the prompt", "run Optimization Studio", "tune the prompt", or wants a measured better prompt for an example. Covers the metric-callable shape, reading the score delta + run link, and versioning the winner. Require a target example with an eval dataset; refuse to optimize without a dataset to score against.
---

# Run a prompt optimization

`opik-optimizer` searches for a better prompt by scoring candidates against a dataset with a
metric. It tunes the **prompt and model params** — not the retriever. Retrieval quality is a
separate concern, watched via `ContextRecall` in `run-evals`.

Reference: `run_optimization` in
[`optimization.py`](../../../use-cases/f1_radio_rag/src/f1_radio_rag/optimization.py);
`promote` in [`prompts.py`](../../../use-cases/f1_radio_rag/src/f1_radio_rag/prompts.py);
CLI [`cli.py`](../../../use-cases/f1_radio_rag/src/f1_radio_rag/cli.py) `optimize`/`promote`.

## When to refuse

Need a **target example with an eval dataset** to score against — optimization is meaningless
without a metric over real data. If there's no dataset, route to `add-dataset-items` first.

## Step 1 — Credentials gate

Needs `OPIK_API_KEY` + `OPIK_WORKSPACE` and the model provider key (e.g. `ANTHROPIC_API_KEY`).
Dry-run first:

```bash
cd use-cases/f1_radio_rag
uv run f1rag optimize                   # DRY_RUN: prints what it would optimize
export ANTHROPIC_API_KEY=... OPIK_API_KEY=... OPIK_WORKSPACE=...
uv run f1rag optimize                   # real run: prints initial -> optimised score + run link
```

## Step 2 — The metric is a plain callable

Optimizer metrics are **not** the metric classes directly — they're callables
`(dataset_item: dict, llm_output: str) -> float` with `__name__` set (the name shows in the
Opik UI). Wrap an LLM-judge metric to score against something real:

```python
from opik.evaluation.metrics import AnswerRelevance

def _relevance_metric(dataset_item: dict, llm_output: str) -> float:
    result = AnswerRelevance(model=JUDGE_MODEL).score(
        input=dataset_item["query"], output=llm_output, context=dataset_item["messages"],
    )
    return result.value

_relevance_metric.__name__ = "answer_relevance"
```

## Step 3 — Build the prompt and run the optimizer

```python
from opik_optimizer import ChatPrompt, MetaPromptOptimizer

prompt = ChatPrompt(name=PROMPT_NAME, system=SYSTEM_PROMPT, user=USER_TEMPLATE, model=GEN_MODEL)
optimizer = MetaPromptOptimizer(model=OPTIMIZER_MODEL, n_threads=4, skip_perfect_score=False)
result = optimizer.optimize_prompt(
    prompt=prompt, dataset=dataset, metric=_relevance_metric, max_trials=12, n_samples=8,
)
```

- `ChatPrompt.user` uses single-brace `{field}` placeholders that bind to dataset item fields.
- `skip_perfect_score=False` forces every round even when the baseline already scores high.
- `max_trials` / `n_samples` trade cost for thoroughness — keep them modest for demos.

## Step 4 — Read the result

- `result.initial_score` → `result.score` — the improvement (or lack of it). Report both.
- `result.get_run_link()` — link to the run in Optimization Studio. Surface it.
- `result.prompt.get_messages()` — the optimised messages, for promotion.

## Step 5 — Promote (optional, only when asked or score improved)

Saving versions the prompt in the Prompt Library; re-using the same `name` appends a version
(upsert — no separate update call, no in-place edit).

```python
client.create_chat_prompt(
    name=PROMPT_NAME,
    messages=result.prompt.get_messages(),
    change_description=f"optimised score {result.score:.3f}",
    tags=["optimised"],
)
```

Don't promote a regression. If `result.score <= result.initial_score`, report it and stop —
ask before saving a worse prompt over a working one.

## Verify

- Dry-run prints the prompt/dataset it would optimize before the real run.
- Real run prints `initial -> optimised` score and a run link; open it to inspect trials.
- After promote, the new version appears under the prompt name in the Opik Prompt Library UI.
