"""
Step 2 of 2: Fetch a registered model from the CometML Model Registry and
trace inference with Opik.

Every Opik trace includes a direct link back to the registered model version
that produced it — so you can always trace a prediction back to the exact
checkpoint.

Set USE_MODEL_REGISTRY=true to download from the CometML registry (requires
COMET_API_KEY, COMET_WORKSPACE, and a registered model). Without it the script
loads distilgpt2 directly from HuggingFace. Opik tracing runs in either case
as long as OPIK_API_KEY + OPIK_WORKSPACE are set.

Run:
    pip install comet_ml opik transformers torch
    export OPIK_API_KEY="<your-api-key>"
    export OPIK_WORKSPACE="<your-workspace>"
    # Optional — use a registered model instead of HuggingFace:
    # export USE_MODEL_REGISTRY=true
    # export COMET_API_KEY="<your-api-key>"
    # export COMET_WORKSPACE="<your-workspace>"
    # export COMET_REGISTRY_NAME="sft-distilgpt2"
    # export COMET_MODEL_VERSION="1.0.0"
    python use_registered_model.py
"""

import os

import opik
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ── Credentials ───────────────────────────────────────────────────────────────
OPIK_API_KEY    = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE  = os.environ.get("OPIK_WORKSPACE")
COMET_API_KEY   = os.environ.get("COMET_API_KEY")
COMET_WORKSPACE = os.environ.get("COMET_WORKSPACE")

REGISTRY_NAME   = os.environ.get("COMET_REGISTRY_NAME", "sft-distilgpt2")
MODEL_VERSION   = os.environ.get("COMET_MODEL_VERSION", "1.0.0")
MODEL_LOCAL_DIR = "./downloaded_model"
OPIK_PROJECT    = os.environ.get("OPIK_PROJECT_NAME", "tracing-finetuned-models")

USE_REGISTRY = os.environ.get("USE_MODEL_REGISTRY", "").lower() in ("1", "true", "yes")
DRY_RUN      = not (OPIK_API_KEY and OPIK_WORKSPACE)

# Module-level model handles — populated in main() before any inference call.
tokenizer = None
model     = None


# ── Step 1: Fetch model from the CometML Model Registry ──────────────────────
def download_registered_model() -> str:
    """Download a specific model version from the CometML Model Registry."""
    import comet_ml

    api = comet_ml.API(api_key=COMET_API_KEY)
    print(f"Downloading {REGISTRY_NAME} v{MODEL_VERSION} from CometML Model Registry...")
    registered_model = api.get_model(workspace=COMET_WORKSPACE, model_name=REGISTRY_NAME)
    registered_model.download(version=MODEL_VERSION, output_folder=MODEL_LOCAL_DIR, expand=True)
    print(f"Model downloaded to {MODEL_LOCAL_DIR}\n")
    return MODEL_LOCAL_DIR


def registry_url() -> str:
    workspace = COMET_WORKSPACE or "your-workspace"
    return f"https://www.comet.com/{workspace}/model-registry/{REGISTRY_NAME}/{MODEL_VERSION}"


# ── Step 2: Load model ────────────────────────────────────────────────────────
def load_model(model_dir: str) -> None:
    global tokenizer, model
    tokenizer           = AutoTokenizer.from_pretrained(model_dir)
    model               = AutoModelForCausalLM.from_pretrained(model_dir)
    model.eval()


# ── Step 3: Opik-traced inference ─────────────────────────────────────────────
@opik.track(project_name=OPIK_PROJECT)
def generate(prompt: str, max_new_tokens: int = 100) -> str:
    """Run inference; attach registry metadata to the trace when a registry model is loaded."""
    if USE_REGISTRY:
        opik.update_current_trace(
            metadata={
                "model_registry_name": REGISTRY_NAME,
                "model_version":       MODEL_VERSION,
                "model_registry_url":  registry_url(),
            }
        )

    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
            do_sample=False,
        )
    return tokenizer.decode(output_ids[0], skip_special_tokens=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    if USE_REGISTRY:
        model_dir = download_registered_model()
    else:
        print("USE_MODEL_REGISTRY not set — loading distilgpt2 from HuggingFace.")
        print("Set USE_MODEL_REGISTRY=true (+ COMET_API_KEY / COMET_WORKSPACE) to use a registered model.\n")
        model_dir = "distilgpt2"

    load_model(model_dir)

    prompts = [
        "The main advantage of fine-tuning a language model is",
        "Supervised fine-tuning works by",
        "To evaluate a fine-tuned model you should",
    ]

    for prompt in prompts:
        response = generate(prompt)
        print(f"Prompt:   {prompt}")
        print(f"Response: {response}\n")

    if DRY_RUN:
        print("[DRY RUN] OPIK_API_KEY / OPIK_WORKSPACE not set — traces were not sent to Opik.")
    else:
        opik.flush_tracker()
        print(f"Traces sent to Opik project '{OPIK_PROJECT}'.")


if __name__ == "__main__":
    main()
