---
name: add-dataset-items
description: Add new items to an Opik evaluation dataset in this repo. Use when the user says "add a case to the dataset", "add items to the Opik dataset", "extend the eval dataset", "seed the dataset", "add test data for the eval", or names new query/expected-output pairs to evaluate. Appends to the example's canonical source data file first, then syncs to Opik via get_or_create_dataset + dataset.insert. Require a target example (or dataset name) and the item content; refuse to invent dataset rows.
---

# Add items to an Opik dataset

An Opik dataset is the set of inputs an example is evaluated against. In this repo each
example keeps a **canonical source file** (e.g. `data/eval_cases.json`) that a loader reads
and inserts into Opik — so dataset items live in two places and must stay in sync.

Reference implementation: [`use-cases/f1_radio_rag`](../../../use-cases/f1_radio_rag) —
source `data/eval_cases.json`, loaded by `data.py`, inserted by `build_dataset` in
[`evaluation.py`](../../../use-cases/f1_radio_rag/src/f1_radio_rag/evaluation.py).

## When to refuse

You need both:

- A **target example** (a folder under `use-cases/`, `guides/`, etc.) or an explicit dataset name.
- The **item content** — at minimum the query/input; ideally the expected output and any
  context fields the metrics need.

If either is missing, ask one short question. Do not fabricate dataset rows — bad data
silently corrupts every downstream eval and optimization run.

## Step 1 — Match the existing item schema

Read the example's source data file and copy the **exact key set** of existing items. Opik
dataset items are free-form dicts, but the evaluation task and metrics read specific keys.
For f1_radio_rag each item is:

```json
{
  "query": "What tyre problems did drivers report?",
  "expected_output": "Verstappen reported front-left graining ...",
  "messages": ["VER: Front-left is graining ...", "..."],
  "assertions": ["Reports the front-left graining ...", "..."]
}
```

New items must provide every key the task/metrics consume. Mismatched or missing keys throw
at eval time (`KeyError` in the task) — not at insert time.

## Step 2 — Append to the canonical source file

Add the new item(s) to the source JSON (the SSOT), preserving formatting. This is the change
that gets committed and reviewed. Keep entries grounded and self-consistent (the expected
output must actually follow from the provided context).

## Step 3 — Sync to Opik

Insert is **idempotent**: Opik content-hashes each item, so re-inserting the whole file only
adds genuinely new rows. The simplest sync is re-running the example's dataset builder.

```python
import opik

client = opik.Opik()  # env-driven; never hardcode workspace/keys
dataset = client.get_or_create_dataset(name=DATASET_NAME)
dataset.insert(items)  # items = the full list from the source file; identical rows are deduped
```

For f1_radio_rag, `build_dataset(client, load_eval_cases())` does exactly this, and
`uv run f1rag eval` calls it as part of the eval — so adding to `data/eval_cases.json` and
running eval is enough; no separate insert step needed.

## Step 4 — Dry-run / credentials

`dataset.insert` needs `OPIK_API_KEY` + `OPIK_WORKSPACE`. Without them, the example runs in
`DRY_RUN` and prints what it would create instead of calling Opik (see the repo convention in
[AGENTS.md](../../../AGENTS.md)). Verify the new items appear in the dry-run output:

```bash
cd use-cases/f1_radio_rag && uv run f1rag eval   # [DRY RUN] lists the dataset items it would create
```

## Verify

- The new item(s) show up in the dry-run listing (or in the Opik UI dataset when creds are set).
- The item's keys match what the eval task and metrics read — otherwise eval throws later.
- The source file is still valid JSON (`jq . data/eval_cases.json`).
