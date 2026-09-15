import litellm
import opik
from opik import opik_context

from . import config, prompts
from .analysis import CapacitySummary, Finding

_logger_wired = False


def _wire_llm_span_logging() -> None:
    """Register Opik's litellm callback once so LLM spans carry model/tokens/cost."""
    global _logger_wired
    if _logger_wired or config.DRY_RUN:
        return
    from litellm.integrations.opik.opik import OpikLogger

    litellm.callbacks = [OpikLogger()]
    _logger_wired = True


def _opik_metadata() -> dict:
    if config.DRY_RUN:
        return {}
    # WHY: this is how the litellm integration nests the LLM span under the current trace.
    return {
        "opik": {
            "current_span_data": opik_context.get_current_span_data(),
            "project_name": config.OPIK_PROJECT_NAME,
        }
    }


@opik.track(project_name=config.OPIK_PROJECT_NAME)
async def write_recommendations(summary: CapacitySummary, findings: list[Finding]) -> str:
    """One synthesis call: rule-based findings in, Markdown rightsizing report out."""
    _wire_llm_span_logging()
    response = await litellm.acompletion(
        model=config.GEN_MODEL,
        messages=[
            {"role": "system", "content": prompts.ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": prompts.analysis_payload(summary, findings)},
        ],
        metadata=_opik_metadata(),
    )
    return response.choices[0].message.content or ""
