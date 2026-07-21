import os

from dotenv import load_dotenv

load_dotenv()

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "prompt-versioning")

DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)

LLM_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", "openai/gpt-5-mini")
JUDGE_MODEL = LLM_MODEL
