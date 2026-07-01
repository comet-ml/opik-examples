import secrets

import opik
from opik.evaluation import evaluate, run_tests
from opik.evaluation.metrics import ContextRecall, Hallucination

from . import config
from .rag import answer


def experiment_name() -> str:
    return f"{config.OPIK_PROJECT_NAME}-{secrets.token_hex(3)}"


def _rag_task(item: dict) -> dict:
    # Live RAG: retrieve + generate from the query. Returns input/output/context for the metrics.
    return answer(item["query"])


def _suite_task(item: dict) -> dict:
    # The assertion judge reads ONLY `input` and `output`, so fold the retrieved messages
    # into `input` — otherwise the groundedness assertions ("grounded in the messages",
    # "does not invent events absent from the messages") have no source to check against.
    # Keep expected_output OUT of `input`, or the judge can use it to pass assertions that
    # should fail.
    result = answer(item["query"])
    return {
        "input": {"query": result["input"], "messages": result["context"]},
        "output": result["output"],
    }


def build_dataset(client, eval_cases: list[dict]):
    dataset = client.get_or_create_dataset(name=config.DATASET_NAME)
    dataset.insert(
        [
            {
                "query": c["query"],
                "expected_output": c["expected_output"],
                "messages": c["messages"],
                "messages_text": "\n".join(c["messages"]),
            }
            for c in eval_cases
        ]
    )
    return dataset


def build_suite(client, eval_cases: list[dict]):
    suite = client.get_or_create_test_suite(
        name=config.SUITE_NAME,
        global_assertions=[
            "The answer is grounded in the provided radio messages",
            "The answer does not invent events absent from the messages",
        ],
        global_execution_policy={"runs_per_item": 2, "pass_threshold": 2},
    )
    suite.insert([{"data": {"query": c["query"]}, "assertions": c["assertions"]} for c in eval_cases])
    return suite


def run_eval(eval_cases: list[dict]):
    client = opik.Opik()
    dataset = build_dataset(client, eval_cases)
    suite = build_suite(client, eval_cases)

    # Assertions, LLM-judged -> a pass rate. Test suites do NOT attach per-row feedback scores,
    # so these experiments show "-" in the UI's Feedback Scores column (expected; result is pass rate).
    suite_result = run_tests(
        test_suite=suite,
        task=_suite_task,
        model=config.JUDGE_MODEL,
        experiment_name=experiment_name(),
    )
    # scoring_metrics produce the numeric feedback scores that populate the UI's Feedback Scores column.
    eval_result = evaluate(
        dataset=dataset,
        task=_rag_task,
        scoring_metrics=[
            ContextRecall(model=config.JUDGE_MODEL),
            Hallucination(model=config.JUDGE_MODEL),
        ],
        experiment_name=experiment_name(),
    )
    return suite_result, eval_result
