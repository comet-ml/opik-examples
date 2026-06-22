---
name: add-eval-suite-items
description: Add new items (plain-English assertions) to an Opik test suite in this repo. Use when the user says "add an assertion", "add a test case to the suite", "extend the eval suite", "add a check to the test suite", "the model should also be tested for X", or describes a pass/fail criterion for an example's output. Appends to the canonical source file, then syncs via get_or_create_test_suite + suite.insert. Require a target example/suite and the assertion text; refuse to invent checks.
---

# Add items to an Opik test suite

A test suite checks an example's output against **plain-English assertions** scored by an
LLM judge — complementary to numeric metrics. Each suite item pairs the input `data` with a
list of `assertions`. Suite-wide assertions and the run policy are set once on the suite.

Reference implementation: `build_suite` in
[`evaluation.py`](../../../use-cases/f1_radio_rag/src/f1_radio_rag/evaluation.py); source
assertions live per-case in
[`data/eval_cases.json`](../../../use-cases/f1_radio_rag/data/eval_cases.json).

## When to refuse

You need both a **target example/suite name** and the **assertion text** (or a clear
criterion you can phrase as one). Don't invent checks — a vague or wrong assertion makes the
judge fail good outputs (or pass bad ones).

## Step 1 — Write good assertions

- **Plain English, judged true/false** about the output. e.g. *"Reports the front-left
  graining described in the radio messages."*
- **Grounded in the item's context** — only assert what the provided input/context supports.
- **One claim per assertion.** Split compound checks so a failure points at one thing.
- **Per-item vs global:** item-specific facts → the item's `assertions`. Checks that must
  hold for *every* item (e.g. "grounded in the provided messages", "invents nothing") →
  `global_assertions` on the suite.

## Step 2 — Append to the canonical source file

Add the assertion(s) to the item's `assertions` array in the source JSON (the SSOT that gets
committed). Keep the existing shape:

```json
{ "data": { "query": "..." }, "assertions": ["Check one ...", "Check two ..."] }
```

## Step 3 — Sync to Opik

```python
suite = client.get_or_create_test_suite(
    name=SUITE_NAME,
    global_assertions=[
        "The answer is grounded in the provided context",
        "The answer does not invent events absent from the context",
    ],
    global_execution_policy={"runs_per_item": 2, "pass_threshold": 2},
)
suite.insert([{"data": {"query": c["query"]}, "assertions": c["assertions"]} for c in cases])
```

- `global_execution_policy`: `runs_per_item` re-runs each item to catch nondeterminism;
  `pass_threshold` is how many of those runs must pass for the item to pass.
- `suite.insert` is idempotent the same way datasets are — re-running the builder is safe.

For f1_radio_rag, `uv run f1rag eval` rebuilds and runs the suite, so editing the source JSON
and running eval is the whole flow.

## Step 4 — Dry-run / credentials

Needs `OPIK_API_KEY` + `OPIK_WORKSPACE`; otherwise `DRY_RUN` prints the assertions it would
create:

```bash
cd use-cases/f1_radio_rag && uv run f1rag eval   # [DRY RUN] lists each query + its assertions
```

## Verify

- New assertions appear in the dry-run listing (or the suite in the Opik UI).
- Each assertion is grounded in that item's context and phrased as a single true/false claim.
- Source file is still valid JSON (`jq . data/eval_cases.json`).
