"""Judge model / GenAI gateway wiring.

Point the LLM judges at your GenAI gateway (edit once). This is the ONLY
file about the model.
"""

import os

from opik.evaluation import models
from opik.evaluation.models import base_model

JudgeModel = str | base_model.OpikBaseModel


# ============================================================
# 1. JUDGE MODEL — set up your GenAI gateway here (edit once)
#    Path A: LiteLLMChatModel(...)           ← OpenAI-compatible gateway (default)
#    Path B: a custom OpikBaseModel subclass ← non-standard gateway
#    Full worked examples for BOTH paths:
#      https://www.comet.com/docs/opik/evaluation/metrics/custom_model
# ============================================================
def build_judge_model() -> JudgeModel:
    """Return the model every LLM judge uses.

    Path A (default): an OpenAI-compatible gateway via LiteLLM. Set GATEWAY_BASE_URL
    + GATEWAY_API_KEY + GATEWAY_MODEL. LiteLLMChatModel forwards base_url/api_key to
    litellm.completion, so the judge's calls route through your gateway. Because the
    model is routed as ``openai/<GATEWAY_MODEL>``, LiteLLM also reads OPENAI_API_KEY as
    the provider key — set it (to your gateway/OpenAI key) if the judge errors on auth.

    If GATEWAY_BASE_URL is unset, falls back to a bare model name (GATEWAY_MODEL, or
    OPIK_EXAMPLES_MODEL), which lets the module import and unit-test without a gateway.
    """
    # GATEWAY_MODEL is the local knob; OPIK_EXAMPLES_MODEL lets CI route judges to a
    # cheap model (used when GATEWAY_MODEL is unset).
    model_name = os.environ.get("GATEWAY_MODEL") or os.environ.get("OPIK_EXAMPLES_MODEL", "gpt-4o")
    base_url = os.environ.get("GATEWAY_BASE_URL")
    if not base_url:
        return model_name  # importable / testable without a gateway
    return models.LiteLLMChatModel(
        model_name=f"openai/{model_name}",
        base_url=base_url,
        api_key=os.environ.get("GATEWAY_API_KEY"),
        temperature=0.0,
    )

    # ---- Path B: non-standard gateway (uncomment & implement) --------------
    # from opik.evaluation.models import OpikBaseModel
    # class MyGatewayModel(OpikBaseModel):
    #     def __init__(self, model_name: str):
    #         super().__init__(model_name=model_name)
    #     def generate_string(self, input: str, **kwargs) -> str: ...
    #     def generate_provider_response(self, **kwargs): ...
    # return MyGatewayModel(model_name)
    # See: https://www.comet.com/docs/opik/evaluation/metrics/custom_model
