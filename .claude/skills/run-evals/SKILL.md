---
name: run-evals
description: Run an Opik evaluation for an example in this repo — metrics (evaluate) and/or assertions (run_tests) against a dataset/test suite. Use when the user says "run the eval", "evaluate the example", "run the test suite", "score the model", "check the metrics", "what's the pass rate", or wants to measure an example's quality in Opik. Covers the credentials/DRY_RUN gate, metric selection, experiment naming, and reading results. Require a target example; refuse to guess which one.
---

# Run an Opik evaluation

Two complementary scorers, usually run together:

- **`run_tests(test_suite, ...)`** — judges the plain-English assertions in a test suite.
  Returns `.pass_rate` and `.experiment_url`.
- **`evaluate(dataset, ...)`** — runs numeric `scoring_metrics` over a dataset.

Reference: `run_eval` in
[`evaluation.py`](../../../use-cases/f1_radio_rag/src/f1_radio_rag/evaluation.py); CLI
[`cli.py`](../../../use-cases/f1_radio_rag/src/f1_radio_rag/cli.py) `eval` command.

## When to refuse

Need a **target example** (folder + its dataset/suite). If the repo has several, ask which.
Don't run evals blindly — they call LLM-judge models and cost tokens/time.

## Step 1 — Credentials gate

`evaluate` / `run_tests` need `OPIK_API_KEY` + `OPIK_WORKSPACE`, and the judge/generation
models need their provider key (e.g. `ANTHROPIC_API_KEY`). Without Opik creds the example
runs in `DRY_RUN` and prints what it would create. Run the dry-run first to confirm the
dataset/suite content, then set creds for the real run.

```bash
cd use-cases/f1_radio_rag
uv run f1rag eval                       # DRY_RUN: lists dataset items + assertions
export ANTHROPIC_API_KEY=... OPIK_API_KEY=... OPIK_WORKSPACE=...
uv run f1rag eval                       # real run: prints pass rate + experiment URL
```

## Step 2 — The task and the shape it returns

The evaluation task is `(item: dict) -> dict`. It runs the live app on the item and returns
the fields the metrics consume — for RAG: `{"input", "output", "context"}`. Reuse the
example's existing task (don't reimplement the app inside the eval).

```python
from opik.evaluation import evaluate, run_tests
from opik.evaluation.metrics import ContextRecall, Hallucination

def task(item: dict) -> dict:
    return app_under_test(item["query"])   # -> {"input","output","context"}
```

## Step 3 — Pick metrics that match the failure modes

- `ContextRecall` — did retrieval surface the needed context? (RAG retrieval quality)
- `Hallucination` — is the answer faithful to the context? (faithfulness)
- `AnswerRelevance` — does the answer address the question?
- Add others from `opik.evaluation.metrics` as the use case needs. Each LLM-judge metric
  takes `model=...`.

```python
run_tests(test_suite=suite, task=task, model=JUDGE_MODEL, experiment_name=experiment_name())
evaluate(dataset=dataset, task=task,
         scoring_metrics=[ContextRecall(model=JUDGE_MODEL), Hallucination(model=JUDGE_MODEL)],
         experiment_name=experiment_name())
```

Use a unique `experiment_name` per run (the example does `f"{project}-{secrets.token_hex(3)}"`)
so runs don't overwrite each other in the UI.

## Step 4 — Read results

- `suite_result.pass_rate` — fraction of suite items passing their assertions.
- `suite_result.experiment_url` / `result.get(...)` — link to the run in Opik for per-item
  drill-down. Surface the URL to the user.

## Verify

- Dry-run lists the expected dataset/suite content before the real run.
- Real run prints a pass rate and an experiment URL; open it to confirm per-item scores.
- If the task throws `KeyError`, a dataset item is missing a key the task/metrics read — fix
  the data (see the `add-dataset-items` skill), not the task.
