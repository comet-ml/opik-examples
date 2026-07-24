import os
from pathlib import Path

DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"

_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", DEFAULT_MODEL)
GEN_MODEL = _MODEL
JUDGE_MODEL = _MODEL
OPTIMIZER_MODEL = _MODEL

PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "prompt-agent-optimization")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHROMA_DIR = str(Path(__file__).resolve().parent.parent / "chroma_db")
COLLECTION = "product_docs"

# Provider key env var expected for each litellm provider prefix.
_PROVIDER_KEYS = {
    "anthropic/": "ANTHROPIC_API_KEY",
    "openai/": "OPENAI_API_KEY",
    "gemini/": "GEMINI_API_KEY",
}


def check_prerequisites() -> None:
    """Raise RuntimeError listing every missing required env var. No DRY_RUN fallback."""
    missing = []
    for var in ("OPIK_API_KEY", "OPIK_WORKSPACE"):
        if not os.environ.get(var):
            missing.append(var)
    provider_key = next(
        (key for prefix, key in _PROVIDER_KEYS.items() if GEN_MODEL.startswith(prefix)),
        None,
    )
    if provider_key and not os.environ.get(provider_key):
        missing.append(f"{provider_key} (for model {GEN_MODEL})")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Set them before running this guide (see the README)."
        )
