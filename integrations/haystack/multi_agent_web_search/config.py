import os

from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SERPERDEV_API_KEY = os.environ.get("SERPERDEV_API_KEY")
OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")

OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "haystack-multi-agent-scout")
OPENAI_MODEL = os.environ.get("HAYSTACK_OPENAI_MODEL", "gpt-5-mini")

DRY_RUN = not (OPENAI_API_KEY and SERPERDEV_API_KEY and OPIK_API_KEY and OPIK_WORKSPACE)