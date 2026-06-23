import secrets

import opik
from opik.evaluation import evaluate, run_tests
from opik.evaluation.metrics import AnswerRelevance, Hallucination

from . import config
from .app import run


def experiment_name() -> str:
    return f"{config.OPIK_PROJECT_NAME}-{secrets.token_hex(3)}"


def _task(item: dict) -> dict:
    # Runs the live app on a dataset item. Returns input/output/context for the metrics.
    return run(item)


def build_dataset(client, cases: list[dict]):
    dataset = client.get_or_create_dataset(name=config.DATASET_NAME)
    dataset.insert(
        [
            {
                "input": c["input"],
                "expected_output": c["expected_output"],
                "context": c["context"],
                "context_text": "\n".join(c["context"]),
            }
            for c in cases
        ]
    )
    return dataset


def build_suite(client, cases: list[dict]):
    suite = client.get_or_create_test_suite(
        name=config.SUITE_NAME,
        global_assertions=[
            "The answer is grounded in the provided context",
            "The answer does not invent details absent from the context",
        ],
        global_execution_policy={"runs_per_item": 2, "pass_threshold": 2},
    )
    suite.insert([{"data": {"input": c["input"]}, "assertions": c["assertions"]} for c in cases])
    return suite


def run_eval(cases: list[dict]):
    client = opik.Opik()
    dataset = build_dataset(client, cases)
    suite = build_suite(client, cases)

    suite_result = run_tests(
        test_suite=suite,
        task=_task,
        model=config.JUDGE_MODEL,
        experiment_name=experiment_name(),
    )
    eval_result = evaluate(
        dataset=dataset,
        task=_task,
        scoring_metrics=[
            AnswerRelevance(model=config.JUDGE_MODEL),
            Hallucination(model=config.JUDGE_MODEL),
        ],
        experiment_name=experiment_name(),
    )
    return suite_result, eval_result
