"""Offline Opik experiments: VLM only vs detector + VLM, then link results back to Comet EM.

Usage: uv run python scripts/05_run_experiments.py [--dataset NAME] [--nb-samples N] [--no-judge]
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import opik
from opik.evaluation import evaluate

from roadwork_demo.config import (
    VARIANTS,
    experiment_name,
    get_settings,
    is_full_run,
    should_link_back,
)
from roadwork_demo.data import load_eval_manifest
from roadwork_demo.metrics import JudgeVerdictCorrect, VerdictAccuracy
from roadwork_demo.pipeline import current_handoff, get_verdict_prompt, load_detector, run_frame
from roadwork_demo.verdicts import JUDGE_VERDICT_CORRECT, VERDICT_ACCURACY

HEADLINE_SCORES = (VERDICT_ACCURACY, JUDGE_VERDICT_CORRECT)


def make_task(variant: str, image_paths: dict[str, str]):
    def task(item: dict) -> dict:
        # WHY: returned as is, so experiment traces have the same output shape as production
        # traces (output.verdict) and the online rule and UI columns work on both.
        return run_frame(image_paths[item["file_name"]], variant)

    return task


def summarize(result) -> tuple[dict[str, float], dict[str, float]]:
    """Mean of each score, and verdict accuracy per expected class."""
    totals, per_class = defaultdict(list), defaultdict(list)
    for tr in result.test_results:
        expected = tr.test_case.dataset_item_content.get("expected_verdict")
        for sr in tr.score_results:
            if sr.scoring_failed:
                continue
            totals[sr.name].append(sr.value)
            if sr.name == VERDICT_ACCURACY:
                per_class[expected].append(sr.value)
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    return {k: mean(v) for k, v in totals.items()}, {k: mean(v) for k, v in per_class.items()}


def link_back_to_em(handoff, s, dataset_name: str, results: dict) -> None:
    """Write Opik experiment links and headline scores onto the Comet experiment."""
    from comet_ml import API

    exp = API().get_experiment_by_key(handoff.experiment_key)
    rows = []
    for variant, (result, means, _) in results.items():
        exp.log_other(f"opik_experiment_{variant}", result.experiment_name)
        exp.log_other(f"opik_experiment_url_{variant}", result.experiment_url)
        for score, value in means.items():
            exp.log_metric(f"opik_{score}_{variant}", value)
        rows.append(
            f'<tr><td><a href="{result.experiment_url}" target="_blank">{result.experiment_name}</a></td>'
            + "".join(f"<td>{means.get(m, float('nan')):.3f}</td>" for m in HEADLINE_SCORES)
            + "</tr>"
        )
    exp.log_other("opik_dataset", dataset_name)
    exp.log_other("opik_project", s.opik_project)
    exp.log_html(
        clear=True,
        html="<h3>Downstream evaluation in Opik</h3>"
        f"<p>Registered model <b>{handoff.registry_model}:{handoff.model_version}</b>, "
        f"Opik dataset <b>{dataset_name}</b>.</p>"
        "<table border='1' cellpadding='6'><tr><th>Opik experiment</th>"
        + "".join(f"<th>{m}</th>" for m in HEADLINE_SCORES)
        + "</tr>" + "".join(rows) + "</table>",
    )
    print(f"Linked Opik results onto Comet experiment: {handoff.experiment_url}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--nb-samples", type=int, default=None)
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()

    s = get_settings()
    handoff = current_handoff()
    dataset_name = args.dataset or s.opik_dataset
    manifest = load_eval_manifest(s.eval_manifest_path)
    image_paths = {item["file_name"]: item["path"] for item in manifest}

    client = opik.Opik()
    dataset = client.get_dataset(dataset_name)
    metrics = [VerdictAccuracy()]
    if not args.no_judge:
        metrics.append(JudgeVerdictCorrect(image_paths))

    full_run = is_full_run(dataset_name, s.opik_dataset, args.nb_samples)
    load_detector(handoff)  # download registry weights once, before worker threads start

    results = {}
    for variant in VARIANTS:
        result = evaluate(
            dataset=dataset,
            task=make_task(variant, image_paths),
            scoring_metrics=metrics,
            experiment_name=experiment_name(variant, handoff.model_version, full_run),
            project_name=s.opik_project,
            experiment_config=handoff.as_metadata()
            | {
                "variant": variant,
                "verdict_model": s.verdict_model,
                "judge_model": s.judge_model,
                "prompt_name": s.prompt_name,
            },
            prompts=[get_verdict_prompt()],
            experiment_tags=[handoff.model_tag(), variant],
            nb_samples=args.nb_samples,
            task_threads=4,
        )
        means, per_class = summarize(result)
        results[variant] = (result, means, per_class)

    print("\n=== Results ===")
    for variant, (result, means, per_class) in results.items():
        print(f"{result.experiment_name}: " + ", ".join(f"{k}={v:.3f}" for k, v in sorted(means.items())))
        print("   per-class accuracy: " + ", ".join(f"{k}={v:.2f}" for k, v in sorted(per_class.items())))
        print(f"   {result.experiment_url}")

    if should_link_back(handoff.model_version, dataset_name, s.opik_dataset, args.nb_samples):
        link_back_to_em(handoff, s, dataset_name, results)
    else:
        print(
            "\nNot linking back to Comet EM: only a full run on the default dataset with a "
            "registered model updates the experiment's headline Opik numbers."
        )


if __name__ == "__main__":
    main()
