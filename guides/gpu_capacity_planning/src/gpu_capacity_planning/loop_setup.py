"""Idempotent setup of the Opik feedback loop around the capacity recommendations.

Creates (or confirms) three things in the Opik workspace:
- the analyst prompt in the Prompt Library,
- an annotation queue where every new report/audit trace lands for SME review,
- an online LLM-as-judge rule that scores each new trace automatically.
"""

import opik
from opik.rest_api.types import AutomationRuleEvaluatorWrite_LlmAsJudge

from . import config, prompts

RULE_NAME = "capacity-recommendation-judge"


def _ensure_prompt(client: opik.Opik) -> str:
    prompt = client.create_prompt(name=config.PROMPT_NAME, prompt=prompts.ANALYST_SYSTEM_PROMPT)
    return f"prompt '{config.PROMPT_NAME}' (commit {prompt.commit})"


def _ensure_queue(client: opik.Opik) -> str:
    for queue in client.get_traces_annotation_queues():
        if queue.name == config.QUEUE_NAME:
            return f"annotation queue '{config.QUEUE_NAME}' (exists, {queue.items_count or 0} items)"
    client.create_traces_annotation_queue(
        name=config.QUEUE_NAME,
        project_name=config.OPIK_PROJECT_NAME,
        description="GPU rightsizing recommendations awaiting SME review",
        instructions=(
            "Rate each recommendation with '" + config.JUDGE_SCORE_NAME + "' (0-1): "
            "is it actionable, grounded in the utilization findings, and safe to apply?"
        ),
        comments_enabled=True,
    )
    return f"annotation queue '{config.QUEUE_NAME}' (created)"


def _project_id(client: opik.Opik) -> str:
    from opik.api_objects import rest_helpers

    return rest_helpers.resolve_project_id_by_name(client.rest_client, config.OPIK_PROJECT_NAME)


def _ensure_judge_rule(client: opik.Opik) -> str:
    project_id = _project_id(client)
    existing = client.rest_client.automation_rule_evaluators.find_evaluators(project_id=project_id)
    for rule in existing.content or []:
        if rule.name == RULE_NAME:
            return f"online judge rule '{RULE_NAME}' (exists)"

    rule = AutomationRuleEvaluatorWrite_LlmAsJudge.model_validate(
        {
            "name": RULE_NAME,
            "project_ids": [project_id],
            "sampling_rate": 1.0,
            "enabled": True,
            "action": "evaluator",
            "code": {
                "model": {"name": config.JUDGE_RULE_MODEL, "temperature": 0.0},
                "messages": [{"role": "USER", "content": prompts.ONLINE_JUDGE_TEMPLATE}],
                "variables": {"output": "output"},
                "schema": [
                    {
                        "name": config.JUDGE_SCORE_NAME,
                        "type": "DOUBLE",
                        "description": "0-1 quality of the rightsizing recommendation",
                    }
                ],
            },
        }
    )
    client.rest_client.automation_rule_evaluators.create_automation_rule_evaluator(request=rule)
    return (
        f"online judge rule '{RULE_NAME}' (created, model {config.JUDGE_RULE_MODEL}) - "
        "requires an AI provider key configured in the Opik workspace to execute"
    )


def ensure_loop() -> list[str]:
    """Create anything missing; safe to run repeatedly. Returns one status line per object."""
    client = opik.Opik(project_name=config.OPIK_PROJECT_NAME)
    return [_ensure_prompt(client), _ensure_queue(client), _ensure_judge_rule(client)]
