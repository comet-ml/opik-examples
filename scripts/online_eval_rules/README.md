# Online Evaluation Rules — SDK & REST

Create and manage Opik **online evaluation rules** (automation rule evaluators) from code —
shown with the Python SDK and the raw REST API side by side, across every common rule type.

## What this does

Online evaluation rules automatically score your traces, threads, and spans as they arrive —
using an LLM-as-judge prompt or a user-defined Python metric. This example provisions and manages
those rules programmatically (project onboarding, CI, bulk setup) instead of clicking through the
UI. One payload is built per rule and sent through either surface; in dry-run it prints **both**
the SDK call and an equivalent `curl`, so you can copy whichever fits your stack.

Rule types covered: `llm_as_judge`, `user_defined_metric_python`, `trace_thread_llm_as_judge`,
`span_llm_as_judge`, `span_user_defined_metric_python`. Full lifecycle: create, list, get, update
(sampling rate / enabled), delete.

## Prerequisites

```bash
uv sync            # recommended (this folder is a uv project)
# or: pip install "opik>=2.0" requests
```

| Environment variable | Required | Description |
|---|---|---|
| `OPIK_API_KEY` | for a live run | Opik API key. Unset → the script runs in DRY_RUN |
| `OPIK_WORKSPACE` | for a live run | Opik workspace name |
| `OPIK_URL_OVERRIDE` | No | Opik API base URL for self-hosted (default: `https://www.comet.com/opik/api`) |
| `OPIK_PROJECT_NAME` | No | Project the rules attach to; created if absent (default: `online-eval-rules-example`) |

> **LLM-as-judge rules also need an LLM provider key configured in your workspace**
> (Opik → Configuration → AI providers). Python-metric rules do not. If it's missing, a live
> create prints an actionable error. The project itself is created automatically by name.

## Running it

```bash
# Dry-run — no credentials needed. Prints the SDK call AND the curl for the rule.
uv run create-online-eval-rules create-llm-judge --name relevance --dry-run

# Live — set credentials, then create each rule type.
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"

uv run create-online-eval-rules create-llm-judge --name relevance
uv run create-online-eval-rules create-python     --name exact-match
uv run create-online-eval-rules create-thread     --name convo-quality
uv run create-online-eval-rules create-span       --name span-relevance
uv run create-online-eval-rules create-span       --name span-check --python

# Choose the live surface (default sdk):
uv run create-online-eval-rules create-llm-judge --name relevance --surface rest

# Manage:
uv run create-online-eval-rules list
uv run create-online-eval-rules get    --id <rule-id>
uv run create-online-eval-rules update --id <rule-id> --sampling-rate 0.2 --disabled
uv run create-online-eval-rules update --id <rule-id> --enabled          # re-enable
uv run create-online-eval-rules delete --id <rule-id> --yes
```

> Note: `update` always uses the REST surface (the SDK update-union types differ).

## How it works

1. **Config** — credentials + project come from env vars; `DRY_RUN` is on whenever the
   key/workspace pair is absent (or `--dry-run` is passed).
2. **One payload** — `build_payload()` returns the plain JSON dict the REST API accepts, per rule
   type (thread judges omit `variables`; Python-metric rules embed `metric_example.py` as source).
3. **Two adapters** — `via_sdk()` maps the dict to the typed `AutomationRuleEvaluatorWrite_*` union
   and calls `opik.Opik().rest_client.automation_rule_evaluators.*`; `via_rest()` sends the same
   dict with `requests`. `--surface` picks the live path.
4. **Dry-run shows both** — `render_sdk_snippet()` and `render_curl()` print the SDK call and the
   curl from the one payload, so the two surfaces never drift.
