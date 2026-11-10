"""Names and models shared by the evaluate and optimize steps."""

import os
from pathlib import Path

# WHY: an unset GitHub Actions variable arrives as "", so every setting falls back with `or`.
GEN_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL") or "anthropic/claude-haiku-4-5-20251001"
# WHY: the online rule runs inside Opik, so its model must match an AI provider set up in the workspace.
JUDGE_MODEL = os.environ.get("OPIK_ONLINE_JUDGE_MODEL") or "anthropic/claude-haiku-4-5-20251001"
PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME") or "eval-in-ci-example"
# WHY: the SDK clients read OPIK_PROJECT_NAME themselves (default "Default Project"); export the resolved
# name so the prompt, dataset, experiments, traces, online rule and links all use one project.
os.environ["OPIK_PROJECT_NAME"] = PROJECT_NAME

DATASET_NAME = "scenario-planner"
PROMPT_NAME = "scenario-planner"
TEST_SUITE_NAME = "scenario-planner-guardrails"
ONLINE_RULE_NAME = "scenario-plan-consistency"
ENV_PRODUCTION = "production"
TRAFFIC_TAG = "simulated-traffic"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

DRY_RUN: bool = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))
