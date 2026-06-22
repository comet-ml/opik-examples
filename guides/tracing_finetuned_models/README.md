# Tracing fine-tuned models with Opik and the CometML Model Registry

Fine-tune a model, register it to the CometML Model Registry, then fetch it and trace every inference call in Opik — with a direct link from each trace back to the exact model version that produced it.

## What this does

Training and inference are typically disconnected: you know a prediction was made, but not which checkpoint produced it. This example closes that gap:

1. Fine-tune `distilgpt2` on an instruction dataset using HuggingFace trl
2. Register the trained model to the CometML Model Registry
3. Fetch the registered model by name and version
4. Run inference inside an Opik-traced function that attaches the registry URL as trace metadata

The result: every prediction in Opik carries a `model_registry_url` field that links directly to the CometML experiment and model version that produced it.

```
train_and_register.py          use_registered_model.py
        │                               │
        │  fine-tunes distilgpt2        │  fetches registered model
        │  logs checkpoints             │  runs Opik-traced inference
        ▼                               ▼
 CometML Model Registry ──────► Opik trace
   sft-distilgpt2 v1.0.0          metadata.model_registry_url
                                   metadata.model_version
```

## Prerequisites

### Environment variables

| Variable | Required for | Description |
|---|---|---|
| `COMET_API_KEY` | Both steps | Comet API key (shared with Opik) |
| `COMET_WORKSPACE` | Both steps | Comet workspace name (shared with Opik) |
| `COMET_REGISTRY_NAME` | Both steps | Model name in the registry (default: `sft-distilgpt2`) |
| `COMET_MODEL_VERSION` | Both steps | Version string (default: `1.0.0`) |
| `OPIK_API_KEY` | Step 2 | Same value as `COMET_API_KEY` |
| `OPIK_WORKSPACE` | Step 2 | Same value as `COMET_WORKSPACE` |
| `OPIK_PROJECT_NAME` | Step 2 | Opik project name (default: `tracing-finetuned-models`) |

> **Note:** CometML and Opik share the same API key and workspace on the Comet platform.

### Dependencies

Install with `uv` (recommended):

```bash
uv sync
```

Or with pip:

```bash
pip install comet_ml transformers trl datasets torch opik
```

## Running it

### Step 1 — Train and register

```bash
export COMET_API_KEY="<your-key>"
export COMET_WORKSPACE="<your-workspace>"
python train_and_register.py
```

Training takes a few minutes on a GPU, longer on CPU. When it finishes it prints the exact `COMET_REGISTRY_NAME` and `COMET_MODEL_VERSION` values to use in step 2.

### Step 2 — Fetch and trace

```bash
export COMET_API_KEY="<your-key>"
export COMET_WORKSPACE="<your-workspace>"
export COMET_REGISTRY_NAME="sft-distilgpt2"
export COMET_MODEL_VERSION="1.0.0"
python use_registered_model.py
```

**No credentials?** `use_registered_model.py` has a dry-run mode — it loads `distilgpt2` directly from HuggingFace and prints traces to the console.

### Notebook (Google Colab)

Open [`tracing_finetuned_models.ipynb`](./tracing_finetuned_models.ipynb) in Colab for an interactive version with step-by-step cells.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/comet-ml/opik-examples/blob/main/guides/tracing_finetuned_models/tracing_finetuned_models.ipynb)

## How it works

### Step 1: `train_and_register.py`

1. **Loads data** — 400 training examples and 100 eval examples from the OpenAssistant Guanaco dataset
2. **Trains** — `SFTTrainer` from `trl` fine-tunes `distilgpt2` for 3 epochs; a `CheckpointCallback` logs each epoch's checkpoint to the CometML experiment
3. **Registers** — the final model is saved and registered to the CometML Model Registry via `experiment.register_model()`, making it accessible by name and version from any machine

### Step 2: `use_registered_model.py`

1. **Downloads** — `api.get_model().download()` fetches the registered version by name and version string
2. **Loads** — standard HuggingFace `from_pretrained()` from the downloaded directory
3. **Traces** — the `generate()` function is decorated with `@opik.track`. Inside, `opik.update_current_trace()` attaches three metadata fields to every trace:
   - `model_registry_name` — the registry name
   - `model_version` — the version string
   - `model_registry_url` — a direct link to the model version in CometML

Open any Opik trace, click `model_registry_url`, and go directly to the CometML page showing the training run, hyperparameters, and checkpoints for that exact model version.
