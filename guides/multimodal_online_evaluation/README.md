# Multimodal Online Evaluation

Run an online LLM-as-judge evaluation over multimodal (text + image) traces in Opik, and create the scoring rule two ways — in the UI and with the SDK.

## What this does

Logs traces that carry an image plus text, then shows how to score them with an online LLM-as-judge rule. It documents the common footguns — add image variables with the **"Images +"** button (not by hand-typing `{{image_output}}`), use a vision-capable model, and remember that score definitions are independent of variable mapping — and creates the identical rule both in the UI and programmatically with the SDK.

## Prerequisites

```bash
uv sync    # or: pip install "opik>=2.0.74"
```

| Variable | Description |
|---|---|
| `OPIK_API_KEY` | Opik API key |
| `OPIK_WORKSPACE` | Opik workspace name |
| `OPIK_URL_OVERRIDE` | Optional; defaults to `https://www.comet.com/opik/api` |

No LLM provider key is needed here — the judge runs inside Opik's online-evaluation rule, not in this notebook. Without credentials the notebook runs in dry-run and prints the payloads instead of sending them.

## Running it

```bash
uv sync
uv run --with jupyter jupyter lab
```

Then open `multimodal_online_evaluation.ipynb`.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/comet-ml/opik-examples/blob/main/guides/multimodal_online_evaluation/multimodal_online_evaluation.ipynb)

## How it works

The notebook logs two multimodal traces (one image as a public URL, one as a base64 data URI), then walks through creating the online-evaluation rule. The UI path is documented step by step with a copy-paste judge prompt; the SDK path creates the same rule via `client.rest_client.automation_rule_evaluators`, with the image supplied as an `image_url` content part rather than a text variable. The final section covers running the rule and reviewing the feedback scores.
