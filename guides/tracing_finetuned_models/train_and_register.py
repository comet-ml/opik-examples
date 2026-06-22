"""
Step 1 of 2: Fine-tune a model and register it to the CometML Model Registry.

Fine-tunes distilgpt2 on the OpenAssistant Guanaco dataset using supervised
fine-tuning (SFT) via HuggingFace trl. Checkpoints are logged to a CometML
experiment during training; the final model is registered to the Model Registry
so it can be fetched by name and version in step 2.

After this script completes it prints the registry name and version to use
in use_registered_model.py.

Run:
    pip install comet_ml transformers trl datasets torch
    export COMET_API_KEY="<your-api-key>"
    export COMET_WORKSPACE="<your-workspace>"
    python train_and_register.py
"""

# comet_ml must be imported before transformers/trl — the Trainer integration
# hooks in at import time.
import comet_ml  # noqa: F401

import os
import shutil
import torch
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainerCallback
from trl import SFTTrainer, SFTConfig

# ── Config ────────────────────────────────────────────────────────────────────
MODEL_NAME        = "distilgpt2"
REGISTRY_NAME     = os.environ.get("COMET_REGISTRY_NAME", "sft-distilgpt2")
MODEL_VERSION     = os.environ.get("COMET_MODEL_VERSION", "1.0.0")
NUM_EPOCHS        = 3
BATCH_SIZE        = 4
LEARNING_RATE     = 2e-5
MAX_SEQ_LENGTH    = 256
OUTPUT_DIR        = "./results_sft"
FINAL_MODEL_DIR   = "./final_model"

# ── Dataset ───────────────────────────────────────────────────────────────────
dataset       = load_dataset("timdettmers/openassistant-guanaco")
train_dataset = dataset["train"].select(range(400))
eval_dataset  = dataset["test"].select(range(100))

# ── Model + tokenizer ─────────────────────────────────────────────────────────
tokenizer             = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.pad_token   = tokenizer.eos_token
model                 = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

# ── Callback: log a checkpoint artifact every epoch ───────────────────────────
class CheckpointCallback(TrainerCallback):
    def on_train_begin(self, args, state, control, **kwargs):
        experiment = comet_ml.get_running_experiment()
        if experiment:
            experiment.add_tag("SFT")

    def on_epoch_end(self, args, state, control, model=None, **kwargs):
        epoch = int(state.epoch)
        experiment = comet_ml.get_running_experiment()
        if experiment is None or model is None:
            return

        checkpoint_path = os.path.join(args.output_dir, f"checkpoint-epoch-{epoch}")
        model.save_pretrained(checkpoint_path)
        tokenizer.save_pretrained(checkpoint_path)

        experiment.log_model(
            name=f"checkpoint_epoch_{epoch}",
            file_or_folder=checkpoint_path,
            metadata={"epoch": epoch},
        )
        shutil.rmtree(checkpoint_path)
        print(f"  → Logged checkpoint_epoch_{epoch} to CometML")

# ── Training ──────────────────────────────────────────────────────────────────
training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    learning_rate=LEARNING_RATE,
    weight_decay=0.01,
    eval_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    report_to=["comet_ml"],
    max_length=MAX_SEQ_LENGTH,
    dataset_text_field="text",
    packing=False,
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    processing_class=tokenizer,
    callbacks=[CheckpointCallback()],
)

print("Starting SFT training...")
trainer.train()

# ── Register final model to the CometML Model Registry ───────────────────────
experiment = comet_ml.get_running_experiment()
if experiment:
    model.save_pretrained(FINAL_MODEL_DIR)
    tokenizer.save_pretrained(FINAL_MODEL_DIR)

    experiment.log_model(
        name=REGISTRY_NAME,
        file_or_folder=FINAL_MODEL_DIR,
        metadata={"epochs": NUM_EPOCHS, "base_model": MODEL_NAME},
    )

    # Register to the Model Registry so it can be fetched by name and version.
    experiment.register_model(
        model_name=REGISTRY_NAME,
        registry_name=REGISTRY_NAME,
        version=MODEL_VERSION,
        tags=["sft", MODEL_NAME],
        comment=f"SFT on OpenAssistant Guanaco, {NUM_EPOCHS} epochs",
        public=False,
    )

    workspace = experiment.workspace
    experiment.end()

    print("\nTraining complete. Model registered to CometML Model Registry.")
    print(f"\nUse these values in use_registered_model.py:")
    print(f"  COMET_WORKSPACE={workspace}")
    print(f"  COMET_REGISTRY_NAME={REGISTRY_NAME}")
    print(f"  COMET_MODEL_VERSION={MODEL_VERSION}")
    print(f"\n  Registry URL: https://www.comet.com/{workspace}/model-registry/{REGISTRY_NAME}")

shutil.rmtree(FINAL_MODEL_DIR, ignore_errors=True)
