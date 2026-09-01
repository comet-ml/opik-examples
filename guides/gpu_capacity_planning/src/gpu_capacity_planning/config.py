import os

COMET_API_KEY = os.environ.get("COMET_API_KEY")
COMET_WORKSPACE = os.environ.get("COMET_WORKSPACE")
COMET_URL_OVERRIDE = os.environ.get("COMET_URL_OVERRIDE")

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "gpu-capacity-planning")

# No Opik credentials -> collect + analyze locally, skip the LLM call and Opik delivery.
DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)
if DRY_RUN:
    # WHY: tracked functions still execute in dry-run; without this the SDK would try to send traces.
    os.environ.setdefault("OPIK_TRACK_DISABLE", "true")

# No Comet EM credentials -> serve sample runs from the bundled synthetic MCP server.
SYNTHETIC = not COMET_API_KEY
SYNTHETIC_WORKSPACE = "demo-workspace"

# litellm model string (Anthropic provider). Swap for any litellm-supported model.
# CI sets OPIK_EXAMPLES_MODEL to a cheap model; locally, leave it unset to use the full model.
GEN_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", "anthropic/claude-sonnet-5")

# Rightsizing thresholds (percent mean GPU utilization) and sweep cap.
LOW_UTIL_PCT = float(os.environ.get("CAPACITY_LOW_UTIL_PCT", "30"))
IDLE_UTIL_PCT = float(os.environ.get("CAPACITY_IDLE_UTIL_PCT", "10"))
MAX_RUNS = int(os.environ.get("CAPACITY_MAX_RUNS", "50"))
