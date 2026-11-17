"""Create an Opik online evaluation rule: a vision LLM judge scores every new trace.

Usage: uv run python scripts/08_online_rule.py [--delete] [--model NAME]

Optional part of the demo. Skip it where online evaluation is not allowed; nothing else
depends on it. The judge model runs inside Opik, so it needs a provider configured in the
workspace (Opik UI -> Configuration -> AI Providers). Model resolution: --model, then
OPIK_ONLINE_JUDGE_MODEL, then "opik-free-model", which works with no provider key.
"""

from __future__ import annotations

import argparse

import opik
from opik.rest_api.types import (
    AutomationRuleEvaluatorWrite_LlmAsJudge,
    ImageUrlWrite,
    LlmAsJudgeCodeWrite,
    LlmAsJudgeMessageContentWrite,
    LlmAsJudgeMessageWrite,
    LlmAsJudgeModelParametersWrite,
    LlmAsJudgeOutputSchemaWrite,
)

from roadwork_demo.config import get_settings
from roadwork_demo.metrics import judge_prompt
from roadwork_demo.verdicts import ONLINE_VERDICT_CORRECT as SCORE_NAME

RULE_NAME = "roadwork-online-judge"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--model", default=None, help="judge model name as Opik knows it")
    ap.add_argument("--text-only", action="store_true", help="judge verdict and reason without the image")
    args = ap.parse_args()

    s = get_settings()
    client = opik.Opik()
    rules = client.rest_client.automation_rule_evaluators
    project = client.rest_client.projects.retrieve_project(name=s.project)
    existing = [
        r
        for r in (rules.find_evaluators(project_id=project.id, name=RULE_NAME, size=50).content or [])
        if r.name == RULE_NAME
    ]

    if args.delete:
        if existing:
            rules.delete_automation_rule_evaluator_batch(ids=[r.id for r in existing], project_id=project.id)
        print(f"Deleted {len(existing)} rule(s) named '{RULE_NAME}'.")
        return
    if existing:
        print(f"Rule '{RULE_NAME}' already exists on project '{s.project}'. Nothing to do.")
        return

    judge_text = judge_prompt()
    variables = {"verdict": "output.verdict", "reason": "output.reason"}
    if args.text_only:
        variables["detections"] = "output.detections"
        message = LlmAsJudgeMessageWrite(
            role="USER",
            content=(
                f"{judge_text}\n\nNo image is available. Judge from the detector output instead.\n"
                "Detector output: {{detections}}\nSystem verdict: {{verdict}}\nSystem reason: {{reason}}"
            ),
        )
    else:
        variables["image"] = "input.image"
        message = _image_message(judge_text)
    code = LlmAsJudgeCodeWrite(
        model=LlmAsJudgeModelParametersWrite(name=args.model or s.online_judge_model),
        messages=[message],
        variables=variables,
        schema_=[
            LlmAsJudgeOutputSchemaWrite(
                name=SCORE_NAME,
                type="BOOLEAN",
                description=(
                    "True if the system verdict is right for the image "
                    "and the reason refers to visible evidence."
                ),
            )
        ],
    )
    _create(rules, project, code, s)


def _image_message(judge_text: str) -> LlmAsJudgeMessageWrite:
    return LlmAsJudgeMessageWrite(
        role="USER",
        # WHY: the image must be an image_url content part, not a {{variable}} in the text.
        content_array=[
            LlmAsJudgeMessageContentWrite(
                type="text",
                text=f"{judge_text}\n\nSystem verdict: {{{{verdict}}}}\nSystem reason: {{{{reason}}}}",
            ),
            LlmAsJudgeMessageContentWrite(type="image_url", image_url=ImageUrlWrite(url="{{image}}")),
        ],
        structured_content=True,
    )


def _create(rules, project, code, s) -> None:
    try:
        rules.create_automation_rule_evaluator(
            request=AutomationRuleEvaluatorWrite_LlmAsJudge(
                name=RULE_NAME,
                project_ids=[project.id],
                sampling_rate=1.0,
                enabled=True,
                action="evaluator",
                code=code,
            )
        )
    except Exception as exc:
        raise SystemExit(
            f"Could not create the rule: {exc}\n"
            "If the model or provider is not available: Opik UI -> Configuration -> AI Providers "
            "-> add an Anthropic key, then re-run (optionally with --model <name shown in the UI>)."
        ) from exc
    print(f"Created online rule '{RULE_NAME}' on project '{s.project}' (score: {SCORE_NAME}).")


if __name__ == "__main__":
    main()
