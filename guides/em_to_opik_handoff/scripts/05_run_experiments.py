"""Offline Opik experiments for one detector version, then link the results back to Comet EM.

Usage: uv run python scripts/05_run_experiments.py [--detector production|<version>|stock]
           [--variants vlm_only detector_vlm] [--dataset NAME] [--nb-samples N] [--no-judge]

Run it once per detector version: the experiment for a version is named detector_vlm-<version>.
vlm_only runs no detector, so it exists once and carries no detector identity.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import opik
from opik.evaluation import evaluate
from opik.exceptions import ExperimentNotFound

from roadwork_demo.config import (
    VARIANTS,
    Handoff,
    Settings,
    exit_if_dry_run,
    experiment_name,
    get_settings,
    is_full_run,
    should_link_back,
)
from roadwork_demo.data import VERDICTS, load_eval_manifest
from roadwork_demo.gate import item_scores, latest
from roadwork_demo.metrics import JudgeVerdictCorrect, VerdictAccuracy, accuracy_by_class, per_class_accuracy
from roadwork_demo.pipeline import get_verdict_prompt, handoff_or_exit, load_detector, run_frame
from roadwork_demo.verdicts import JUDGE_VERDICT_CORRECT, VERDICT_ACCURACY

HEADLINE_SCORES = (VERDICT_ACCURACY, JUDGE_VERDICT_CORRECT)
REFERENCE_VARIANT = "vlm_only"


def make_task(variant: str, image_paths: dict[str, str], handoff: Handoff | None):
    def task(item: dict) -> dict:
        # WHY: returned as is, so experiment traces have the same output shape as production
        # traces (output.verdict) and the online rule and UI columns work on both.
        return run_frame(image_paths[item["file_name"]], variant, handoff)

    return task


def summarize(result) -> dict[str, float]:
    """Mean of each score over the items that were scored."""
    totals = defaultdict(list)
    for tr in result.test_results:
        for sr in tr.score_results:
            if not sr.scoring_failed:
                totals[sr.name].append(sr.value)
    return {name: sum(values) / len(values) for name, values in totals.items()}


def reference_accuracy(client: opik.Opik) -> float | None:
    """Verdict accuracy of the latest full vlm_only experiment, if there is one."""
    name = experiment_name(REFERENCE_VARIANT, None)
    try:
        experiment = latest(client.get_experiments_by_name(name), name)
    except ExperimentNotFound:
        experiment = None
    scores = item_scores(experiment) if experiment else {}
    return sum(scores.values()) / len(scores) if scores else None


def link_back_to_em(
    handoff: Handoff,
    s: Settings,
    dataset_name: str,
    dataset_version: str | None,
    result,
    means: dict[str, float],
    per_class: dict[str, float],
    vlm_only_accuracy: float | None,
) -> None:
    """Write the Opik experiment link and scores onto the Comet experiment that trained the detector.

    Metric names carry no version or variant, so the EM experiment table and panels compare
    training runs directly: mAP next to downstream verdict accuracy.
    """
    from comet_ml import API

    exp = API().get_experiment_by_key(handoff.experiment_key)
    if exp is None:
        print(f"\nComet experiment {handoff.experiment_key} no longer exists; nothing linked back.")
        return
    for score, value in means.items():
        exp.log_metric(f"opik_{score}", value)
    for verdict, value in per_class.items():
        exp.log_metric(f"opik_accuracy_{verdict}", value)
    exp.log_other("opik_experiment", result.experiment_name)
    exp.log_other("opik_experiment_url", result.experiment_url)
    exp.log_other("opik_dataset", dataset_name)
    exp.log_other("opik_dataset_version", dataset_version)
    exp.log_other("opik_project", s.project)
    if vlm_only_accuracy is not None:
        exp.log_other("opik_vlm_only_accuracy", round(vlm_only_accuracy, 4))
    exp.add_tags(["opik-evaluated"])

    columns = [*HEADLINE_SCORES, *(f"accuracy_{v}" for v in VERDICTS)]
    values = means | {f"accuracy_{verdict}": value for verdict, value in per_class.items()}
    cells = "".join(f"<td>{values[c]:.3f}</td>" if c in values else "<td></td>" for c in columns)
    link = f'<a href="{result.experiment_url}" target="_blank">{result.experiment_name}</a>'
    rows = f"<tr><td>{link}</td>{cells}</tr>"
    if vlm_only_accuracy is not None:
        blanks = "<td></td>" * (len(columns) - 1)
        rows += (
            f"<tr><td>{REFERENCE_VARIANT} (no detector, reference)</td>"
            f"<td>{vlm_only_accuracy:.3f}</td>{blanks}</tr>"
        )
    exp.log_html(
        clear=True,
        html="<h3>Downstream evaluation in Opik</h3>"
        f"<p>Registered model <b>{handoff.registry_model}:{handoff.model_version}</b>, Opik dataset "
        f"<b>{dataset_name}</b> version <b>{dataset_version}</b>, project <b>{s.project}</b>.</p>"
        "<table border='1' cellpadding='6'><tr><th>Opik experiment</th>"
        + "".join(f"<th>{c}</th>" for c in columns)
        + f"</tr>{rows}</table>",
    )
    print(f"\nLinked Opik results onto Comet experiment: {handoff.experiment_url}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default=None, help="production, a registry version or stock")
    ap.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--nb-samples", type=int, default=None)
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()

    s = get_settings()
    exit_if_dry_run(s, f"run the {', '.join(args.variants)} experiments on dataset '{s.opik_dataset}'")
    dataset_name = args.dataset or s.opik_dataset
    manifest = load_eval_manifest(s.eval_manifest_path)
    image_paths = {item["file_name"]: item["path"] for item in manifest}

    client = opik.Opik()
    dataset = client.get_dataset(dataset_name)
    dataset_version = dataset.get_current_version_name()
    metrics = [VerdictAccuracy()]
    if not args.no_judge:
        metrics.append(JudgeVerdictCorrect(image_paths))

    full_run = is_full_run(dataset_name, s.opik_dataset, args.nb_samples)
    handoff = None
    if "detector_vlm" in args.variants:
        handoff = handoff_or_exit(args.detector)
        load_detector(handoff)  # download registry weights once, before worker threads start

    results = {}
    for variant in args.variants:
        # WHY: only the variant that runs the detector carries its identity; vlm_only is one
        # experiment for every detector version.
        h = handoff if variant == "detector_vlm" else None
        config = {
            "variant": variant,
            "verdict_model": s.verdict_model,
            "prompt_name": s.prompt_name,
            "dataset_version": dataset_version,
        }
        if not args.no_judge:
            config["judge_model"] = s.judge_model
        result = evaluate(
            dataset=dataset,
            task=make_task(variant, image_paths, h),
            scoring_metrics=metrics,
            experiment_name=experiment_name(variant, h.model_version if h else None, full_run),
            experiment_config=(h.as_metadata() | config) if h else config,
            prompts=[get_verdict_prompt()],
            experiment_tags=[h.model_tag(), variant] if h else [variant],
            experiment_scoring_functions=[per_class_accuracy],
            nb_samples=args.nb_samples,
            task_threads=4,
        )
        results[variant] = (result, summarize(result), accuracy_by_class(result.test_results))

    print(f"\n=== Results (dataset {dataset_name}, version {dataset_version}) ===")
    for result, means, per_class in results.values():
        print(f"{result.experiment_name}: " + ", ".join(f"{k}={v:.3f}" for k, v in sorted(means.items())))
        print("   per-class accuracy: " + ", ".join(f"{k}={v:.2f}" for k, v in sorted(per_class.items())))
        print(f"   {result.experiment_url}")

    if handoff and should_link_back(handoff.model_version, dataset_name, s.opik_dataset, args.nb_samples):
        result, means, per_class = results["detector_vlm"]
        link_back_to_em(
            handoff, s, dataset_name, dataset_version, result, means, per_class, reference_accuracy(client)
        )
    else:
        print(
            "\nNot linking back to Comet EM: only a full detector_vlm run on the default dataset "
            "with a registered model updates the training experiment's Opik numbers."
        )


if __name__ == "__main__":
    main()
