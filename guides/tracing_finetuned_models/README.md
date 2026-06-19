# Tracing fine-tuned models with Opik and the CometML Model Registry

Fine-tune a model, register it to the CometML Model Registry, then fetch it and trace every inference call in Opik — with a direct link from each trace back to the exact model version that produced it.

## What this does

Training and inference are typically disconnected: you know a prediction was made, but not which checkpoint produced it. This example closes that gap. It shows the full workflow:

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

```bash
# Step 1 dependencies
pip install comet_ml transformers trl datasets torch

# Step 2 dependencies
pip install comet_ml opik transformers torch
```

### Environment variables

| Variable | Required for | Description |
|---|---|---|
| `COMET_API_KEY` | Both steps | CometML API key |
| `COMET_WORKSPACE` | Both steps | CometML workspace name |
| `COMET_REGISTRY_NAME` | Both steps | Model name in the registry (default: `sft-distilgpt2`) |
| `COMET_MODEL_VERSION` | Both steps | Version string (default: `1.0.0`) |
| `OPIK_API_KEY` | Step 2 | Opik API key |
| `OPIK_WORKSPACE` | Step 2 | Opik workspace name |
| `OPIK_PROJECT_NAME` | Step 2 | Opik project name (default: `tracing-finetuned-models`) |

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
export OPIK_API_KEY="<your-key>"
export OPIK_WORKSPACE="<your-workspace>"
python use_registered_model.py
```

**No credentials?** Both scripts have a dry-run mode. `train_and_register.py` requires CometML credentials to log anything; `use_registered_model.py` runs without any credentials — it loads `distilgpt2` directly from HuggingFace and prints traces to the console.

## How it works

### Step 1: `train_and_register.py`

1. **Loads data** — 400 training examples and 100 eval examples from the OpenAssistant Guanaco dataset
2. **Trains** — `SFTTrainer` from `trl` fine-tunes `distilgpt2` for 3 epochs; a `CheckpointCallback` logs each epoch's checkpoint to the CometML experiment
3. **Registers** — after training, the final model is saved and registered to the CometML Model Registry via `experiment.register_model()`. This makes it accessible by name and version from any machine

### Step 2: `use_registered_model.py`

1. **Downloads** — `comet_ml.API().download_registry_model()` fetches the registered version by name and version string
2. **Loads** — standard HuggingFace `from_pretrained()` from the downloaded directory
3. **Traces** — the `generate()` function is decorated with `@opik.track`. Inside, `opik.update_current_trace()` attaches three metadata fields to every trace:
   - `model_registry_name` — the registry name
   - `model_version` — the version string
   - `model_registry_url` — a direct link to the model version in CometML

The metadata link means you can open any Opik trace, click the `model_registry_url`, and go directly to the CometML page showing the training run, hyperparameters, and checkpoints for that exact model version.
