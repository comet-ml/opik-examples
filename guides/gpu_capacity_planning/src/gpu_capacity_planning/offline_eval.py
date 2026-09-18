"""Offline evaluation: score the current analyst setup against the golden dataset.

Run this before shipping a prompt, code, or model change - the experiment it logs is the
regression gate: compare it in the Opik UI against the previous run of the same dataset.
"""

import litellm
import opik
from opik.evaluation import evaluate
from opik.evaluation.metrics.llm_judges.g_eval.metric import GEval

from . import config, prompts
from .recommender import analyst_prompt


def _task(item: dict) -> dict:
    system_prompt, _ = analyst_prompt()
    payload = (item.get("input") or {}).get("analysis_payload", "")
    response = litellm.completion(
        model=config.GEN_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
    )
    return {"output": response.choices[0].message.content or ""}


def run_offline_eval(dataset_name: str, experiment_name: str | None) -> str:
    """Evaluate the current prompt+model against the dataset; returns the experiment name."""
    client = opik.Opik(project_name=config.OPIK_PROJECT_NAME)
    dataset = client.get_dataset(dataset_name)
    _, prompt_obj = analyst_prompt()

    judge = GEval(
        task_introduction=prompts.JUDGE_TASK_INTRO,
        evaluation_criteria=prompts.JUDGE_RUBRIC,
        model=config.GEN_MODEL,
        name=config.JUDGE_SCORE_NAME,
        project_name=config.OPIK_PROJECT_NAME,
    )
    result = evaluate(
        dataset=dataset,
        task=_task,
        scoring_metrics=[judge],
        experiment_name=experiment_name,
        prompts=[prompt_obj] if prompt_obj else None,
        experiment_config={"model": config.GEN_MODEL, "prompt": config.PROMPT_NAME},
        task_threads=4,
    )
    return result.experiment_name
