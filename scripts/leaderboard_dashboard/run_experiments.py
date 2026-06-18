"""
Runs 2 experiments against a shared dataset and writes a YAML file
with all details needed to configure a leaderboard dashboard.

No LLM API key required — uses heuristic scoring to simulate two
model configurations so the flow works end-to-end immediately.

Usage:
    source ../../.env.dev && python run_experiments.py
    source ../../.env.dev && python run_experiments.py --output my_config.yaml
"""

import argparse
import time
import yaml
from typing import Any

import opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import base_metric, score_result


# ---------------------------------------------------------------------------
# Dataset items — a small Q&A set used by both experiments
# ---------------------------------------------------------------------------

DATASET_ITEMS = [
    {
        "question": "What is the capital of France?",
        "expected_answer": "Paris",
        "category": "geography",
    },
    {
        "question": "What is 12 multiplied by 8?",
        "expected_answer": "96",
        "category": "math",
    },
    {
        "question": "Who wrote Hamlet?",
        "expected_answer": "Shakespeare",
        "category": "literature",
    },
    {
        "question": "What is the boiling point of water in Celsius?",
        "expected_answer": "100",
        "category": "science",
    },
    {
        "question": "What year did World War II end?",
        "expected_answer": "1945",
        "category": "history",
    },
]


# ---------------------------------------------------------------------------
# Simulated model responses
# (replace the body of each function with a real LLM call in production)
# ---------------------------------------------------------------------------

def model_a_respond(question: str) -> str:
    """
    Simulates a high-accuracy but verbose model (e.g. gpt-4o).
    Always includes the correct answer with full sentences.
    """
    answers = {
        "What is the capital of France?": "The capital of France is Paris, a major European city known for the Eiffel Tower.",
        "What is 12 multiplied by 8?": "12 multiplied by 8 equals 96.",
        "Who wrote Hamlet?": "Hamlet was written by William Shakespeare, the famous English playwright.",
        "What is the boiling point of water in Celsius?": "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
        "What year did World War II end?": "World War II ended in 1945 with the surrender of Germany and Japan.",
    }
    return answers.get(question, "I don't know.")


def model_b_respond(question: str) -> str:
    """
    Simulates a fast but occasionally wrong model (e.g. gpt-4o-mini).
    Gives terse answers and gets 1 question wrong.
    """
    answers = {
        "What is the capital of France?": "Paris",
        "What is 12 multiplied by 8?": "96",
        "Who wrote Hamlet?": "Shakespeare",
        "What is the boiling point of water in Celsius?": "212",   # wrong (Fahrenheit)
        "What year did World War II end?": "1945",
    }
    return answers.get(question, "Unknown.")


# ---------------------------------------------------------------------------
# Scoring metrics
# ---------------------------------------------------------------------------

class AccuracyMetric(base_metric.BaseMetric):
    """1.0 if expected_answer appears anywhere in the output, 0.0 otherwise."""

    def __init__(self) -> None:
        super().__init__(name="accuracy")

    def score(
        self, output: str, expected_answer: str, **kwargs: Any
    ) -> score_result.ScoreResult:
        hit = expected_answer.lower() in output.lower()
        return score_result.ScoreResult(
            name=self.name,
            value=1.0 if hit else 0.0,
            reason="Answer found in output" if hit else "Answer not found in output",
        )


class RelevanceMetric(base_metric.BaseMetric):
    """
    Heuristic relevance: checks whether the output contains keywords
    from the question (overlap > 0 → relevant).
    """

    def __init__(self) -> None:
        super().__init__(name="relevance")

    def score(self, output: str, question: str, **kwargs: Any) -> score_result.ScoreResult:
        stop_words = {"what", "is", "the", "of", "who", "did", "in", "a", "an"}
        question_keywords = {
            w.lower().strip("?") for w in question.split() if w.lower() not in stop_words
        }
        output_words = {w.lower() for w in output.split()}
        overlap = len(question_keywords & output_words)
        value = min(1.0, overlap / max(len(question_keywords), 1))
        return score_result.ScoreResult(
            name=self.name,
            value=round(value, 3),
            reason=f"Keyword overlap: {overlap}/{len(question_keywords)}",
        )


class ConcisenessMetric(base_metric.BaseMetric):
    """
    Penalises very long answers. Score = max(0, 1 - (words - 5) / 30).
    Answers under 5 words score 1.0; beyond 35 words score 0.
    """

    def __init__(self) -> None:
        super().__init__(name="conciseness")

    def score(self, output: str, **kwargs: Any) -> score_result.ScoreResult:
        word_count = len(output.split())
        value = max(0.0, 1.0 - (word_count - 5) / 30)
        return score_result.ScoreResult(
            name=self.name,
            value=round(value, 3),
            reason=f"Output word count: {word_count}",
        )


METRICS = [AccuracyMetric(), RelevanceMetric(), ConcisenessMetric()]


# ---------------------------------------------------------------------------
# Task factories
# ---------------------------------------------------------------------------

def make_task(respond_fn):
    """Returns an opik task function that wraps the given model response fn."""
    def task(dataset_item: dict[str, Any]) -> dict[str, Any]:
        question = dataset_item["question"]
        t0 = time.perf_counter()
        answer = respond_fn(question)
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "output": answer,
            "question": question,
            "expected_answer": dataset_item["expected_answer"],
            "latency_ms": latency_ms,
        }
    return task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def collect_score_names(results) -> list[str]:
    names: set[str] = set()
    for tr in results.test_results:
        for sr in tr.score_results:
            if not sr.scoring_failed:
                names.add(sr.name)
    return sorted(names)


def collect_metadata_keys(experiment_config: dict) -> list[str]:
    """
    Returns column IDs as the frontend expects them: 'metadata.<key>'.

    The widget filters selectedColumns for items starting with 'metadata.'
    to build metadata columns. The display label is formatted as 'config.<key>'
    by the frontend, but the ID itself must use the 'metadata.' prefix.
    """
    return [f"metadata.{k}" for k in experiment_config.keys()]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(output_path: str) -> None:
    client = opik.Opik()

    # -- Dataset --
    dataset_name = "leaderboard-demo"
    print(f"[1/5] Setting up dataset '{dataset_name}' ...")
    dataset = client.get_or_create_dataset(name=dataset_name)
    dataset.insert(DATASET_ITEMS)

    # -- Experiment configs (metadata shown in leaderboard) --
    config_a = {
        "model": "gpt-4o",
        "temperature": 0.2,
        "max_tokens": 512,
        "strategy": "verbose",
    }
    config_b = {
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "max_tokens": 128,
        "strategy": "terse",
    }

    # -- Experiment A --
    print("[2/5] Running Experiment A (gpt-4o, verbose) ...")
    results_a = evaluate(
        dataset=dataset,
        task=make_task(model_a_respond),
        scoring_metrics=METRICS,
        experiment_name="leaderboard-demo: gpt-4o",
        experiment_config=config_a,
        experiment_tags=["demo", "gpt-4o"],
        verbose=1,
    )

    # -- Experiment B --
    print("[3/5] Running Experiment B (gpt-4o-mini, terse) ...")
    results_b = evaluate(
        dataset=dataset,
        task=make_task(model_b_respond),
        scoring_metrics=METRICS,
        experiment_name="leaderboard-demo: gpt-4o-mini",
        experiment_config=config_b,
        experiment_tags=["demo", "gpt-4o-mini"],
        verbose=1,
    )

    # -- Collect leaderboard metadata --
    print("[4/5] Collecting score names and metadata keys ...")

    score_names = collect_score_names(results_a) or collect_score_names(results_b)
    score_column_ids = [f"feedback_scores.{n}" for n in score_names]

    metadata_column_ids = collect_metadata_keys(config_a)

    # Pick the ranking metric (prefer "accuracy" if present)
    ranking_metric = (
        "feedback_scores.accuracy"
        if "accuracy" in score_names
        else score_column_ids[0]
    )

    # -- Build output YAML --
    print(f"[5/5] Writing leaderboard config to '{output_path}' ...")

    leaderboard_config = {
        "dataset": {
            "id": results_a.dataset_id,
            "name": dataset_name,
        },
        "experiments": [
            {
                "id": results_a.experiment_id,
                "name": results_a.experiment_name,
                "model": config_a["model"],
                "url": results_a.experiment_url,
            },
            {
                "id": results_b.experiment_id,
                "name": results_b.experiment_name,
                "model": config_b["model"],
                "url": results_b.experiment_url,
            },
        ],
        "leaderboard": {
            "dashboard_name": "Model Evaluation Leaderboard",
            "description": "Ranks experiments by accuracy score",
            "ranking_metric": ranking_metric,
            "ranking_direction": True,   # True = descending (higher is better)
            "columns": {
                "predefined": [
                    "dataset_id",
                    "created_at",
                    "duration.p50",
                    "trace_count",
                    "total_estimated_cost_avg",
                ],
                "scores": score_column_ids,
                "metadata": metadata_column_ids,
            },
        },
    }

    with open(output_path, "w") as f:
        yaml.dump(leaderboard_config, f, default_flow_style=False, sort_keys=False)

    print()
    print("Done! Leaderboard config written to:", output_path)
    print()
    print("Experiments:")
    for exp in leaderboard_config["experiments"]:
        print(f"  - {exp['name']} ({exp['id']})")
        if exp["url"]:
            print(f"    {exp['url']}")
    print()
    print(f"Score columns: {score_column_ids}")
    print(f"Ranking by:    {ranking_metric} (higher is better)")
    print()
    print("Next step:")
    print(f"  source ../../.env.dev && python create_leaderboard_from_yaml.py --config {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run demo experiments and export leaderboard config.")
    parser.add_argument(
        "--output",
        default="leaderboard_config.yaml",
        help="Path to write the YAML config (default: leaderboard_config.yaml)",
    )
    args = parser.parse_args()
    main(args.output)
