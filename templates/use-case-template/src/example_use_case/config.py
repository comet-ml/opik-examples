import os

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "example-use-case")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# No Opik credentials -> every command still runs and prints locally instead of calling Opik.
DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)
# Generation/judging needs an Anthropic key; without it we describe what would happen.
LLM_READY = bool(ANTHROPIC_API_KEY)

# litellm model strings (Anthropic provider). Swap for any litellm-supported model.
# CI sets OPIK_EXAMPLES_MODEL to a cheap model; locally, leave it unset to use the full model.
GEN_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", "anthropic/claude-sonnet-4-6")  # the deployed app
JUDGE_MODEL = GEN_MODEL  # LLM-as-judge for metrics
OPTIMIZER_MODEL = GEN_MODEL  # meta-model that rewrites the prompt

DATASET_NAME = "example-use-case-eval"
SUITE_NAME = "example-use-case-suite"
PROMPT_NAME = "example-use-case-prompt"
