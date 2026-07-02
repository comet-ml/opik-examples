import os

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "f1-radio-rag")

# No Opik credentials -> every command still runs and prints locally instead of calling Opik.
DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)

# litellm model strings. CI sets OPIK_EXAMPLES_MODEL to a cheap model (e.g. openai/gpt-4o-mini);
# locally, leave it unset to use the full model.
GEN_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", "anthropic/claude-sonnet-4-6")  # deployed summariser
JUDGE_MODEL = GEN_MODEL  # LLM-as-judge for metrics
OPTIMIZER_MODEL = GEN_MODEL  # meta-model that rewrites the prompt

CHROMA_DIR = "chroma_db"
COLLECTION = "f1_radio"

DATASET_NAME = "f1-radio-eval"
SUITE_NAME = "f1-radio-suite"
PROMPT_NAME = "f1-radio-summariser"
